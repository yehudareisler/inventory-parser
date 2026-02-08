"""Tests for the inventory TUI — multi-stage interaction tests.

These tests verify the interactive review/edit workflow by mocking
user input (via monkeypatch on builtins.input) and checking returned
values and printed output (via capsys) at each stage.

Each test simulates a complete user interaction:
  parse → display → user commands → verify outcome
"""

import pytest
from datetime import date

from inventory_parser import parse, ParseResult
from inventory_tui import (
    review_loop, display_result, eval_qty, parse_date,
    find_partner, update_partner, check_alias_opportunity,
)


# ============================================================
# Fixtures
# ============================================================

TODAY = date(2025, 3, 19)


@pytest.fixture
def config():
    """Standard test config — same as test_parser.py plus transaction_types."""
    return {
        'items': [
            'cherry tomatoes', 'sweet cherry tomatoes', 'small potatoes',
            'spaghetti', 'cucumbers', 'chicken', 'carrots', 'aluminum pans',
            'froot loops', 'cornflakes', 'cheerios', 'cocoa puffs', 'trix',
        ],
        'aliases': {
            'small pot': 'small potatoes',
            'cherry tom': 'cherry tomatoes',
            'spaghetti noodles': 'spaghetti',
            'spuds': 'small potatoes',
        },
        'locations': ['L', 'C', 'N'],
        'default_source': 'warehouse',
        'transaction_types': [
            'starting_point', 'recount', 'warehouse_to_branch',
            'supplier_to_warehouse', 'eaten', 'between_branch',
            'between_warehouses', 'inside_branch',
        ],
        'action_verbs': {
            'warehouse_to_branch': ['passed', 'gave', 'sent', 'delivered'],
            'supplier_to_warehouse': ['received', 'got'],
            'eaten': ['eaten', 'consumed', 'used'],
        },
        'unit_conversions': {
            'cherry tomatoes': {'base_unit': 'count', 'small box': 990, 'box': 1980},
            'sweet cherry tomatoes': {'base_unit': 'count', 'small box': 990, 'box': 1980},
            'small potatoes': {'base_unit': 'count', 'box': 920},
        },
    }


def make_input(responses):
    """Create a mock input() that returns responses in sequence."""
    it = iter(responses)
    def mock_input(prompt=''):
        try:
            return next(it)
        except StopIteration:
            raise EOFError("No more mock inputs")
    return mock_input


# ============================================================
# Unit tests: helper functions
# ============================================================

class TestEvalQty:
    def test_plain_number(self):
        assert eval_qty("34") == 34

    def test_float(self):
        assert eval_qty("0.5") == 0.5

    def test_math_x(self):
        assert eval_qty("2x17") == 34

    def test_math_star(self):
        assert eval_qty("11*920") == 10120

    def test_invalid(self):
        assert eval_qty("abc") is None


class TestParseDate:
    def test_dot_format(self):
        assert parse_date("15.3.25") == date(2025, 3, 15)

    def test_slash_format(self):
        assert parse_date("3/15/25") == date(2025, 3, 15)

    def test_iso_format(self):
        assert parse_date("2025-03-15") == date(2025, 3, 15)

    def test_invalid(self):
        assert parse_date("not-a-date") is None


# ============================================================
# Unit tests: double-entry partner detection
# ============================================================

class TestFindPartner:
    def test_finds_partner(self):
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34},
        ]
        assert find_partner(rows, 0) == 1
        assert find_partner(rows, 1) == 0

    def test_no_partner_different_batch(self):
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34},
            {'batch': 2, 'inv_type': 'spaghetti', 'qty': 34},
        ]
        assert find_partner(rows, 0) is None

    def test_no_partner_single_row(self):
        rows = [
            {'batch': 1, 'inv_type': 'cucumbers', 'qty': 4},
        ]
        assert find_partner(rows, 0) is None


class TestUpdatePartner:
    def test_item_update_syncs(self):
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34},
        ]
        update_partner(rows, 0, 'inv_type', 'cherry tomatoes')
        assert rows[1]['inv_type'] == 'cherry tomatoes'

    def test_qty_update_negates(self):
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34},
        ]
        update_partner(rows, 0, 'qty', -50)
        assert rows[1]['qty'] == 50

    def test_location_not_synced(self):
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34, 'vehicle_sub_unit': 'warehouse'},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34, 'vehicle_sub_unit': 'L'},
        ]
        update_partner(rows, 0, 'vehicle_sub_unit', 'C')
        assert rows[1]['vehicle_sub_unit'] == 'L'  # unchanged


# ============================================================
# Display tests
# ============================================================

