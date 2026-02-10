"""
Tests for the inventory message parser — Hebrew language.

Full Hebrew test suite: parser tests + TUI tests with Hebrew commands,
field codes, and UI strings from config_he.yaml.
"""

import pytest
from datetime import date

from inventory_parser import parse
from inventory_tui import (
    review_loop, display_result, eval_qty, parse_date,
    find_partner, update_partner, check_alias_opportunity,
    UIStrings,
)


# ============================================================
# Fixtures
# ============================================================

TODAY = date(2025, 3, 19)

# Hebrew UI config — must match config_he.yaml ui section
_HE_UI = {
    'commands': {
        'confirm': 'א',
        'quit': 'ב',
        'retry': 'ע',
        'edit': 'ע',
        'save_note': 'ש',
        'skip': 'ד',
        'delete_prefix': 'ח',
        'add_row': '+',
        'help': '?',
        'yes': 'כ',
        'no': 'ל',
    },
    'field_codes': {
        'ת': 'date',
        'פ': 'inv_type',
        'כ': 'qty',
        'ס': 'trans_type',
        'מ': 'vehicle_sub_unit',
        'ה': 'notes',
        'ק': 'batch',
    },
    'field_display_names': {
        'date': 'תאריך',
        'inv_type': 'פריט',
        'qty': 'כמות',
        'trans_type': 'סוג',
        'vehicle_sub_unit': 'מיקום',
        'notes': 'הערות',
        'batch': 'קבוצה',
    },
    'table_headers': ['#', 'תאריך', 'פריט', 'כמות', 'סוג', 'מיקום', 'קבוצה', 'הערות'],
    'option_letters': 'אבגדהוזחטיכלמנסעפצקרשת',
    'strings': {
        'note_prefix': 'הערה',
        'unparseable_prefix': 'לא ניתן לפרש',
        'review_prompt': '\n[א]ישור / עריכה (לדוגמה 1פ) / [ע]ריכה מחדש / [ב]יטול  (? לעזרה)',
        'notes_only_prompt': '[ש]מור כהערה / [ע]ריכה מחדש / [ד]ילוג  (? לעזרה)',
        'unparseable_prompt': '\n[ע]ריכה מחדש / [ד]ילוג  (? לעזרה)',
        'no_transactions': '\nלא נמצאו עסקאות.',
        'confirm_incomplete_warning': '  אזהרה: שורה/ות {row_list} עם שדות חסרים (???). לאשר בכל זאת? [{yes}/{no}] ',
        'enter_letter_prompt': 'הקש אות (או Enter לביטול)> ',
        'edit_cancelled': '  העריכה בוטלה.',
        'row_deleted': '  שורה {num} נמחקה.',
        'invalid_row': '  מספר שורה לא חוקי.',
        'row_updated': '  שורה {num} {field} \u2192 {value}',
        'unknown_command': '  פקודה לא מוכרת. הקש ? לעזרה, או נסה לדוגמה 1פ לעריכת פריט בשורה 1.',
        'original_text_label': '\nטקסט מקורי:\n{text}\n',
        'enter_corrected_text': 'הקלד טקסט מתוקן (שורה ריקה לסיום):',
        'save_alias_prompt': 'לשמור "{original}" \u2192 "{canonical}" כקיצור? [{yes}/{no}] ',
        'help_commands_header': 'פקודות:',
        'help_field_codes_header': 'קודי שדות:',
        'help_examples_header': 'דוגמאות:',
        'help_confirm_desc': 'אישור ושמירת כל השורות',
        'help_quit_desc': 'ביטול (מחיקת הניתוח)',
        'help_retry_desc': 'עריכת טקסט מקורי וניתוח מחדש',
        'help_edit_desc': 'עריכת שדה (לדוגמה {example})',
        'help_delete_desc': 'מחיקת שורה (לדוגמה {example})',
        'help_add_desc': 'הוספת שורה חדשה',
        'help_help_desc': 'הצגת עזרה זו',
        'help_save_note_desc': 'שמירה כהערה (לשמירת הטקסט)',
        'help_skip_desc': 'דילוג (מחיקת קלט זה)',
        'help_items_header': 'פריטים מוכרים:',
        'help_aliases_header': 'כינויים:',
    },
}


