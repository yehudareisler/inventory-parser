"""
Tests for the inventory message parser — Hebrew language.

These tests mirror the English test_parser.py structure, using Hebrew
item names, verbs, locations, and container names from config_he.yaml.
"""

import pytest
from datetime import date

from inventory_parser import parse
from inventory_tui import review_loop


# ============================================================
# Fixtures
# ============================================================

TODAY = date(2025, 3, 19)


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
        },
        'from_words': ['מאת'],
        'filler_words': [],
        'non_zero_sum_types': ['נאכל', 'נקודת_התחלה', 'ספירה_חוזרת', 'ספק_למחסן'],
        'default_transfer_type': 'מחסן_לסניף',
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
# Parser tests
# ============================================================

def test_simple_consumption(config):
    """
    נאכל ב-ל 15.3.25
    2 קופסה קטנה עגבניות שרי
    4 מלפפונים

    Exercises: Hebrew verb, location, date, container conversion, non-zero-sum.
    """
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
    assert result.rows[0]['qty'] == 1980  # 2 קופסה קטנה × 990
    assert result.rows[0]['trans_type'] == 'נאכל'
    assert result.rows[0]['vehicle_sub_unit'] == 'ל'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'מלפפונים'
    assert result.rows[1]['qty'] == 4
    assert result.rows[1]['trans_type'] == 'נאכל'
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'