class TestDisplay:
    def test_shows_row_data(self, config, capsys):
        result = parse("passed 2x17 spaghetti noodles to L", config, today=TODAY)
        display_result(result.rows)
        output = capsys.readouterr().out
        assert 'spaghetti' in output
        assert '-34' in output
        assert 'warehouse' in output

    def test_shows_notes(self, capsys):
        display_result([], notes=["Rimon to N via naor by phone"])
        output = capsys.readouterr().out
        assert 'Rimon to N' in output
        assert 'Note' in output

    def test_shows_unparseable_warnings(self, capsys):
        display_result([], unparseable=["4 82 95 3 1"])
        output = capsys.readouterr().out
        assert 'Could not parse' in output
        assert '4 82 95 3 1' in output

    def test_warning_flag_on_missing_fields(self, capsys):
        rows = [{
            'date': TODAY, 'inv_type': 'cucumbers', 'qty': 4,
            'trans_type': None, 'vehicle_sub_unit': None,
            'batch': 1, 'notes': None,
        }]
        display_result(rows)
        output = capsys.readouterr().out
        assert '\u26a0' in output  # warning symbol
        assert '???' in output    # placeholder for None fields


# ============================================================
# Review loop: confirm and quit
# ============================================================

class TestReviewConfirmQuit:
    def test_confirm_returns_rows(self, config, monkeypatch):
        """Parse eaten by L → confirm → returns the parsed row."""
        result = parse("eaten by L 15.3.25\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["c"]))
        outcome = review_loop(result, "eaten by L 15.3.25\n4 cucumbers", config)

        assert outcome is not None
        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'cucumbers'
        assert outcome['rows'][0]['qty'] == 4
        assert outcome['rows'][0]['trans_type'] == 'eaten'
        assert outcome['rows'][0]['vehicle_sub_unit'] == 'L'

    def test_quit_returns_none(self, config, monkeypatch):
        """Parse → quit → returns None (discarded)."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["q"]))
        outcome = review_loop(result, "4 cucumbers to L", config)
        assert outcome is None

    def test_confirm_preserves_notes(self, config, monkeypatch):
        """Parse with transactions + note → confirm → both preserved."""
        result = parse(
            "cucumber\nsmall potatoes\nRimon to N via naor by phone",
            config, today=TODAY,
        )
        monkeypatch.setattr('builtins.input', make_input(["c"]))
        outcome = review_loop(result, "...", config)

        assert len(outcome['rows']) == 4  # 2 items × double-entry
        assert len(outcome['notes']) == 1
        assert 'Rimon' in outcome['notes'][0]


# ============================================================
# Review loop: field editing
# ============================================================

class TestReviewEditing:
    def test_edit_trans_type(self, config, monkeypatch):
        """Edit trans_type from warehouse_to_branch to eaten.

        Stage 1: Parse "4 cucumbers to L" → table with warehouse_to_branch
        Stage 2: User types "1t" → trans_type options shown
        Stage 3: User types "e" → selects 'eaten' (5th option)
        Stage 4: User types "c" → confirms
        Verify: both rows (double-entry pair) have trans_type='eaten'
        """
        result = parse("4 cucumbers to L", config, today=TODAY)
        # transaction_types: [a]starting_point [b]recount [c]warehouse_to_branch
        #   [d]supplier_to_warehouse [e]eaten [f]between_branch ...
        monkeypatch.setattr('builtins.input', make_input(["1t", "e", "c"]))
        outcome = review_loop(result, "4 cucumbers to L", config)

        assert outcome['rows'][0]['trans_type'] == 'eaten'
        assert outcome['rows'][1]['trans_type'] == 'eaten'  # partner auto-updated

    def test_edit_qty_with_math(self, config, monkeypatch):
        """Edit qty using math expression.

        Stage 1: Parse → row with qty=4
        Stage 2: User types "1q" → qty prompt
        Stage 3: User types "2x17" → qty becomes 34
        Stage 4: User types "c" → confirms
        """
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1q", "2x17", "c"]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)
        assert outcome['rows'][0]['qty'] == 34

    def test_edit_date(self, config, monkeypatch):
        """Edit date field.

        Stage 1: Parse → row with today's date
        Stage 2: User types "1d" → date prompt
        Stage 3: User types "25.12.25" → date becomes 2025-12-25
        Stage 4: User types "c" → confirms
        """
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1d", "25.12.25", "c"]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)
        assert outcome['rows'][0]['date'] == date(2025, 12, 25)

    def test_edit_item_updates_partner(self, config, monkeypatch):
        """Editing item on a double-entry row updates the partner row.

        Stage 1: Parse "passed 4 spaghetti to L" → 2 rows (double-entry)
        Stage 2: User types "1i" → item options shown
        Stage 3: User types "a" → selects 'cherry tomatoes' (1st item)
        Stage 4: User types "c" → confirms
        Verify: BOTH rows now show 'cherry tomatoes'
        """
        result = parse("passed 4 spaghetti to L", config, today=TODAY)
        assert len(result.rows) == 2
        # items: [a]cherry tomatoes [b]sweet cherry tomatoes [c]small potatoes
        #   [d]spaghetti [e]cucumbers ...
        monkeypatch.setattr('builtins.input', make_input(["1i", "a", "c"]))
        outcome = review_loop(result, "passed 4 spaghetti to L", config)

        assert outcome['rows'][0]['inv_type'] == 'cherry tomatoes'
        assert outcome['rows'][1]['inv_type'] == 'cherry tomatoes'

    def test_edit_notes(self, config, monkeypatch):
        """Edit notes field (free text).

        Stage 1: Parse → row with no notes
        Stage 2: User types "1n" → notes prompt
        Stage 3: User types text → notes set
        Stage 4: User types "c" → confirms
        """
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1n", "special delivery", "c"]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)
        assert outcome['rows'][0]['notes'] == 'special delivery'


# ============================================================
# Review loop: row operations
# ============================================================

class TestReviewRowOps:
    def test_delete_row(self, config, monkeypatch):
        """Delete a row from the table.

        Stage 1: Parse → 2 rows (cucumbers, spaghetti)
        Stage 2: User types "x1" → deletes cucumbers row
        Stage 3: User types "c" → confirms
        Verify: only spaghetti remains
        """
        result = parse("eaten by L\n4 cucumbers\n2 spaghetti", config, today=TODAY)
        assert len(result.rows) == 2
        monkeypatch.setattr('builtins.input', make_input(["x1", "c"]))
        outcome = review_loop(result, "...", config)

        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'spaghetti'

    def test_add_row(self, config, monkeypatch):
        """Add an empty row.

        Stage 1: Parse → 1 row
        Stage 2: User types "+" → new empty row appended
        Stage 3: User types "c" → incomplete row warning
        Stage 4: User types "y" → confirms anyway
        Verify: 2 rows, second is empty template
        """
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["+", "c", "y"]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 2
        assert outcome['rows'][1]['inv_type'] == '???'


# ============================================================
# Review loop: edit and retry
# ============================================================

class TestEditRetry:
    def test_retry_from_unparseable(self, config, monkeypatch):
        """Unparseable input → edit line → re-parse succeeds.

        Stage 1: Parse "4 82 95 3 1" → no rows, goes to unparseable flow
        Stage 2: User types "e" → edit mode, shown numbered lines
        Stage 3: User edits line 1, then Enter to re-parse
        Stage 4: Re-parsed into rows → shown as table
        Stage 5: User types "c" → confirms
        """
        result = parse("4 82 95 3 1", config, today=TODAY)
        assert len(result.rows) == 0
        assert len(result.unparseable) > 0

        monkeypatch.setattr('builtins.input', make_input([
            "e",                    # choose edit
            "1",                    # edit line 1
            "4 cucumbers to L",     # replacement text
            "",                     # finish editing (re-parse)
            "c",                    # confirm new parse
        ]))
        outcome = review_loop(result, "4 82 95 3 1", config)

        assert outcome is not None
        assert len(outcome['rows']) == 2  # double-entry for cucumbers to L
        assert outcome['rows'][1]['inv_type'] == 'cucumbers'
        assert outcome['rows'][1]['vehicle_sub_unit'] == 'L'

    def test_skip_unparseable(self, config, monkeypatch):
        """Unparseable input → skip → returns None."""
        result = parse("4 82 95 3 1", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["s"]))
        outcome = review_loop(result, "4 82 95 3 1", config)
        assert outcome is None

    def test_retry_from_normal_review(self, config, monkeypatch):
        """Normal parse → user edits lines → re-parse with different result."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input([
            "r",                            # retry
            "1",                            # edit line 1
            "passed 2x17 spaghetti to L",   # replacement
            "2",                            # edit line 2
            "",                             # delete it
            "",                             # finish editing (re-parse)
            "c",                            # confirm
        ]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)

        assert len(outcome['rows']) == 2
        assert outcome['rows'][0]['inv_type'] == 'spaghetti'
        assert outcome['rows'][0]['qty'] == -34