@pytest.fixture
def config():
    """Hebrew test config — matches config_he.yaml."""
    return {
        'items': [
            'עגבניות שרי', 'עגבניות שרי מתוקות', 'תפוחי אדמה קטנים',
            'ספגטי', 'מלפפונים', 'עוף', 'גזר', 'תבניות אלומיניום',
            'פרוט לופס', 'קורנפלקס', 'צ\'יריוס', 'קקאו פאפס', 'טריקס',
        ],
        'aliases': {
            'תפו"א קטנים': 'תפוחי אדמה קטנים',
            'שרי': 'עגבניות שרי',
            'נודלס ספגטי': 'ספגטי',
            'תפודים': 'תפוחי אדמה קטנים',
            'תפוא': 'תפוחי אדמה קטנים',
            'תפוח אדמה': 'תפוחי אדמה קטנים',
            'עגבניה': 'עגבניות שרי',
            'עגבניות': 'עגבניות שרי',
        },
        'locations': ['ל', 'כ', 'נ'],
        'default_source': 'מחסן',
        'transaction_types': [
            'נקודת_התחלה', 'ספירה_חוזרת', 'מחסן_לסניף',
            'ספק_למחסן', 'נאכל', 'בין_סניפים',
            'בין_מחסנים', 'בתוך_סניף',
        ],
        'action_verbs': {
            'מחסן_לסניף': ['העביר', 'העבירו', 'עבר', 'עברו', 'נתן', 'שלח'],
            'ספק_למחסן': ['קיבל', 'קיבלו', 'קיבלנו', 'הגיע'],
            'נאכל': ['נאכל', 'נאכלו', 'אכל', 'אכלו', 'צרך', 'השתמש'],
        },
        'unit_conversions': {
            'עגבניות שרי': {'base_unit': 'יחידה', 'קופסה קטנה': 990, 'קופסה': 1980},
            'עגבניות שרי מתוקות': {'base_unit': 'יחידה', 'קופסה קטנה': 990, 'קופסה': 1980},
            'תפוחי אדמה קטנים': {'base_unit': 'יחידה', 'קופסה': 920},
        },
        'prepositions': {
            'to': ['ל'],
            'by': ['ב'],
            'from': ['מ'],
        },
        'from_words': ['מאת'],
        'filler_words': [],
        'non_zero_sum_types': ['נאכל', 'נקודת_התחלה', 'ספירה_חוזרת', 'ספק_למחסן'],
        'default_transfer_type': 'מחסן_לסניף',
        'ui': _HE_UI,
    }


def make_input(responses):
    """Create a mock input() that returns responses in sequence."""
    it = iter(responses)
    def mock_input(prompt=''):
        if prompt:
            print(prompt, end='')
        try:
            return next(it)
        except StopIteration:
            raise EOFError("No more mock inputs")
    return mock_input


# ============================================================
# Parser tests
# ============================================================

