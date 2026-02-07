"""
Tests for the inventory message parser.

These tests define the parser API and serve as the living specification.

Parser API:
    from inventory_parser import parse

    result = parse(text, config, today=date.today())
    result.rows         # list of row dicts (fully or partially parsed)
    result.notes        # list of note strings (non-transaction text)
    result.unparseable  # list of raw text strings that couldn't be parsed

Row dict keys:
    date             - date object (defaults to today if not in message)
    inv_type         - canonical item name (str), or raw text if unknown
    qty              - numeric quantity in base units (int or float)
    trans_type       - transaction type (str or None if ambiguous)
    vehicle_sub_unit - location (str or None if ambiguous)
    batch            - batch number (int)
    notes            - optional notes (str or None)

Context broadcasting:
    When parsing multi-line input, context (destination, source, date,
    action verb) propagates forward. Lines without explicit context
    inherit from the previous line. If items at the START of the message
    have no context, they get filled by the last-seen context from
    anywhere in the message (backward fill for otherwise-unfilled items).
"""

import pytest
from datetime import date

from inventory_parser import parse


# ============================================================
# Fixtures
# ============================================================

TODAY = date(2025, 3, 19)


@pytest.fixture
def config():
    """Standard test config with known items, aliases, and conversions."""
    return {
        'items': [
            'cherry tomatoes',
            'sweet cherry tomatoes',
            'small potatoes',
            'spaghetti',
            'cucumbers',
            'chicken',
            'carrots',
            'aluminum pans',
            'froot loops',
            'cornflakes',
            'cheerios',
            'cocoa puffs',
            'trix',
        ],
        'aliases': {
            'small pot': 'small potatoes',
            'cherry tom': 'cherry tomatoes',
            'spaghetti noodles': 'spaghetti',
            'spuds': 'small potatoes',
        },
        'locations': ['L', 'C', 'N'],
        'default_source': 'warehouse',
        'action_verbs': {
            'warehouse_to_branch': ['passed', 'gave', 'sent', 'delivered'],
            'supplier_to_warehouse': ['received', 'got'],
            'eaten': ['eaten', 'consumed', 'used'],
        },
        'unit_conversions': {
            'cherry tomatoes': {
                'base_unit': 'count',
                'small box': 990,
                'box': 1980,
            },
            'sweet cherry tomatoes': {
                'base_unit': 'count',
                'small box': 990,
                'box': 1980,
            },
            'small potatoes': {
                'base_unit': 'count',
                'box': 920,
            },
        },
    }


@pytest.fixture
def config_no_conversions(config):
    """Config without unit conversions — tests unknown-container flow."""
    return {**config, 'unit_conversions': {}}


# ============================================================
# Test 1: Simple consumption
# ============================================================