# ============================================================
# Review loop: note-only input
# ============================================================

class TestNoteHandling:
    def test_note_save(self, config, monkeypatch):
        """Note-only input → save as note.

        Stage 1: Parse "Rimon to N via naor by phone" → no rows, 1 note
        Stage 2: User types "n" → save note
        Verify: returns with the note preserved
        """
        result = parse("Rimon to N via naor by phone", config, today=TODAY)
        assert len(result.notes) >= 1
        monkeypatch.setattr('builtins.input', make_input(["n"]))
        outcome = review_loop(result, "Rimon to N via naor by phone", config)

        assert outcome is not None
        assert len(outcome['notes']) >= 1
        assert 'Rimon' in outcome['notes'][0]

    def test_note_skip(self, config, monkeypatch):
        """Note-only input → skip → discard."""
        result = parse("Rimon to N via naor by phone", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["s"]))
        outcome = review_loop(result, "Rimon to N via naor by phone", config)
        assert outcome is None


# ============================================================
# Alias learning (unit tests)
# ============================================================

class TestAliasLearning:
    def test_detects_alias_opportunity(self, config):
        """Unknown token edited to canonical name → alias opportunity."""
        rows = [{'inv_type': 'small potatoes', 'qty': 4}]
        original_tokens = {0: 'taters'}  # not canonical, not a known alias
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 1
        assert prompts[0] == ('taters', 'small potatoes')

    def test_no_opportunity_for_canonical(self, config):
        """Canonical item edited to another canonical → no alias prompt."""
        rows = [{'inv_type': 'small potatoes', 'qty': 4}]
        original_tokens = {0: 'cucumbers'}  # both are canonical
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 0

    def test_no_opportunity_for_known_alias(self, config):
        """Known alias → no redundant alias prompt."""
        rows = [{'inv_type': 'small potatoes', 'qty': 4}]
        original_tokens = {0: 'spuds'}  # already in aliases
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 0

    def test_no_opportunity_for_empty_original(self, config):
        """Empty string original → no alias prompt."""
        rows = [{'inv_type': 'cucumbers', 'qty': 4}]
        prompts = check_alias_opportunity(rows, {0: ''}, config)
        assert len(prompts) == 0

    def test_no_opportunity_for_question_marks(self, config):
        """'???' original → no alias prompt."""
        rows = [{'inv_type': 'cucumbers', 'qty': 4}]
        prompts = check_alias_opportunity(rows, {0: '???'}, config)
        assert len(prompts) == 0

    def test_no_opportunity_for_same_word(self, config):
        """Same as canonical → no alias prompt."""
        rows = [{'inv_type': 'cucumbers', 'qty': 4}]
        prompts = check_alias_opportunity(rows, {0: 'cucumbers'}, config)
        assert len(prompts) == 0

    def test_out_of_bounds_index_no_crash(self, config):
        """Token index beyond row count → no crash, no prompt."""
        rows = [{'inv_type': 'cucumbers', 'qty': 4}]
        prompts = check_alias_opportunity(rows, {5: 'taters'}, config)
        assert len(prompts) == 0