def test_simple_consumption(config):
    """Hebrew verb + location + date + container conversion + non-zero-sum."""
    result = parse(
        "נאכל ב-ל 15.3.25\n"
        "2 קופסה קטנה עגבניות שרי\n"
        "4 מלפפונים",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2
    assert result.notes == []
    assert result.unparseable == []

    assert result.rows[0]['date'] == date(2025, 3, 15)
    assert result.rows[0]['inv_type'] == 'עגבניות שרי'
    assert result.rows[0]['qty'] == 1980  # 2 × 990
    assert result.rows[0]['trans_type'] == 'נאכל'
    assert result.rows[0]['vehicle_sub_unit'] == 'ל'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'מלפפונים'
    assert result.rows[1]['qty'] == 4
    assert result.rows[1]['trans_type'] == 'נאכל'
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'


def test_transfer_with_math(config):
    """Hebrew verb + math expression + alias + double-entry."""
    result = parse(
        "העבירו 2x17 נודלס ספגטי ל-ל",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2

    assert result.rows[0]['inv_type'] == 'ספגטי'
    assert result.rows[0]['qty'] == -34
    assert result.rows[0]['trans_type'] == 'מחסן_לסניף'
    assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'ספגטי'
    assert result.rows[1]['qty'] == 34
    assert result.rows[1]['trans_type'] == 'מחסן_לסניף'
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'


def test_multiple_destinations(config):
    """Hebrew alias + different destinations + container conversion + batches."""
    result = parse(
        '8 קופסה תפו"א קטנים ל-כ\n'
        '7 קופסה תפוחי אדמה קטנים ל-ל',
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4

    assert result.rows[0]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[0]['qty'] == -7360
    assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['qty'] == 7360
    assert result.rows[1]['vehicle_sub_unit'] == 'כ'
    assert result.rows[1]['batch'] == 1

    assert result.rows[2]['qty'] == -6440
    assert result.rows[2]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[2]['batch'] == 2

    assert result.rows[3]['qty'] == 6440
    assert result.rows[3]['vehicle_sub_unit'] == 'ל'
    assert result.rows[3]['batch'] == 2


def test_unparseable_numbers(config):
    """Numbers without item names → unparseable."""
    result = parse("4 82 95 3 1", config, today=TODAY)
    assert len(result.rows) == 0
    assert len(result.unparseable) > 0


def test_communication_note(config):
    """No quantity, no known item → classified as note."""
    result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
    assert len(result.rows) == 0
    assert len(result.notes) == 1
    assert 'רימון' in result.notes[0]


def test_destination_changes_mid_list(config):
    """Forward broadcasting, batch change on destination change."""
    result = parse(
        "3 מלפפונים ל-ל\n"
        "2 ספגטי\n"
        "5 עגבניות שרי ל-כ\n"
        "1 תפוחי אדמה קטנים",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 8

    assert result.rows[0]['inv_type'] == 'מלפפונים'
    assert result.rows[0]['qty'] == -3
    assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[1]['qty'] == 3
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'
    assert result.rows[1]['batch'] == 1

    assert result.rows[2]['inv_type'] == 'ספגטי'
    assert result.rows[3]['vehicle_sub_unit'] == 'ל'
    assert result.rows[3]['batch'] == 1

    assert result.rows[4]['inv_type'] == 'עגבניות שרי'
    assert result.rows[5]['vehicle_sub_unit'] == 'כ'
    assert result.rows[5]['batch'] == 2

    assert result.rows[6]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[7]['vehicle_sub_unit'] == 'כ'
    assert result.rows[7]['batch'] == 2


def test_no_context_list(config):
    """No header — no date, no destination, no action verb."""
    result = parse(
        "4 פרוט לופס\n"
        "189 קורנפלקס\n"
        "3 קקאו פאפס\n"
        "1 טריקס",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4
    expected = [
        ('פרוט לופס', 4),
        ('קורנפלקס', 189),
        ('קקאו פאפס', 3),
        ('טריקס', 1),
    ]
    for row, (item, qty) in zip(result.rows, expected):
        assert row['inv_type'] == item
        assert row['qty'] == qty
        assert row['trans_type'] is None
        assert row['vehicle_sub_unit'] is None
        assert row['date'] == TODAY
        assert row['batch'] == 1


def test_multi_date_consumption(config):
    """Same location, different dates → separate batches."""
    result = parse(
        "נאכל ב-ל 15.3.25\n"
        "2 קופסה קטנה עגבניות שרי\n"
        "4 מלפפונים\n"
        "\n"
        "נאכלו ב-ל 16.3.25\n"
        "1980 עגבניות שרי\n"
        "4 מלפפונים",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4

    assert result.rows[0]['date'] == date(2025, 3, 15)
    assert result.rows[0]['inv_type'] == 'עגבניות שרי'
    assert result.rows[0]['qty'] == 1980
    assert result.rows[0]['trans_type'] == 'נאכל'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'מלפפונים'
    assert result.rows[1]['qty'] == 4
    assert result.rows[1]['batch'] == 1

    assert result.rows[2]['date'] == date(2025, 3, 16)
    assert result.rows[2]['inv_type'] == 'עגבניות שרי'
    assert result.rows[2]['qty'] == 1980
    assert result.rows[2]['batch'] == 2

    assert result.rows[3]['inv_type'] == 'מלפפונים'
    assert result.rows[3]['qty'] == 4
    assert result.rows[3]['batch'] == 2


def test_no_separator_location(config):
    """לל (no separator between prep and location) should parse."""
    result = parse("3 מלפפונים לל", config, today=TODAY)
    assert len(result.rows) == 2
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'
    assert result.rows[1]['qty'] == 3


def test_mixed_parse_context_alias_unparseable(config, capsys):
    """Alias, unmatched item, qty-less alias, and DDMMYY context line."""
    result = parse(
        "3 תפוח אדמה\n"
        "2 תפוז\n"
        "עגבניה\n"
        "לכ 150226",
        config,
        today=TODAY,
    )

    # תפוח אדמה → תפוחי אדמה קטנים (alias), double-entry to כ
    assert result.rows[0]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[0]['qty'] == -3
    assert result.rows[1]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[1]['qty'] == 3
    assert result.rows[1]['vehicle_sub_unit'] == 'כ'
    assert result.rows[1]['date'] == date(2026, 2, 15)

    # עגבניה → עגבניות שרי (alias), qty defaults to 1
    assert result.rows[2]['inv_type'] == 'עגבניות שרי'
    assert result.rows[2]['qty'] == -1
    assert result.rows[3]['inv_type'] == 'עגבניות שרי'
    assert result.rows[3]['qty'] == 1
    assert result.rows[3]['vehicle_sub_unit'] == 'כ'
    assert result.rows[3]['date'] == date(2026, 2, 15)

    # לכ 150226 is a context line, not unparseable
    assert 'לכ 150226' not in result.unparseable

    # 2 תפוז should be unparseable (short token, high cutoff)
    assert '2 תפוז' in result.unparseable

    # Display should show known items hint after unparseable warning
    ui = UIStrings(config)
    display_result(result.rows, unparseable=result.unparseable, ui=ui)
    output = capsys.readouterr().out
    assert 'לא ניתן לפרש' in output
    assert 'תפוז' in output
    assert 'פריטים מוכרים:' in output


# ============================================================
# Double-entry partner detection (Hebrew items)
# ============================================================

class TestFindPartnerHe:
    def test_finds_partner(self):
        rows = [
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': -34},
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': 34},
        ]
        assert find_partner(rows, 0) == 1
        assert find_partner(rows, 1) == 0

    def test_no_partner_different_batch(self):
        rows = [
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': -34},
            {'batch': 2, 'inv_type': 'ספגטי', 'qty': 34},
        ]
        assert find_partner(rows, 0) is None

    def test_no_partner_single_row(self):
        rows = [{'batch': 1, 'inv_type': 'מלפפונים', 'qty': 4}]
        assert find_partner(rows, 0) is None


class TestUpdatePartnerHe:
    def test_item_update_syncs(self):
        rows = [
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': -34},
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': 34},
        ]
        update_partner(rows, 0, 'inv_type', 'עגבניות שרי')
        assert rows[1]['inv_type'] == 'עגבניות שרי'

    def test_qty_update_negates(self):
        rows = [
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': -34},
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': 34},
        ]
        update_partner(rows, 0, 'qty', -50)
        assert rows[1]['qty'] == 50

    def test_location_not_synced(self):
        rows = [
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': -34, 'vehicle_sub_unit': 'מחסן'},
            {'batch': 1, 'inv_type': 'ספגטי', 'qty': 34, 'vehicle_sub_unit': 'ל'},
        ]
        update_partner(rows, 0, 'vehicle_sub_unit', 'כ')
        assert rows[1]['vehicle_sub_unit'] == 'ל'  # unchanged


# ============================================================
# Display tests (Hebrew UI)
# ============================================================

class TestDisplayHe:
    def test_shows_hebrew_headers(self, config, capsys):
        result = parse("העבירו 2x17 נודלס ספגטי ל-ל", config, today=TODAY)
        ui = UIStrings(config)
        display_result(result.rows, ui=ui)
        output = capsys.readouterr().out
        assert 'פריט' in output
        assert 'כמות' in output
        assert 'מיקום' in output
        assert 'סוג' in output

    def test_shows_hebrew_notes(self, config, capsys):
        ui = UIStrings(config)
        display_result([], notes=["רימון ל-נ דרך נאור בטלפון"], ui=ui)
        output = capsys.readouterr().out
        assert 'הערה' in output
        assert 'רימון' in output

    def test_shows_hebrew_unparseable(self, config, capsys):
        ui = UIStrings(config)
        display_result([], unparseable=["4 82 95 3 1"], ui=ui)
        output = capsys.readouterr().out
        assert 'לא ניתן לפרש' in output
        assert '4 82 95 3 1' in output

    def test_warning_flag_on_missing_fields(self, config, capsys):
        ui = UIStrings(config)
        rows = [{
            'date': TODAY, 'inv_type': 'מלפפונים', 'qty': 4,
            'trans_type': None, 'vehicle_sub_unit': None,
            'batch': 1, 'notes': None,
        }]
        display_result(rows, ui=ui)
        output = capsys.readouterr().out
        assert '\u26a0' in output
        assert '???' in output


# ============================================================
# Review loop: confirm and quit (Hebrew commands)
# ============================================================

class TestReviewConfirmQuitHe:
    def test_confirm_returns_rows(self, config, monkeypatch):
        """א confirms and returns parsed rows."""
        result = parse("נאכל ב-ל 15.3.25\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["א"]))
        outcome = review_loop(result, "נאכל ב-ל 15.3.25\n4 מלפפונים", config)

        assert outcome is not None
        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'מלפפונים'
        assert outcome['rows'][0]['qty'] == 4
        assert outcome['rows'][0]['trans_type'] == 'נאכל'
        assert outcome['rows'][0]['vehicle_sub_unit'] == 'ל'

    def test_quit_returns_none(self, config, monkeypatch):
        """ב quits and returns None."""
        result = parse("4 מלפפונים ל-ל", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["ב"]))
        outcome = review_loop(result, "4 מלפפונים ל-ל", config)
        assert outcome is None

    def test_confirm_preserves_notes(self, config, monkeypatch):
        """א with transactions + note → both preserved."""
        text = "4 מלפפונים ל-ל\nרימון ל-נ דרך נאור בטלפון"
        result = parse(text, config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["א"]))
        outcome = review_loop(result, text, config)

        assert len(outcome['rows']) == 2  # double-entry
        assert len(outcome['notes']) >= 1


# ============================================================
# Review loop: field editing (Hebrew field codes)
# ============================================================

class TestReviewEditingHe:
    def test_edit_trans_type(self, config, monkeypatch):
        """1ס → trans_type picker, ה → select נאכל (5th), א → confirm.

        transaction_types: [א]נקודת_התחלה [ב]ספירה_חוזרת [ג]מחסן_לסניף
          [ד]ספק_למחסן [ה]נאכל ...
        """
        result = parse("4 מלפפונים ל-ל", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1ס", "ה", "א"]))
        outcome = review_loop(result, "4 מלפפונים ל-ל", config)

        assert outcome['rows'][0]['trans_type'] == 'נאכל'
        assert outcome['rows'][1]['trans_type'] == 'נאכל'

    def test_edit_qty_with_math(self, config, monkeypatch):
        """1כ → qty prompt, 2x17 → qty becomes 34, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1כ", "2x17", "א"]))
        outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)
        assert outcome['rows'][0]['qty'] == 34

    def test_edit_date(self, config, monkeypatch):
        """1ת → date prompt, 25.12.25 → date set, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1ת", "25.12.25", "א"]))
        outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)
        assert outcome['rows'][0]['date'] == date(2025, 12, 25)

    def test_edit_item_updates_partner(self, config, monkeypatch):
        """1פ → item picker, א → select עגבניות שרי (1st), א → confirm.

        items: [א]עגבניות שרי [ב]עגבניות שרי מתוקות [ג]תפוחי אדמה קטנים
          [ד]ספגטי [ה]מלפפונים ...
        """
        result = parse("העבירו 4 ספגטי ל-ל", config, today=TODAY)
        assert len(result.rows) == 2
        monkeypatch.setattr('builtins.input', make_input(["1פ", "א", "א"]))
        outcome = review_loop(result, "העבירו 4 ספגטי ל-ל", config)

        assert outcome['rows'][0]['inv_type'] == 'עגבניות שרי'
        assert outcome['rows'][1]['inv_type'] == 'עגבניות שרי'

    def test_edit_notes(self, config, monkeypatch):
        """1ה → notes prompt, free text, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1ה", "משלוח מיוחד", "א"]))
        outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)
        assert outcome['rows'][0]['notes'] == 'משלוח מיוחד'

    def test_edit_batch(self, config, monkeypatch):
        """1ק → batch prompt, number, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["1ק", "5", "א"]))
        outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)
        assert outcome['rows'][0]['batch'] == 5


# ============================================================
# Review loop: row operations (Hebrew commands)
# ============================================================

class TestReviewRowOpsHe:
    def test_delete_row(self, config, monkeypatch):
        """ח1 → delete row 1, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים\n2 ספגטי", config, today=TODAY)
        assert len(result.rows) == 2
        monkeypatch.setattr('builtins.input', make_input(["ח1", "א"]))
        outcome = review_loop(result, "...", config)

        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'ספגטי'

    def test_add_row(self, config, monkeypatch):
        """+ → add row, א → incomplete warning, כ → confirm anyway."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["+", "א", "כ"]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 2
        assert outcome['rows'][1]['inv_type'] == '???'


# ============================================================
# Review loop: edit and retry (Hebrew commands)
# ============================================================

class TestEditRetryHe:
    def test_retry_from_unparseable(self, config, monkeypatch):
        """ע → edit line 1, corrected text, א → confirm."""
        result = parse("4 82 95 3 1", config, today=TODAY)
        assert len(result.rows) == 0
        assert len(result.unparseable) > 0

        monkeypatch.setattr('builtins.input', make_input([
            "ע",                       # edit (unparseable context)
            "1",                       # edit line 1
            "4 מלפפונים ל-ל",           # replacement text
            "",                        # finish editing (re-parse)
            "א",                       # confirm
        ]))
        outcome = review_loop(result, "4 82 95 3 1", config)

        assert outcome is not None
        assert len(outcome['rows']) == 2
        assert outcome['rows'][1]['inv_type'] == 'מלפפונים'
        assert outcome['rows'][1]['vehicle_sub_unit'] == 'ל'

    def test_skip_unparseable(self, config, monkeypatch):
        """ד → skip."""
        result = parse("4 82 95 3 1", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["ד"]))
        outcome = review_loop(result, "4 82 95 3 1", config)
        assert outcome is None

    def test_retry_from_normal_review(self, config, monkeypatch):
        """ע → edit lines in normal review, א → confirm."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input([
            "ע",                            # retry
            "1",                            # edit line 1
            "העבירו 2x17 ספגטי ל-ל",         # replacement
            "2",                            # edit line 2
            "",                             # delete it
            "",                             # finish editing (re-parse)
            "א",                            # confirm
        ]))
        outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)

        assert len(outcome['rows']) == 2
        assert outcome['rows'][0]['inv_type'] == 'ספגטי'
        assert outcome['rows'][0]['qty'] == -34


# ============================================================
# Review loop: note handling (Hebrew commands)
# ============================================================

class TestNoteHandlingHe:
    def test_note_save(self, config, monkeypatch):
        """ש → save as note."""
        result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
        assert len(result.notes) >= 1
        monkeypatch.setattr('builtins.input', make_input(["ש"]))
        outcome = review_loop(result, "רימון ל-נ דרך נאור בטלפון", config)

        assert outcome is not None
        assert len(outcome['notes']) >= 1
        assert 'רימון' in outcome['notes'][0]

    def test_note_skip(self, config, monkeypatch):
        """ד → skip note."""
        result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["ד"]))
        outcome = review_loop(result, "רימון ל-נ דרך נאור בטלפון", config)
        assert outcome is None

    def test_note_retry(self, config, monkeypatch):
        """ע → edit line from note context, corrected text, א → confirm."""
        result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
        assert len(result.notes) >= 1
        monkeypatch.setattr('builtins.input', make_input([
            "ע",                    # edit
            "1",                    # edit line 1
            "4 מלפפונים ל-ל",        # replacement text
            "",                     # finish editing (re-parse)
            "א",                    # confirm
        ]))
        outcome = review_loop(result, "רימון ל-נ דרך נאור בטלפון", config)

        assert outcome is not None
        assert len(outcome['rows']) == 2
        assert outcome['rows'][1]['inv_type'] == 'מלפפונים'


# ============================================================
# Alias learning (Hebrew items)
# ============================================================

class TestAliasLearningHe:
    def test_detects_alias_opportunity(self, config):
        """Unknown token edited to canonical → alias opportunity."""
        rows = [{'inv_type': 'תפוחי אדמה קטנים', 'qty': 4}]
        original_tokens = {0: 'תפודי'}
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 1
        assert prompts[0] == ('תפודי', 'תפוחי אדמה קטנים')

    def test_no_opportunity_for_canonical(self, config):
        """Canonical item edited to another canonical → no alias prompt."""
        rows = [{'inv_type': 'תפוחי אדמה קטנים', 'qty': 4}]
        original_tokens = {0: 'מלפפונים'}
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 0

    def test_no_opportunity_for_known_alias(self, config):
        """Known alias → no redundant alias prompt."""
        rows = [{'inv_type': 'תפוחי אדמה קטנים', 'qty': 4}]
        original_tokens = {0: 'תפודים'}  # already in aliases
        prompts = check_alias_opportunity(rows, original_tokens, config)
        assert len(prompts) == 0


# ============================================================
# Help text tests
# ============================================================

class TestHelpTextHe:
    def test_help_shows_hebrew_commands(self, config):
        """Help text contains Hebrew command letters."""
        ui = UIStrings(config)
        assert 'א' in ui.help_text
        assert 'ב' in ui.help_text
        assert 'ע' in ui.help_text
        assert 'פקודות:' in ui.help_text

    def test_help_shows_hebrew_field_codes(self, config):
        """Help text contains Hebrew field code descriptions."""
        ui = UIStrings(config)
        assert 'ת = תאריך' in ui.help_text
        assert 'פ = פריט' in ui.help_text
        assert 'כ = כמות' in ui.help_text

    def test_help_notes_hebrew(self, config):
        """Notes help uses Hebrew."""
        ui = UIStrings(config)
        assert 'ש' in ui.help_text_notes
        assert 'ע' in ui.help_text_notes
        assert 'ד' in ui.help_text_notes

    def test_help_unparseable_hebrew(self, config):
        """Unparseable help uses Hebrew."""
        ui = UIStrings(config)
        assert 'ע' in ui.help_text_unparseable
        assert 'ד' in ui.help_text_unparseable


# ============================================================
# Edge cases: Hebrew field codes and commands
# ============================================================

class TestEdgeCasesHe:
    def test_hebrew_field_code_regex(self, config, monkeypatch):
        """1פ works as Hebrew field edit command."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        # 1פ → item picker, א → select first (עגבניות שרי), א → confirm
        monkeypatch.setattr('builtins.input', make_input(["1פ", "א", "א"]))
        outcome = review_loop(result, "...", config)
        assert outcome['rows'][0]['inv_type'] == 'עגבניות שרי'

    def test_hebrew_delete_prefix_regex(self, config, monkeypatch):
        """ח1 works as Hebrew delete command."""
        result = parse("נאכל ב-ל\n4 מלפפונים\n2 ספגטי", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["ח2", "א"]))
        outcome = review_loop(result, "...", config)
        assert len(outcome['rows']) == 1
        assert outcome['rows'][0]['inv_type'] == 'מלפפונים'

    def test_option_picker_hebrew_letters(self, config, monkeypatch):
        """Closed-set picker uses Hebrew option letters."""
        result = parse("4 מלפפונים ל-ל", config, today=TODAY)
        # 1מ → location picker
        # Options: [א]מחסן [ב]ל [ג]כ [ד]נ
        # ג → select כ
        monkeypatch.setattr('builtins.input', make_input(["1מ", "ג", "א"]))
        outcome = review_loop(result, "4 מלפפונים ל-ל", config)
        assert outcome['rows'][0]['vehicle_sub_unit'] == 'כ'

    def test_edit_cancel_hebrew(self, config, monkeypatch, capsys):
        """Empty Enter on edit prompt → cancel with Hebrew message."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        # 1כ → qty prompt, Enter (empty) → cancel, א → confirm
        monkeypatch.setattr('builtins.input', make_input(["1כ", "", "א"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'העריכה בוטלה' in output
        assert outcome['rows'][0]['qty'] == 4  # unchanged

    def test_unknown_command_hebrew(self, config, monkeypatch, capsys):
        """Unknown command shows Hebrew error."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        monkeypatch.setattr('builtins.input', make_input(["xyz", "א"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'פקודה לא מוכרת' in output

    def test_confirm_incomplete_warning_hebrew(self, config, monkeypatch, capsys):
        """Incomplete row warning uses Hebrew with כ/ל."""
        result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
        # + → add row, א → confirm, כ → yes on warning
        monkeypatch.setattr('builtins.input', make_input(["+", "א", "כ"]))
        outcome = review_loop(result, "...", config)
        output = capsys.readouterr().out
        assert 'אזהרה' in output
        assert len(outcome['rows']) == 2