def test_transfer_with_math(config):
    """
    העבירו 2x17 נודלס ספגטי ל-ל

    Exercises: Hebrew verb, math expression, alias, double-entry.
    """
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
    """
    8 קופסה תפו"א קטנים ל-כ
    7 קופסה תפוחי אדמה קטנים ל-ל

    Exercises: Hebrew alias, different destinations, container conversion, batches.
    """
    result = parse(
        '8 קופסה תפו"א קטנים ל-כ\n'
        '7 קופסה תפוחי אדמה קטנים ל-ל',
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4

    # Batch 1: 8 קופסה to כ → 8 × 920 = 7360
    assert result.rows[0]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[0]['qty'] == -7360
    assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[1]['qty'] == 7360
    assert result.rows[1]['vehicle_sub_unit'] == 'כ'
    assert result.rows[1]['batch'] == 1

    # Batch 2: 7 קופסה to ל → 7 × 920 = 6440
    assert result.rows[2]['qty'] == -6440
    assert result.rows[2]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[2]['batch'] == 2

    assert result.rows[3]['qty'] == 6440
    assert result.rows[3]['vehicle_sub_unit'] == 'ל'
    assert result.rows[3]['batch'] == 2


def test_unparseable_numbers(config):
    """
    4 82 95 3 1

    Numbers without item names → unparseable.
    """
    result = parse("4 82 95 3 1", config, today=TODAY)
    assert len(result.rows) == 0
    assert len(result.unparseable) > 0


def test_communication_note(config):
    """
    רימון ל-נ דרך נאור בטלפון

    No quantity, no known item → classified as note.
    """
    result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
    assert len(result.rows) == 0
    assert len(result.notes) == 1
    assert 'רימון' in result.notes[0]


def test_destination_changes_mid_list(config):
    """
    3 מלפפונים ל-ל
    2 ספגטי
    5 עגבניות שרי ל-כ
    1 תפוחי אדמה קטנים

    Exercises: forward broadcasting, batch change on destination change.
    """
    result = parse(
        "3 מלפפונים ל-ל\n"
        "2 ספגטי\n"
        "5 עגבניות שרי ל-כ\n"
        "1 תפוחי אדמה קטנים",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 8  # 4 items × 2 rows each (double-entry)

    # Batch 1: to ל
    assert result.rows[0]['inv_type'] == 'מלפפונים'
    assert result.rows[0]['qty'] == -3
    assert result.rows[0]['vehicle_sub_unit'] == 'מחסן'
    assert result.rows[1]['qty'] == 3
    assert result.rows[1]['vehicle_sub_unit'] == 'ל'
    assert result.rows[1]['batch'] == 1

    # ספגטי inherits destination ל
    assert result.rows[2]['inv_type'] == 'ספגטי'
    assert result.rows[3]['vehicle_sub_unit'] == 'ל'
    assert result.rows[3]['batch'] == 1

    # Batch 2: to כ
    assert result.rows[4]['inv_type'] == 'עגבניות שרי'
    assert result.rows[5]['vehicle_sub_unit'] == 'כ'
    assert result.rows[5]['batch'] == 2

    # תפוחי אדמה inherits destination כ
    assert result.rows[6]['inv_type'] == 'תפוחי אדמה קטנים'
    assert result.rows[7]['vehicle_sub_unit'] == 'כ'
    assert result.rows[7]['batch'] == 2


def test_no_context_list(config):
    """
    4 פרוט לופס
    189 קורנפלקס
    3 קקאו פאפס
    1 טריקס

    No header — no date, no destination, no action verb.
    """
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
    """
    נאכל ב-ל 15.3.25
    2 קופסה קטנה עגבניות שרי
    4 מלפפונים

    נאכלו ב-ל 16.3.25
    1980 עגבניות שרי
    4 מלפפונים

    Same location, different dates → separate batches.
    """
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

    # Batch 1: 15.3.25
    assert result.rows[0]['date'] == date(2025, 3, 15)
    assert result.rows[0]['inv_type'] == 'עגבניות שרי'
    assert result.rows[0]['qty'] == 1980
    assert result.rows[0]['trans_type'] == 'נאכל'
    assert result.rows[0]['batch'] == 1

    assert result.rows[1]['inv_type'] == 'מלפפונים'
    assert result.rows[1]['qty'] == 4
    assert result.rows[1]['batch'] == 1

    # Batch 2: 16.3.25
    assert result.rows[2]['date'] == date(2025, 3, 16)
    assert result.rows[2]['inv_type'] == 'עגבניות שרי'
    assert result.rows[2]['qty'] == 1980
    assert result.rows[2]['batch'] == 2

    assert result.rows[3]['inv_type'] == 'מלפפונים'
    assert result.rows[3]['qty'] == 4
    assert result.rows[3]['batch'] == 2


# ============================================================
# TUI tests (Hebrew)
# ============================================================

def test_tui_confirm_hebrew(config, monkeypatch):
    """Parse Hebrew consumption → confirm → returns correct rows."""
    result = parse("נאכל ב-ל 15.3.25\n4 מלפפונים", config, today=TODAY)
    monkeypatch.setattr('builtins.input', make_input(["c"]))
    outcome = review_loop(result, "נאכל ב-ל 15.3.25\n4 מלפפונים", config)

    assert outcome is not None
    assert len(outcome['rows']) == 1
    assert outcome['rows'][0]['inv_type'] == 'מלפפונים'
    assert outcome['rows'][0]['qty'] == 4
    assert outcome['rows'][0]['trans_type'] == 'נאכל'
    assert outcome['rows'][0]['vehicle_sub_unit'] == 'ל'


def test_tui_edit_type_hebrew(config, monkeypatch):
    """Edit trans_type on a Hebrew row via picker.

    transaction_types: [a]נקודת_התחלה [b]ספירה_חוזרת [c]מחסן_לסניף
      [d]ספק_למחסן [e]נאכל ...
    """
    result = parse("4 מלפפונים ל-ל", config, today=TODAY)
    # 1t → edit trans_type, e → select נאכל (5th option), c → confirm
    monkeypatch.setattr('builtins.input', make_input(["1t", "e", "c"]))
    outcome = review_loop(result, "4 מלפפונים ל-ל", config)

    assert outcome['rows'][0]['trans_type'] == 'נאכל'
    assert outcome['rows'][1]['trans_type'] == 'נאכל'  # partner auto-updated


def test_tui_edit_qty_hebrew(config, monkeypatch):
    """Edit qty using math expression on a Hebrew row."""
    result = parse("נאכל ב-ל\n4 מלפפונים", config, today=TODAY)
    monkeypatch.setattr('builtins.input', make_input(["1q", "2x17", "c"]))
    outcome = review_loop(result, "נאכל ב-ל\n4 מלפפונים", config)
    assert outcome['rows'][0]['qty'] == 34


def test_tui_retry_hebrew(config, monkeypatch):
    """Retry with different Hebrew text."""
    result = parse("4 82 95 3 1", config, today=TODAY)
    assert len(result.rows) == 0

    monkeypatch.setattr('builtins.input', make_input([
        "e",                       # edit
        "4 מלפפונים ל-ל",           # corrected text
        "",                        # end of input
        "c",                       # confirm
    ]))
    outcome = review_loop(result, "4 82 95 3 1", config)

    assert outcome is not None
    assert len(outcome['rows']) == 2
    assert outcome['rows'][1]['inv_type'] == 'מלפפונים'
    assert outcome['rows'][1]['vehicle_sub_unit'] == 'ל'


def test_tui_note_hebrew(config, monkeypatch):
    """Hebrew note-only input → save as note."""
    result = parse("רימון ל-נ דרך נאור בטלפון", config, today=TODAY)
    assert len(result.notes) >= 1
    monkeypatch.setattr('builtins.input', make_input(["n"]))
    outcome = review_loop(result, "רימון ל-נ דרך נאור בטלפון", config)

    assert outcome is not None
    assert len(outcome['notes']) >= 1
    assert 'רימון' in outcome['notes'][0]