# ============================================================
# Helper function edge cases
# ============================================================

class TestHelperEdgeCases:
    """Unit tests for TUI helper functions: eval_qty, parse_date, format_*, etc."""

    def test_eval_qty_empty(self):
        assert eval_qty("") is None

    def test_eval_qty_whitespace(self):
        assert eval_qty("  ") is None

    def test_eval_qty_negative(self):
        """eval_qty accepts negative numbers for manual editing."""
        assert eval_qty("-5") == -5

    def test_eval_qty_very_large(self):
        assert eval_qty("999999999") == 999999999

    def test_eval_qty_zero(self):
        assert eval_qty("0") == 0

    def test_eval_qty_float_whole(self):
        """Whole floats like '4.0' return integer 4."""
        assert eval_qty("4.0") == 4

    def test_eval_qty_float_fraction(self):
        assert eval_qty("0.5") == 0.5

    def test_parse_date_empty(self):
        assert parse_date("") is None

    def test_parse_date_whitespace(self):
        assert parse_date("  ") is None

    def test_parse_date_iso_format(self):
        assert parse_date("2025-03-15") == date(2025, 3, 15)

    def test_parse_date_dot_two_digit_year(self):
        assert parse_date("15.3.25") == date(2025, 3, 15)

    def test_parse_date_dot_four_digit_year(self):
        assert parse_date("15.03.2025") == date(2025, 3, 15)

    def test_parse_date_slash_format(self):
        assert parse_date("3/15/25") == date(2025, 3, 15)

    def test_parse_date_invalid_string(self):
        assert parse_date("not-a-date") is None

    def test_parse_date_invalid_numbers(self):
        assert parse_date("32.13.25") is None


