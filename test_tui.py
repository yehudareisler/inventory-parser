"""Tests for the inventory TUI — multi-stage interaction tests.

These tests verify the interactive review/edit workflow by mocking
user input (via monkeypatch on builtins.input) and checking returned
values and printed output (via capsys) at each stage.

Each test simulates a complete user interaction:
  parse → display → user commands → verify outcome
"""

import pytest
from datetime import date

from inventory_parser import parse
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