def test_simple_consumption(config):
    """
    Input:
        eaten by L 15.3.25
        2 small boxes cherry tomatoes
        4 cucumbers

    Exercises:
    - Date extraction (DD.M.YY format)
    - "eaten by <unit>" header → TRANS_TYPE=eaten, scopes subsequent lines
    - Container conversion: 2 small boxes × 990 = 1980
    - Multiple items under one header
    - Single batch (same destination)
    - Non-zero-sum (eaten = single row per item, no double-entry)
    """
    result = parse(
        "eaten by L 15.3.25\n"
        "2 small boxes cherry tomatoes\n"
        "4 cucumbers",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2
    assert result.notes == []
    assert result.unparseable == []

    assert result.rows[0] == {
        'date': date(2025, 3, 15),
        'inv_type': 'cherry tomatoes',
        'qty': 1980,  # 2 small boxes × 990
        'trans_type': 'eaten',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': date(2025, 3, 15),
        'inv_type': 'cucumbers',
        'qty': 4,
        'trans_type': 'eaten',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }


# ============================================================
# Test 2: Transfer with math expression
# ============================================================

def test_transfer_with_math(config):
    """
    Input:
        passed 2x17 spaghetti noodles to L

    Exercises:
    - Math expression: "2x17" → 34
    - "passed X to Y" → warehouse_to_branch
    - Double-entry: source (warehouse) and destination (L)
    - Alias: "spaghetti noodles" → "spaghetti"
    - Default source = warehouse
    """
    result = parse(
        "passed 2x17 spaghetti noodles to L",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2

    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': -34,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': 34,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }


# ============================================================
# Test 3: Multiple destinations (with conversion)
# ============================================================

def test_multiple_destinations(config):
    """
    Input:
        8 boxes of small pot to C
        7 boxes of small potatoes to L

    Exercises:
    - Abbreviation: "small pot" → "small potatoes"
    - Different destinations → different batches
    - Container conversion: boxes × 920
    - Double-entry for each transfer
    """
    result = parse(
        "8 boxes of small pot to C\n"
        "7 boxes of small potatoes to L",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4

    # Batch 1: 8 boxes to C → 8 × 920 = 7360
    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': -7360,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': 7360,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'C',
        'batch': 1,
        'notes': None,
    }

    # Batch 2: 7 boxes to L → 7 × 920 = 6440
    assert result.rows[2] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': -6440,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 2,
        'notes': None,
    }
    assert result.rows[3] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': 6440,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 2,
        'notes': None,
    }


# ============================================================
# Tests 4 & 14: Unparseable input (cryptic numbers)
# ============================================================