class TestFormatFunctions:
    """Tests for display formatting helpers."""

    def test_format_qty_none(self):
        from inventory_tui import format_qty
        assert format_qty(None) == '???'

    def test_format_qty_int(self):
        from inventory_tui import format_qty
        assert format_qty(4) == '4'

    def test_format_qty_float_whole(self):
        from inventory_tui import format_qty
        assert format_qty(4.0) == '4'

    def test_format_qty_float_fraction(self):
        from inventory_tui import format_qty
        assert format_qty(4.5) == '4.5'

    def test_format_date_none(self):
        from inventory_tui import format_date
        assert format_date(None) == '???'

    def test_format_date_date_object(self):
        from inventory_tui import format_date
        assert format_date(date(2025, 3, 15)) == '2025-03-15'

    def test_format_date_string_passthrough(self):
        from inventory_tui import format_date
        assert format_date("some string") == "some string"


class TestRowWarningDetection:
    """Tests for row_has_warning (⚠ flag detection)."""

    def test_complete_row_no_warning(self):
        from inventory_tui import row_has_warning
        row = {'trans_type': 'eaten', 'vehicle_sub_unit': 'L'}
        assert not row_has_warning(row)

    def test_missing_trans_type_has_warning(self):
        from inventory_tui import row_has_warning
        row = {'trans_type': None, 'vehicle_sub_unit': 'L'}
        assert row_has_warning(row)

    def test_missing_location_has_warning(self):
        from inventory_tui import row_has_warning
        row = {'trans_type': 'eaten', 'vehicle_sub_unit': None}
        assert row_has_warning(row)

    def test_both_missing_has_warning(self):
        from inventory_tui import row_has_warning
        row = {'trans_type': None, 'vehicle_sub_unit': None}
        assert row_has_warning(row)


class TestEmptyRow:
    """Tests for empty_row() structure."""

    def test_empty_row_has_correct_defaults(self):
        from inventory_tui import empty_row
        row = empty_row()
        assert row['inv_type'] == '???'
        assert row['qty'] == 0
        assert row['trans_type'] is None
        assert row['vehicle_sub_unit'] is None
        assert row['batch'] == 1
        assert row['notes'] is None
        assert row['date'] == date.today()


class TestClosedSetOptions:
    """Tests for get_closed_set_options."""

    def test_items_options(self, config):
        from inventory_tui import get_closed_set_options
        opts = get_closed_set_options('inv_type', config)
        assert 'cucumbers' in opts
        assert 'spaghetti' in opts

    def test_trans_type_options(self, config):
        from inventory_tui import get_closed_set_options
        opts = get_closed_set_options('trans_type', config)
        assert 'eaten' in opts
        assert 'warehouse_to_branch' in opts

    def test_location_options_includes_warehouse(self, config):
        from inventory_tui import get_closed_set_options
        opts = get_closed_set_options('vehicle_sub_unit', config)
        assert 'warehouse' in opts
        assert 'L' in opts

    def test_unknown_field_returns_empty(self, config):
        from inventory_tui import get_closed_set_options
        assert get_closed_set_options('nonexistent', config) == []


# ============================================================
# Display edge cases
# ============================================================

class TestDisplayEdgeCases:
    """Tests for display_result with unusual data."""

    def test_empty_everything(self, capsys):
        """No rows, notes, or unparseable → 'Nothing to display'."""
        display_result([], notes=[], unparseable=[])
        output = capsys.readouterr().out
        assert 'Nothing to display' in output

    def test_many_rows(self, capsys):
        """20+ rows display without crash."""
        rows = []
        for i in range(20):
            rows.append({
                'date': TODAY, 'inv_type': 'cucumbers', 'qty': i,
                'trans_type': 'eaten', 'vehicle_sub_unit': 'L',
                'batch': 1, 'notes': None,
            })
        display_result(rows)
        output = capsys.readouterr().out
        assert 'cucumbers' in output


# ============================================================
# Find partner edge cases
# ============================================================

class TestFindPartnerEdgeCases:
    """Tests for partner detection with unusual data."""

    def test_qty_zero_no_partner(self):
        """Rows with qty=0 have no partner (qty*qty can't be < 0)."""
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 0},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 0},
        ]
        assert find_partner(rows, 0) is None

    def test_qty_none_no_partner(self):
        """Row with qty=None has no partner."""
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': None},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34},
        ]
        assert find_partner(rows, 0) is None

    def test_three_rows_correct_partner(self):
        """Three rows in same batch — finds correct partner by item."""
        rows = [
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': -34},
            {'batch': 1, 'inv_type': 'spaghetti', 'qty': 34},
            {'batch': 1, 'inv_type': 'cucumbers', 'qty': -5},
        ]
        assert find_partner(rows, 0) == 1
        assert find_partner(rows, 2) is None  # cucumbers has no partner


# ============================================================
# Review loop: multiple edits
# ============================================================