# ============================================================
# Hebrew preposition + location edge cases
# ============================================================

class TestHebrewPrepositionLocation:
    """Tests for Hebrew prefixed prepositions ל (to) and מ (from)
    attached directly to location codes."""

    def test_standalone_location_header(self, config):
        """לכ on its own line broadcasts location to subsequent items."""
        result = parse(
            "לכ\n"
            "12 עגבניה\n"
            "6 מלפפון",
            config,
            today=TODAY,
        )

        # No notes or unparseable — לכ is a context-setting line
        assert result.notes == []
        assert result.unparseable == []

        # 2 items × double-entry = 4 rows
        assert len(result.rows) == 4

        # Item 1: עגבניה → עגבניות שרי (alias), qty=12, to כ
        assert result.rows[0]['inv_type'] == 'עגבניות שרי'
        assert result.rows[0]['qty'] == -12
        assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 12
        assert result.rows[1]['vehicle_sub_unit'] == 'כ'

        # Item 2: מלפפון → מלפפונים (fuzzy), qty=6, to כ
        assert result.rows[2]['inv_type'] == 'מלפפונים'
        assert result.rows[2]['qty'] == -6
        assert result.rows[3]['qty'] == 6
        assert result.rows[3]['vehicle_sub_unit'] == 'כ'

    def test_standalone_location_lamed(self, config):
        """לל — standalone location ל (both preposition and location name)."""
        result = parse(
            "לל\n"
            "4 מלפפונים",
            config,
            today=TODAY,
        )

        assert result.notes == []
        assert result.unparseable == []
        assert len(result.rows) == 2
        assert result.rows[1]['vehicle_sub_unit'] == 'ל'

    def test_from_prefix_basic(self, config):
        """מכ — from כ, double-entry reversed (stock leaves כ, arrives at מחסן)."""
        result = parse("12 מלפפונים מכ", config, today=TODAY)

        assert len(result.rows) == 2
        # "from כ" → negative at כ, positive at מחסן
        assert result.rows[0]['qty'] == -12
        assert result.rows[0]['vehicle_sub_unit'] == 'כ'
        assert result.rows[1]['qty'] == 12
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'

    def test_from_prefix_to_lamed(self, config):
        """מל — from ל (preposition מ + location ל)."""
        result = parse("6 ספגטי מל", config, today=TODAY)

        assert len(result.rows) == 2
        # "from ל" → negative at ל, positive at מחסן
        assert result.rows[0]['qty'] == -6
        assert result.rows[0]['vehicle_sub_unit'] == 'ל'
        assert result.rows[1]['qty'] == 6
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'

    def test_from_prefix_with_hyphen(self, config):
        """מ-כ — from כ with hyphen separator."""
        result = parse("8 ספגטי מ-כ", config, today=TODAY)

        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'כ'
        assert result.rows[0]['qty'] == -8
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 8

    def test_from_header_broadcasts(self, config):
        """מכ on its own line broadcasts 'from כ' to subsequent items."""
        result = parse(
            "מכ\n"
            "10 מלפפונים\n"
            "5 ספגטי",
            config,
            today=TODAY,
        )

        assert result.notes == []
        assert result.unparseable == []
        assert len(result.rows) == 4

        # Both items should have "from כ" direction
        assert result.rows[0]['vehicle_sub_unit'] == 'כ'
        assert result.rows[0]['qty'] == -10
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 10

        assert result.rows[2]['vehicle_sub_unit'] == 'כ'
        assert result.rows[2]['qty'] == -5
        assert result.rows[3]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[3]['qty'] == 5

    def test_to_and_from_same_message(self, config):
        """Mixed to/from in same message: different directions."""
        result = parse(
            "12 מלפפונים לכ\n"
            "6 ספגטי מנ",
            config,
            today=TODAY,
        )

        assert len(result.rows) == 4

        # "to כ": -qty at מחסן, +qty at כ
        assert result.rows[0]['qty'] == -12
        assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 12
        assert result.rows[1]['vehicle_sub_unit'] == 'כ'

        # "from נ": -qty at נ, +qty at מחסן
        assert result.rows[2]['qty'] == -6
        assert result.rows[2]['vehicle_sub_unit'] == 'נ'
        assert result.rows[3]['qty'] == 6
        assert result.rows[3]['vehicle_sub_unit'] == 'מחסן'

    def test_mem_preposition_doesnt_match_item_names(self, config):
        """מלפפונים should NOT be parsed as מ + ל (from ל) + leftover.

        The regex requires word boundary after the location, so
        מלפפונים (where ל is followed by פפונים, not whitespace) is safe.
        """
        result = parse("12 מלפפונים", config, today=TODAY)

        # No location extracted — just a plain item
        assert len(result.rows) == 1
        assert result.rows[0]['inv_type'] == 'מלפפונים'
        assert result.rows[0]['qty'] == 12
        assert result.rows[0]['vehicle_sub_unit'] is None

    def test_mem_as_location(self):
        """Edge case: מ is both a preposition (from) and a location name.

        With locations [ל, כ, נ, מ]:
        - למ = to מ
        - ממ = from מ
        - מל = from ל (not ambiguous: מ is preposition, ל is location)
        """
        config_with_mem = {
            'items': ['מלפפונים', 'ספגטי'],
            'aliases': {},
            'locations': ['ל', 'כ', 'נ', 'מ'],
            'default_source': 'מחסן',
            'transaction_types': ['מחסן_לסניף'],
            'action_verbs': {},
            'unit_conversions': {},
            'prepositions': {
                'to': ['ל'],
                'by': ['ב'],
                'from': ['מ'],
            },
            'from_words': ['מאת'],
            'filler_words': [],
            'non_zero_sum_types': [],
            'default_transfer_type': 'מחסן_לסניף',
        }

        # למ = "to מ"
        result = parse("12 ספגטי למ", config_with_mem, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[0]['qty'] == -12
        assert result.rows[1]['vehicle_sub_unit'] == 'מ'
        assert result.rows[1]['qty'] == 12

        # ממ = "from מ"
        result = parse("6 ספגטי ממ", config_with_mem, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'מ'
        assert result.rows[0]['qty'] == -6
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 6

        # מל = "from ל" (not: location מ + stray ל)
        result = parse("8 ספגטי מל", config_with_mem, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'ל'
        assert result.rows[0]['qty'] == -8
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 8

    def test_lamed_as_location_and_preposition(self):
        """Edge case: ל is both a preposition (to) and a location name.

        - לל = "to ל"
        - מל = "from ל" (when מ is configured as from preposition)
        - Neither confused with item names.
        """
        config_lamed = {
            'items': ['מלפפונים'],
            'aliases': {},
            'locations': ['ל', 'כ'],
            'default_source': 'מחסן',
            'transaction_types': ['מחסן_לסניף'],
            'action_verbs': {},
            'unit_conversions': {},
            'prepositions': {
                'to': ['ל'],
                'from': ['מ'],
            },
            'from_words': ['מאת'],
            'filler_words': [],
            'non_zero_sum_types': [],
            'default_transfer_type': 'מחסן_לסניף',
        }

        # לל = "to ל"
        result = parse("4 מלפפונים לל", config_lamed, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[0]['qty'] == -4
        assert result.rows[1]['vehicle_sub_unit'] == 'ל'
        assert result.rows[1]['qty'] == 4

        # מל = "from ל"
        result = parse("4 מלפפונים מל", config_lamed, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'ל'
        assert result.rows[0]['qty'] == -4
        assert result.rows[1]['vehicle_sub_unit'] == 'מחסן'
        assert result.rows[1]['qty'] == 4