def test_unparseable_numbers(config):
    """
    Input:
        4 82 95 3 1
           37 19
           70 3

    Exercises:
    - Numbers without item names → unparseable
    - No rows generated, no crash
    - Raw text preserved in result.unparseable
    - Tool processes one message at a time (no cross-message context)
    """
    result = parse(
        "4 82 95 3 1\n"
        "   37 19\n"
        "   70 3",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 0
    assert len(result.unparseable) > 0


# ============================================================
# Test 5: Supplier delivery with typo and math
# ============================================================

def test_supplier_delivery(config):
    """
    Input:
        11*920
        smalal potatoes
        that's what got from Ran Serah

    Exercises:
    - Math expression: "11*920" → 10120
    - Typo correction: "smalal potatoes" → "small potatoes" (fuzzy match)
    - Multi-line merging: qty on line 1, item on line 2, verb on line 3
    - "got from X" → supplier_to_warehouse
    - Supplier name "Ran Serah" extracted into NOTES
    - Non-zero-sum (single row, items enter the system)
    """
    result = parse(
        "11*920\n"
        "smalal potatoes\n"
        "that's what got from Ran Serah",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 1

    row = result.rows[0]
    assert row['date'] == TODAY
    assert row['inv_type'] == 'small potatoes'
    assert row['qty'] == 10120
    assert row['trans_type'] == 'supplier_to_warehouse'
    assert row['vehicle_sub_unit'] == 'warehouse'
    assert row['batch'] == 1
    # Notes should contain the supplier name
    assert 'Ran Serah' in (row['notes'] or '')


# ============================================================
# Test 6: Multi-date consumption (same truck, different dates)
# ============================================================

def test_multi_date_consumption(config):
    """
    Input:
        eaten by L 15.3.25
        2 small boxes cherry tomatoes
        4 cucumbers
        8 boxes of small potatoes
        1 sweet cherry tomatoes
        4 chicken

        eaten by L 16.3.25
        1980 cherry tomatoes
        4 cucumbers
        1610 small potatoes
        990 sweet cherry tomatoes
        4 chicken

    Exercises:
    - Same truck, different dates → separate batches
    - "eaten by <unit> <date>" header scopes subsequent lines
    - Container conversion: 2 small boxes × 990, 8 boxes × 920
    - Raw counts (1980, 1610, 990) already in base unit
    - 5 items per batch, 10 rows total
    """
    result = parse(
        "eaten by L 15.3.25\n"
        "2 small boxes cherry tomatoes\n"
        "4 cucumbers\n"
        "8 boxes of small potatoes\n"
        "1 sweet cherry tomatoes\n"
        "4 chicken\n"
        "\n"
        "eaten by L 16.3.25\n"
        "1980 cherry tomatoes\n"
        "4 cucumbers\n"
        "1610 small potatoes\n"
        "990 sweet cherry tomatoes\n"
        "4 chicken",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 10

    # --- Batch 1: 15.3.25 ---
    assert result.rows[0] == {
        'date': date(2025, 3, 15),
        'inv_type': 'cherry tomatoes',
        'qty': 1980,  # 2 small boxes × 990
        'trans_type': 'eaten',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1]['inv_type'] == 'cucumbers'
    assert result.rows[1]['qty'] == 4
    assert result.rows[1]['batch'] == 1

    assert result.rows[2]['inv_type'] == 'small potatoes'
    assert result.rows[2]['qty'] == 7360  # 8 boxes × 920
    assert result.rows[2]['batch'] == 1

    assert result.rows[3]['inv_type'] == 'sweet cherry tomatoes'
    assert result.rows[3]['qty'] == 1
    assert result.rows[3]['batch'] == 1

    assert result.rows[4]['inv_type'] == 'chicken'
    assert result.rows[4]['qty'] == 4
    assert result.rows[4]['batch'] == 1

    # --- Batch 2: 16.3.25 ---
    assert result.rows[5] == {
        'date': date(2025, 3, 16),
        'inv_type': 'cherry tomatoes',
        'qty': 1980,
        'trans_type': 'eaten',
        'vehicle_sub_unit': 'L',
        'batch': 2,
        'notes': None,
    }
    assert result.rows[6]['qty'] == 4       # cucumbers
    assert result.rows[7]['qty'] == 1610    # small potatoes (raw count)
    assert result.rows[8]['qty'] == 990     # sweet cherry tomatoes (raw count)
    assert result.rows[9]['qty'] == 4       # chicken

    for row in result.rows[5:]:
        assert row['date'] == date(2025, 3, 16)
        assert row['batch'] == 2


# ============================================================
# Test 7: Warehouse receiving
# ============================================================

def test_warehouse_receiving(config):
    """
    Input:
        + 3 boxes of small potatoes gathered into the warehouse

    Exercises:
    - "gathered into the warehouse" pattern → receiving at warehouse
    - QTY is positive (items entering)
    - Container conversion: 3 × 920 = 2760

    Note: TRANS_TYPE is ambiguous (could be supplier_to_warehouse,
    between_warehouses, or return from branch). Parser makes best guess.
    """
    result = parse(
        "+ 3 boxes of small potatoes gathered into the warehouse",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row['inv_type'] == 'small potatoes'
    assert row['qty'] == 2760  # 3 × 920
    assert row['vehicle_sub_unit'] == 'warehouse'
    assert row['date'] == TODAY


# ============================================================
# Test 8: Partial withdrawal
# ============================================================

def test_partial_withdrawal(config):
    """
    Input:
        took 5 out of 9 carrots

    Exercises:
    - "took X out of Y <item>" → QTY=X (amount taken)
    - Y (total/original count) preserved in notes as context
    - TRANS_TYPE ambiguous → None
    - VEHICLE_SUB_UNIT ambiguous → None
    """
    result = parse(
        "took 5 out of 9 carrots",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row['inv_type'] == 'carrots'
    assert row['qty'] == 5
    assert row['trans_type'] is None
    assert row['vehicle_sub_unit'] is None
    assert row['notes'] is not None
    assert '9' in row['notes']


# ============================================================
# Test 9: Request / need (future scope)
# ============================================================

@pytest.mark.skip(reason="Requests are future scope — not in first iteration")
def test_request_need(config):
    """
    Input:
        A need for 80 aluminum pans and 10000 amall potatoes

    Exercises:
    - "need for" pattern → detected as request (separate output)
    - Multiple items in one line ("X and Y")
    - Typo correction: "amall potatoes" → "small potatoes"

    Requests go to a separate output. Not in first iteration scope.
    """
    pass


# ============================================================
# Test 10: WhatsApp metadata stripping
# ============================================================

def test_whatsapp_metadata(config):
    """
    Input:
        8 boxes of small pot to C <This message was edited>

    Exercises:
    - Strip "<This message was edited>" before parsing
    - Abbreviation: "small pot" → "small potatoes"
    - Container conversion: 8 × 920 = 7360
    - Normal transfer after metadata removal
    """
    result = parse(
        "8 boxes of small pot to C <This message was edited>",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2

    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': -7360,  # 8 × 920
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': 7360,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'C',
        'batch': 1,
        'notes': None,
    }


# ============================================================
# Test 11: Item list with no context
# ============================================================

def test_no_context_list(config):
    """
    Input:
        4 froot loops
        189 cornflakes
        117 cheerios
        3 cocoa puffs
        1 trix

    Exercises:
    - No header line — no date, no destination, no action verb
    - Parser extracts items + quantities
    - trans_type and vehicle_sub_unit are None (no context to infer from)
    - All items in one batch
    - Date defaults to today
    """
    result = parse(
        "4 froot loops\n"
        "189 cornflakes\n"
        "117 cheerios\n"
        "3 cocoa puffs\n"
        "1 trix",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 5

    expected = [
        ('froot loops', 4),
        ('cornflakes', 189),
        ('cheerios', 117),
        ('cocoa puffs', 3),
        ('trix', 1),
    ]
    for row, (item, qty) in zip(result.rows, expected):
        assert row['inv_type'] == item
        assert row['qty'] == qty
        assert row['trans_type'] is None
        assert row['vehicle_sub_unit'] is None
        assert row['date'] == TODAY
        assert row['batch'] == 1


# ============================================================
# Test 12: Fractional container
# ============================================================

def test_fractional_container(config):
    """
    Input:
        passed half a box of cherry tomatoes to L

    Exercises:
    - Fractional container: "half a box" → 0.5 × 1980 = 990
    - "passed X to Y" → warehouse_to_branch with double-entry

    Note: Parser may optionally flag fractional containers with extra
    confidence warning. User reviews everything anyway.
    """
    result = parse(
        "passed half a box of cherry tomatoes to L",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 2

    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': -990,  # 0.5 × 1980
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': 990,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }


# ============================================================
# Test 13: Communication note (not a transaction)
# ============================================================

def test_communication_note(config):
    """
    Input:
        Rimon to N via naor by phone

    Exercises:
    - No quantity, no known item → not a transaction
    - Saved as note (not discarded)
    - No rows generated
    """
    result = parse(
        "Rimon to N via naor by phone",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 0
    assert len(result.notes) == 1
    assert 'Rimon to N via naor by phone' in result.notes[0]


# ============================================================
# Test 15: Mixed destinations in one paste
# ============================================================

def test_mixed_destinations(config):
    """
    Input:
        passed 2x 17 spagetti noodles to L
        passed half a box of cherry tomatoes to L
        14 box of spuds to C

    Exercises:
    - Two destinations → two batches (L=batch 1, C=batch 2)
    - Same destination (L) groups into one batch
    - Math with space: "2x 17" → 34
    - Typo: "spagetti" → "spaghetti" (fuzzy match)
    - Alias: "spuds" → "small potatoes" (learned alias)
    - Fractional container: "half a box" → 990
    - Container: "14 box" → 14 × 920 = 12880
    - Double-entry for all transfers
    """
    result = parse(
        "passed 2x 17 spagetti noodles to L\n"
        "passed half a box of cherry tomatoes to L\n"
        "14 box of spuds to C",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 6

    # --- Batch 1: to L ---
    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': -34,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': 34,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[2] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': -990,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[3] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': 990,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }

    # --- Batch 2: to C ---
    assert result.rows[4] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': -12880,  # 14 × 920
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 2,
        'notes': None,
    }
    assert result.rows[5] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': 12880,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'C',
        'batch': 2,
        'notes': None,
    }


# ============================================================
# Test 16: Context broadcasting from note line
# ============================================================

def test_context_broadcast_from_note(config):
    """
    Input:
        cucumber
        small potatoes
        Rimon to N via naor by phone

    Exercises:
    - Items at start of message have no destination
    - Note line (last) provides "to N" → destination broadcasts to items
    - Backward fill: items before the note get N as destination
    - Items default qty=1 (no quantity specified)
    - Note preserved alongside transaction rows
    - No verb + destination → default trans_type (warehouse_to_branch)
    """
    result = parse(
        "cucumber\n"
        "small potatoes\n"
        "Rimon to N via naor by phone",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 4  # 2 items × 2 rows each (double-entry)

    # cucumber to N
    assert result.rows[0]['inv_type'] == 'cucumbers'
    assert result.rows[0]['qty'] == -1
    assert result.rows[0]['vehicle_sub_unit'] == 'warehouse'
    assert result.rows[0]['trans_type'] == 'warehouse_to_branch'

    assert result.rows[1]['inv_type'] == 'cucumbers'
    assert result.rows[1]['qty'] == 1
    assert result.rows[1]['vehicle_sub_unit'] == 'N'

    # small potatoes to N
    assert result.rows[2]['inv_type'] == 'small potatoes'
    assert result.rows[2]['qty'] == -1
    assert result.rows[2]['vehicle_sub_unit'] == 'warehouse'

    assert result.rows[3]['inv_type'] == 'small potatoes'
    assert result.rows[3]['qty'] == 1
    assert result.rows[3]['vehicle_sub_unit'] == 'N'

    # Note preserved
    assert len(result.notes) == 1
    assert 'Rimon to N via naor by phone' in result.notes[0]


# ============================================================
# Test 17: Destination changes mid-list (forward broadcasting)
# ============================================================

def test_destination_changes_mid_list(config):
    """
    Input:
        3 cucumbers to L
        2 spaghetti
        5 cherry tomatoes to C
        1 small potatoes

    Exercises:
    - Spaghetti inherits destination L from cucumbers line (forward)
    - Small potatoes inherits destination C from cherry tomatoes line (forward)
    - Batch changes when destination changes (L=batch 1, C=batch 2)
    - No verb → default trans_type (warehouse_to_branch) since dest exists
    - Double-entry for all items
    """
    result = parse(
        "3 cucumbers to L\n"
        "2 spaghetti\n"
        "5 cherry tomatoes to C\n"
        "1 small potatoes",
        config,
        today=TODAY,
    )

    assert len(result.rows) == 8  # 4 items × 2 rows each

    # --- Batch 1: to L ---
    assert result.rows[0] == {
        'date': TODAY,
        'inv_type': 'cucumbers',
        'qty': -3,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[1] == {
        'date': TODAY,
        'inv_type': 'cucumbers',
        'qty': 3,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }
    # spaghetti inherits L
    assert result.rows[2] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': -2,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 1,
        'notes': None,
    }
    assert result.rows[3] == {
        'date': TODAY,
        'inv_type': 'spaghetti',
        'qty': 2,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'L',
        'batch': 1,
        'notes': None,
    }

    # --- Batch 2: to C ---
    assert result.rows[4] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': -5,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 2,
        'notes': None,
    }
    assert result.rows[5] == {
        'date': TODAY,
        'inv_type': 'cherry tomatoes',
        'qty': 5,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'C',
        'batch': 2,
        'notes': None,
    }
    # small potatoes inherits C
    assert result.rows[6] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': -1,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'warehouse',
        'batch': 2,
        'notes': None,
    }
    assert result.rows[7] == {
        'date': TODAY,
        'inv_type': 'small potatoes',
        'qty': 1,
        'trans_type': 'warehouse_to_branch',
        'vehicle_sub_unit': 'C',
        'batch': 2,
        'notes': None,
    }