class TestMultipleEdits:
    """Tests for editing multiple fields before confirm."""

    def test_edit_two_fields_then_confirm(self, config, monkeypatch):
        """Edit qty and notes on same row, then confirm."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input([
            "1q", "10",         # edit qty
            "1n", "test note",  # edit notes
            "c",                # confirm
        ]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)
        assert outcome['rows'][0]['qty'] == 10
        assert outcome['rows'][0]['notes'] == 'test note'

    def test_edit_same_field_twice_overwrites(self, config, monkeypatch):
        """Editing same field twice: second value wins."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input([
            "1q", "10",   # first edit
            "1q", "20",   # overwrite
            "c",
        ]))
        outcome = review_loop(result, "eaten by L\n4 cucumbers", config)
        assert outcome['rows'][0]['qty'] == 20

    def test_edit_then_delete_edited_row(self, config, monkeypatch):
        """Edit a row, then delete it — deleted row is gone."""
        result = parse("eaten by L\n4 cucumbers\n2 spaghetti", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input([
            "1q", "10",  # edit row 1
            "x1",        # delete it
            "c",
        ]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'spaghetti'


# ============================================================
# Review loop: delete edge cases
# ============================================================

class TestDeleteEdgeCases:
    """Tests for row deletion edge cases."""

    def test_delete_all_rows(self, config, monkeypatch):
        """Delete all rows → nothing to display, then quit."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["x1", "q"]))
        outcome = review_loop(result, "...", config)
        assert outcome is None

    def test_delete_row_zero_invalid(self, config, monkeypatch, capsys):
        """Row 0 is invalid (1-indexed) → error message, no deletion."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["x0", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert len(outcome['rows']) == 1  # unchanged

    def test_delete_nonexistent_row(self, config, monkeypatch, capsys):
        """Deleting row 99 → error message, no deletion."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["x99", "c"]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 1  # unchanged

    def test_delete_one_of_double_entry_pair(self, config, monkeypatch):
        """Delete one row of a double-entry pair → orphaned partner remains."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2
        monkeypatch.setattr('builtins.input', make_input(["x1", "c", "y"]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 1


# ============================================================
# Review loop: edit error handling
# ============================================================

class TestEditErrorHandling:
    """Tests for error handling during field editing."""

    def test_edit_nonexistent_row(self, config, monkeypatch, capsys):
        """Editing row 99 → error message."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["99q", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Invalid' in output or 'invalid' in output.lower()

    def test_edit_cancel_preserves_value(self, config, monkeypatch):
        """Start edit, press Enter to cancel → value unchanged."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1q", "", "c"]))
        outcome = review_loop(result, "...", config)
        assert outcome['rows'][0]['qty'] == 4

    def test_edit_qty_invalid_shows_error(self, config, monkeypatch, capsys):
        """Invalid qty expression → error message, value unchanged."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1q", "abc", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Invalid' in output or 'invalid' in output.lower()
        assert outcome['rows'][0]['qty'] == 4

    def test_edit_date_invalid_shows_error(self, config, monkeypatch, capsys):
        """Invalid date → error message, date unchanged."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1d", "xyz", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Invalid' in output or 'invalid' in output.lower()

    def test_edit_batch_invalid_shows_error(self, config, monkeypatch, capsys):
        """Non-numeric batch → error message, value unchanged."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1b", "abc", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Invalid' in output or 'invalid' in output.lower()

    def test_unknown_command_shows_help_hint(self, config, monkeypatch, capsys):
        """Unknown command → error with help hint."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["xyz", "c"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Unknown' in output or 'unknown' in output.lower()

    def test_uppercase_command_works(self, config, monkeypatch):
        """'C' (uppercase) is accepted as confirm."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["C"]))
        outcome = review_loop(result, "...", config)
        assert outcome is not None


# ============================================================
# Review loop: double-entry partner via review loop
# ============================================================

class TestDoubleEntryPartnerIntegration:
    """Integration tests for partner auto-update through the review loop."""

    def test_edit_qty_negates_partner(self, config, monkeypatch):
        """Edit qty on one side → partner gets negated value."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['qty'] == -4  # warehouse side
        assert result.rows[1]['qty'] == 4   # L side
        monkeypatch.setattr('builtins.input', make_input(["2q", "10", "c"]))
        outcome = review_loop(result, "...", config)
        assert outcome['rows'][1]['qty'] == 10
        assert outcome['rows'][0]['qty'] == -10

    def test_edit_location_doesnt_sync_partner(self, config, monkeypatch):
        """Edit location on one row → partner's location unchanged."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        # 1l → location picker: [a]warehouse [b]L [c]C [d]N → select C
        monkeypatch.setattr('builtins.input', make_input(["1l", "c", "c"]))
        outcome = review_loop(result, "...", config)
        assert outcome['rows'][0]['vehicle_sub_unit'] == 'C'
        assert outcome['rows'][1]['vehicle_sub_unit'] == 'L'  # unchanged

    def test_edit_batch_syncs_partner(self, config, monkeypatch):
        """Edit batch on one row → partner's batch matches."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1b", "5", "c"]))
        outcome = review_loop(result, "...", config)
        assert outcome['rows'][0]['batch'] == 5
        assert outcome['rows'][1]['batch'] == 5


# ============================================================
# Review loop: confirm with incomplete rows
# ============================================================

class TestConfirmIncomplete:
    """Tests for the incomplete-row warning on confirm."""

    def test_confirm_incomplete_warns(self, config, monkeypatch, capsys):
        """Confirming a row with trans_type=None shows warning."""
        result = parse("4 cucumbers", config, today=TODAY)  # no verb, no dest
        monkeypatch.setattr('builtins.input', make_input(["c", "y"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'Warning' in output or '???' in output or 'warning' in output.lower()

    def test_decline_warning_returns_to_review(self, config, monkeypatch):
        """Declining the warning returns to the review loop."""
        result = parse("4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["c", "n", "q"]))
        outcome = review_loop(result, "...", config)
        assert outcome is None  # quit after declining


# ============================================================
# Alias learning integration
# ============================================================

class TestAliasLearningIntegration:
    """Integration tests for the alias learning workflow."""

    def test_alias_prompt_on_item_edit(self, config, monkeypatch, capsys):
        """
        Full flow: edit item from unknown to canonical → alias prompt on confirm.

        Stage 1: Parse "4 taters to L" → taters fuzzy-matches to something
                 OR is unknown. Either way, user edits to 'small potatoes'.
        Stage 2: User edits item on row 1 to small potatoes.
        Stage 3: On confirm, alias prompt appears for the original token.
        """
        # Parse something where the item gets assigned via the parse
        result = parse("4 cucumbers to L", config, today=TODAY)
        # Edit item from cucumbers to small potatoes
        # items: [a]cherry tomatoes [b]sweet cherry [c]small potatoes ...
        monkeypatch.setattr('builtins.input', make_input([
            "1i", "c",   # edit item → small potatoes (3rd option)
            "c",         # confirm
            "n",         # decline alias (cucumbers→small potatoes is canonical→canonical)
        ]))
        outcome = review_loop(result, "4 cucumbers to L", config)
        # The key thing: no crash, flow completes
        assert outcome is not None


# ============================================================
# State machine completeness tests
# ============================================================

class TestStateMachineCompleteness:
    """Tests verifying the review loop handles all state combinations.

    The review loop has implicit states based on (rows, notes, unparseable).
    These tests ensure every valid combination is handled with appropriate
    commands and user feedback.

    Tests marked xfail(strict=True) document known gaps. When a gap is
    fixed, the test starts passing and pytest flags it as XPASS (error),
    forcing the developer to remove the marker.
    """

    # --- Gap: Missing state for notes + unparseable without rows ---

    @pytest.mark.xfail(strict=True,
                        reason="No state for notes+unparseable; falls to NORMAL_REVIEW where save-note is unavailable")
    def test_notes_and_unparseable_can_save_note(self, config, monkeypatch):
        """With notes + unparseable but no rows, saving as note should work.

        Currently: notes+unparseable falls through to NORMAL_REVIEW,
        where 'n' (save note) is not a recognized command → EOFError.
        Expected: a combined state that offers save-note + edit + skip.
        """
        result = ParseResult(rows=[], notes=["hello world"], unparseable=["4 xyz"])
        monkeypatch.setattr('builtins.input', make_input(["n"]))
        outcome = review_loop(result, "4 xyz\nhello world", config)
        assert outcome is not None
        assert len(outcome['notes']) >= 1

    @pytest.mark.xfail(strict=True,
                        reason="No state for notes+unparseable; shows review_prompt with [c]onfirm")
    def test_notes_and_unparseable_shows_appropriate_prompt(self, config, monkeypatch, capsys):
        """Should show note-save/edit/skip options, not the full review prompt.

        Currently: falls to NORMAL_REVIEW which shows
        '[c]onfirm / edit (e.g. 1i) / [r]etry / [q]uit'.
        Expected: prompt appropriate for no-rows state (like notes_only_prompt).
        """
        result = ParseResult(rows=[], notes=["hello world"], unparseable=["4 xyz"])
        monkeypatch.setattr('builtins.input', make_input(["q"]))
        review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert '[c]onfirm' not in output

    # --- Gap: Unknown commands silently ignored in non-NORMAL states ---

    @pytest.mark.xfail(strict=True,
                        reason="Unknown commands silently ignored in UNPARSEABLE_ONLY state")
    def test_unknown_command_in_unparseable_gives_feedback(self, config, monkeypatch, capsys):
        """Typing gibberish in unparseable state should show error message.

        Currently: unrecognized input hits a bare 'continue' with no output.
        Expected: error message like 'Unknown command'.
        """
        result = ParseResult(rows=[], notes=[], unparseable=["4 xyz"])
        monkeypatch.setattr('builtins.input', make_input(["xyz", "s"]))
        review_loop(result, "4 xyz", config)
        output = capsys.readouterr().out
        assert 'unknown' in output.lower()

    @pytest.mark.xfail(strict=True,
                        reason="Unknown commands silently ignored in NOTES_ONLY state")
    def test_unknown_command_in_notes_only_gives_feedback(self, config, monkeypatch, capsys):
        """Typing gibberish in notes-only state should show error message.

        Currently: unrecognized input hits a bare 'continue' with no output.
        Expected: error message like 'Unknown command'.
        """
        result = ParseResult(rows=[], notes=["hello world"], unparseable=[])
        monkeypatch.setattr('builtins.input', make_input(["xyz", "s"]))
        review_loop(result, "hello world", config)
        output = capsys.readouterr().out
        assert 'unknown' in output.lower()

    # --- Gap: Add row not available in non-NORMAL states ---

    @pytest.mark.xfail(strict=True,
                        reason="'+' (add row) not recognized in UNPARSEABLE_ONLY state")
    def test_add_row_from_unparseable(self, config, monkeypatch):
        """'+' should add a row, transitioning to NORMAL_REVIEW.

        Currently: '+' is unrecognized → silently ignored → EOFError.
        Expected: empty row added, state transitions to NORMAL_REVIEW.
        """
        result = ParseResult(rows=[], notes=[], unparseable=["4 xyz"])
        monkeypatch.setattr('builtins.input', make_input(["+", "c", "y"]))
        outcome = review_loop(result, "4 xyz", config)
        assert outcome is not None
        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == '???'

    @pytest.mark.xfail(strict=True,
                        reason="'+' (add row) not recognized in NOTES_ONLY state")
    def test_add_row_from_notes_only(self, config, monkeypatch):
        """'+' should add a row, transitioning to NORMAL_REVIEW.

        Currently: '+' is unrecognized → silently ignored → EOFError.
        Expected: empty row added, state transitions to NORMAL_REVIEW.
        """
        result = ParseResult(rows=[], notes=["hello world"], unparseable=[])
        monkeypatch.setattr('builtins.input', make_input(["+", "c", "y"]))
        outcome = review_loop(result, "hello world", config)
        assert outcome is not None
        assert len(outcome['rows']) == 1

    # --- Gap: Empty-after-deletion has no dedicated state ---

    @pytest.mark.xfail(strict=True,
                        reason="No EMPTY state; confirm silently returns zero rows after deletion")
    def test_empty_after_deletion_rejects_confirm(self, config, monkeypatch):
        """After deleting all rows, confirm should not return an empty result.

        Currently: falls to NORMAL_REVIEW, 'c' returns {'rows': [], 'notes': []}.
        Expected: either reject 'c', warn, or transition to a retry/quit-only state.
        """
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["x1", "c"]))
        outcome = review_loop(result, "...", config)
        assert outcome is None or len(outcome.get('rows', [])) > 0

    # --- Gap: parse_date DDMMYY inconsistency ---

    @pytest.mark.xfail(strict=True,
                        reason="TUI parse_date doesn't support DDMMYY unlike parser's _extract_date")
    def test_parse_date_ddmmyy(self):
        """parse_date should handle 6-digit DDMMYY (e.g. 150325 → 2025-03-15).

        The parser's _extract_date handles this format, but the TUI's
        parse_date (used for manual date editing) does not. A user who
        types DDMMYY during date editing gets 'Invalid date'.
        """
        assert parse_date("150325") == date(2025, 3, 15)

    # --- Gap: Delete partner without feedback ---

    @pytest.mark.xfail(strict=True,
                        reason="No warning/feedback when deleting half of double-entry pair")
    def test_delete_half_of_pair_warns(self, config, monkeypatch, capsys):
        """Deleting one row of a double-entry pair should warn about the orphan.

        Currently: row is silently deleted, orphaned partner remains with
        no indication that it was part of a pair. Edits auto-update the
        partner, but delete does not.
        Expected: message about partner row, or auto-delete partner.
        """
        result = parse("4 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2  # double-entry pair
        monkeypatch.setattr('builtins.input', make_input(["x1", "c"]))
        review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert ('partner' in output.lower() or 'pair' in output.lower()
                or 'double' in output.lower())
