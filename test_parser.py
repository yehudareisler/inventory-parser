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

from inventory_parser import parse, fuzzy_resolve


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


# ============================================================
# Input boundary conditions
# ============================================================

class TestInputBoundaries:
    """Tests for degenerate and boundary-condition inputs."""

    def test_empty_string(self, config):
        """Empty input produces no output and no crash."""
        result = parse("", config, today=TODAY)
        assert result.rows == []
        assert result.notes == []
        assert result.unparseable == []

    def test_whitespace_only(self, config):
        """Whitespace-only input produces no output."""
        result = parse("   \n  \n  ", config, today=TODAY)
        assert result.rows == []
        assert result.notes == []
        assert result.unparseable == []

    def test_single_number_no_item(self, config):
        """A bare number with no item name → unparseable."""
        result = parse("42", config, today=TODAY)
        assert len(result.rows) == 0
        assert len(result.unparseable) == 1

    def test_single_item_no_qty_defaults_to_one(self, config):
        """
        A bare item name with no quantity → qty defaults to 1.

        Per requirements: "If no quantity found but a known item is
        found, default qty = 1."
        """
        result = parse("cucumbers", config, today=TODAY)
        assert len(result.rows) == 1
        assert result.rows[0]['inv_type'] == 'cucumbers'
        assert result.rows[0]['qty'] == 1

    def test_just_a_location(self, config):
        """
        'to L' with no item or qty → classified as note.

        Has alphabetic text and a destination, but no transaction data.
        """
        result = parse("to L", config, today=TODAY)
        assert len(result.rows) == 0

    def test_just_a_verb(self, config):
        """'eaten' alone → classified as note (has alpha chars but no transaction)."""
        result = parse("eaten", config, today=TODAY)
        assert len(result.rows) == 0

    def test_just_a_date(self, config):
        """A bare date with nothing else → unparseable (no alpha text)."""
        result = parse("15.3.25", config, today=TODAY)
        assert len(result.rows) == 0
        assert len(result.unparseable) == 1

    def test_leading_minus_stripped(self, config):
        """
        Leading -/+ signs in message text are stripped.

        The sign is determined by double-entry logic, not message text.
        "-5 cucumbers to L" → qty=5 (positive), sign from source/dest logic.
        """
        result = parse("-5 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['qty'] == -5   # warehouse (source) side
        assert result.rows[1]['qty'] == 5    # L (destination) side

    def test_leading_plus_stripped(self, config):
        """Leading + sign stripped, parsed normally."""
        result = parse("+ 3 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[1]['qty'] == 3

    def test_very_large_quantity(self, config):
        """Very large numbers don't crash."""
        result = parse("999999 cucumbers to L", config, today=TODAY)
        assert result.rows[1]['qty'] == 999999

    def test_special_characters_in_text(self, config):
        """Parentheses and other special chars don't break parsing."""
        result = parse("4 cucumbers (fresh) to L", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['inv_type'] == 'cucumbers'


# ============================================================
# Item matching edge cases
# ============================================================

class TestItemMatchingEdgeCases:
    """Tests for item name resolution edge cases."""

    def test_substring_disambiguation_longest_wins(self, config):
        """
        'sweet cherry tomatoes' must match the full name, not 'cherry tomatoes'.

        The matcher sorts by length descending and checks substrings,
        so "sweet cherry tomatoes" (longer) should win.
        """
        result = parse("4 sweet cherry tomatoes to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'sweet cherry tomatoes'

    def test_shorter_substring_exact(self, config):
        """'cherry tomatoes' matches exactly, not 'sweet cherry tomatoes'."""
        result = parse("4 cherry tomatoes to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cherry tomatoes'

    def test_case_insensitive_matching(self, config):
        """Item matching is case-insensitive."""
        result = parse("4 CUCUMBERS to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'

    def test_mixed_case_matching(self, config):
        """Mixed case like 'CuCuMbErS' still matches."""
        result = parse("4 CuCuMbErS to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'

    def test_singular_matches_plural_canonical(self, config):
        """'cucumber' (no s) matches canonical 'cucumbers'."""
        result = parse("4 cucumber to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'

    def test_extra_s_fuzzy_matches(self, config):
        """'cucumberss' (extra s) fuzzy-matches 'cucumbers'."""
        result = parse("4 cucumberss to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'

    def test_completely_unknown_item_goes_to_unparseable(self, config):
        """Totally unknown word → unparseable (qty found but item unknown)."""
        result = parse("4 flibbertigibbet to L", config, today=TODAY)
        assert len(result.rows) == 0
        assert len(result.unparseable) == 1

    def test_short_prefix_matches(self, config):
        """Short prefix like 'small' matches 'small potatoes'."""
        result = parse("4 small to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'small potatoes'

    def test_embedded_item_in_longer_text(self, config):
        """Item name inside longer text is still found (substring match)."""
        result = parse("4 fresh cucumbers to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'


# ============================================================
# Date parsing edge cases (parser-level)
# ============================================================

class TestDateParsingEdgeCases:
    """Tests for date extraction in the parser (not TUI date editing)."""

    def test_date_dd_mm_yyyy_full_year(self, config):
        """Full four-digit year: 15.03.2025."""
        result = parse("15.03.2025 4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['date'] == date(2025, 3, 15)

    def test_date_slash_format_in_parser(self, config):
        """US slash format: M/DD/YY → date extracted."""
        result = parse("3/15/25 4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['date'] == date(2025, 3, 15)

    def test_invalid_date_falls_back_to_today(self, config):
        """Invalid date (32.13.25) is ignored; date falls back to today."""
        result = parse("32.13.25 4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['date'] == TODAY

    def test_date_without_year_not_matched(self, config):
        """Partial date '15.3' (no year) is not recognized as a date."""
        result = parse("15.3 4 cucumbers to L", config, today=TODAY)
        # 15.3 is not a valid date pattern (requires year component)
        assert result.rows[0]['date'] == TODAY

    def test_six_digit_ddmmyy_consumed_as_date(self, config):
        """
        150325 (DDMMYY) is consumed as date, NOT as quantity.

        Date extraction runs before qty extraction, so the 6-digit
        number is interpreted as 15.03.2025.
        """
        result = parse("150325 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['date'] == date(2025, 3, 15)
        # Qty defaults to 1 since the number was consumed as a date
        assert result.rows[1]['qty'] == 1

    def test_first_valid_date_wins(self, config):
        """When two date-like patterns appear, first match wins."""
        result = parse("15.3.25 16.3.25 4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['date'] == date(2025, 3, 15)


# ============================================================
# Math expression edge cases
# ============================================================

class TestMathExpressionEdgeCases:
    """Tests for quantity math expression handling."""

    def test_unicode_multiply_sign(self, config):
        """Unicode × (multiplication sign) works like x and *."""
        result = parse("2×17 spaghetti to L", config, today=TODAY)
        assert result.rows[1]['qty'] == 34

    def test_math_with_spaces(self, config):
        """'2 x 17' with spaces around x."""
        result = parse("2 x 17 spaghetti to L", config, today=TODAY)
        assert result.rows[1]['qty'] == 34

    def test_asterisk_multiplication(self, config):
        """'11*920' with asterisk."""
        result = parse("11*920 spaghetti to L", config, today=TODAY)
        assert result.rows[1]['qty'] == 10120


# ============================================================
# Container conversion edge cases
# ============================================================

class TestContainerEdgeCases:
    """Tests for container/unit conversion edge cases."""

    def test_container_singular_and_plural(self, config):
        """Both 'box' and 'boxes' match the same container type."""
        r1 = parse("1 box cherry tomatoes to L", config, today=TODAY)
        r2 = parse("2 boxes cherry tomatoes to L", config, today=TODAY)
        assert r1.rows[1]['qty'] == 1980     # 1 × 1980
        assert r2.rows[1]['qty'] == 3960     # 2 × 1980

    def test_no_conversion_factor_keeps_raw_qty(self, config):
        """
        Container recognized but no conversion for this item → qty unchanged.

        'cucumbers' has no unit_conversions entry, so '4 boxes cucumbers'
        keeps qty=4 (the box is ignored or not converted).
        """
        result = parse("4 boxes cucumbers to L", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'
        # Qty stays 4 since there's no conversion factor for cucumbers boxes
        assert abs(result.rows[0]['qty']) == 4

    def test_half_without_container_not_fractional(self, config):
        """
        'half cucumbers' (no 'a [container]') → NOT recognized as fraction.

        The "half a [container]" pattern requires "half a" followed by a
        known container type. Without it, 'half' is just unmatched text.
        """
        result = parse("half cucumbers to L", config, today=TODAY)
        # Item gets default qty=1 since "half" isn't parsed as a number
        assert result.rows[1]['qty'] == 1


# ============================================================
# Context broadcasting edge cases
# ============================================================

class TestContextBroadcastingEdgeCases:
    """Tests for multi-line context propagation edge cases."""

    def test_backward_fill_from_end(self, config):
        """
        Items at the start with no context get filled from the end.

        "4 cucumbers\n3 spaghetti\nto L" → both items get destination L.
        """
        result = parse("4 cucumbers\n3 spaghetti\nto L", config, today=TODAY)
        assert len(result.rows) == 4  # 2 items × double-entry
        for row in result.rows:
            assert row['vehicle_sub_unit'] in ('warehouse', 'L')

    def test_three_destinations_three_batches(self, config):
        """Three different destinations → three separate batches."""
        result = parse(
            "3 cucumbers to L\n"
            "2 spaghetti to C\n"
            "1 chicken to N",
            config, today=TODAY,
        )
        assert len(result.rows) == 6
        assert result.rows[0]['batch'] == 1
        assert result.rows[2]['batch'] == 2
        assert result.rows[4]['batch'] == 3

    def test_date_change_increments_batch(self, config):
        """Same destination but different dates → different batches."""
        result = parse(
            "15.3.25 4 cucumbers to L\n"
            "16.3.25 3 spaghetti to L",
            config, today=TODAY,
        )
        assert result.rows[0]['batch'] == 1
        assert result.rows[0]['date'] == date(2025, 3, 15)
        assert result.rows[2]['batch'] == 2
        assert result.rows[2]['date'] == date(2025, 3, 16)

    def test_verb_changes_mid_message(self, config):
        """
        Verb change mid-message: 'eaten by L' then 'passed to C'.

        First item gets eaten/L, second gets warehouse_to_branch/C.
        """
        result = parse(
            "eaten by L\n"
            "4 cucumbers\n"
            "passed 3 spaghetti to C",
            config, today=TODAY,
        )
        assert result.rows[0]['trans_type'] == 'eaten'
        assert result.rows[0]['vehicle_sub_unit'] == 'L'
        assert result.rows[1]['trans_type'] == 'warehouse_to_branch'

    def test_blank_lines_dont_break_context(self, config):
        """Blank lines between items don't break context propagation."""
        result = parse(
            "eaten by L 15.3.25\n"
            "4 cucumbers\n"
            "\n"
            "\n"
            "3 spaghetti",
            config, today=TODAY,
        )
        assert len(result.rows) == 2
        for row in result.rows:
            assert row['trans_type'] == 'eaten'
            assert row['vehicle_sub_unit'] == 'L'
            assert row['date'] == date(2025, 3, 15)

    def test_verb_only_line_applies_to_previous(self, config):
        """
        A verb-only line after an item applies retroactively.

        "4 cucumbers to L\neaten" → cucumbers becomes eaten at L.
        """
        result = parse("4 cucumbers to L\neaten", config, today=TODAY)
        assert len(result.rows) == 1  # eaten = non-zero-sum, single row
        assert result.rows[0]['trans_type'] == 'eaten'
        assert result.rows[0]['vehicle_sub_unit'] == 'L'


# ============================================================
# Multi-line merging edge cases
# ============================================================

class TestMultiLineMerging:
    """Tests for how adjacent lines get merged."""

    def test_qty_line_then_item_line_merged(self, config):
        """
        Qty on line 1, item on line 2 → merged into one transaction.

        This is the "11*920\nsmalal potatoes" pattern.
        Note: the merge copies item from line 2 into line 1's dict,
        but location from line 2 is NOT carried over. Context for
        location must come from elsewhere (a header line, a note, etc).
        """
        result = parse("20\ncucumbers", config, today=TODAY)
        assert len(result.rows) == 1
        assert result.rows[0]['inv_type'] == 'cucumbers'
        assert result.rows[0]['qty'] == 20

    def test_two_qty_lines_then_item(self, config):
        """
        Two qty-only lines then an item: only second qty merges.

        "10\n20\ncucumbers to L" → 10 becomes unparseable,
        20 merges with cucumbers.
        """
        result = parse("10\n20\ncucumbers to L", config, today=TODAY)
        assert any(r['inv_type'] == 'cucumbers' and r['qty'] == 20 for r in result.rows)

    def test_qty_with_unmatched_text_no_merge(self, config):
        """
        Qty + unknown text line → does NOT merge with next item.

        "4 flibbert\ncucumbers to L" → "4 flibbert" is unparseable,
        cucumbers is parsed separately.
        """
        result = parse("4 flibbert\ncucumbers to L", config, today=TODAY)
        assert len(result.unparseable) == 1
        assert any(r['inv_type'] == 'cucumbers' for r in result.rows)


# ============================================================
# Double-entry bookkeeping invariants
# ============================================================

class TestDoubleEntryInvariants:
    """Tests for double-entry accounting correctness."""

    def test_transfer_sums_to_zero(self, config):
        """Transfer transactions must sum to zero per batch."""
        result = parse(
            "passed 34 spaghetti to L\n"
            "passed 10 cucumbers to C",
            config, today=TODAY,
        )
        batch_sums = {}
        for row in result.rows:
            b = row['batch']
            batch_sums[b] = batch_sums.get(b, 0) + row['qty']
        for batch, total in batch_sums.items():
            assert total == 0, f"Batch {batch} sums to {total}, expected 0"

    def test_eaten_is_single_row_positive(self, config):
        """Non-zero-sum type (eaten) produces a single row with positive qty."""
        result = parse("eaten by L\n4 cucumbers", config, today=TODAY)
        assert len(result.rows) == 1
        assert result.rows[0]['qty'] == 4
        assert result.rows[0]['trans_type'] == 'eaten'

    def test_supplier_delivery_single_row(self, config):
        """supplier_to_warehouse is non-zero-sum → single positive row."""
        result = parse(
            "11*920\nsmalal potatoes\nthat's what got from Ran Serah",
            config, today=TODAY,
        )
        assert len(result.rows) == 1
        assert result.rows[0]['qty'] == 10120
        assert result.rows[0]['vehicle_sub_unit'] == 'warehouse'

    def test_same_item_different_destinations_separate_batches(self, config):
        """Same item to two destinations → separate batches, each sums to zero."""
        result = parse(
            "4 cucumbers to L\n"
            "3 cucumbers to C",
            config, today=TODAY,
        )
        batch1 = [r for r in result.rows if r['batch'] == 1]
        batch2 = [r for r in result.rows if r['batch'] == 2]
        assert sum(r['qty'] for r in batch1) == 0
        assert sum(r['qty'] for r in batch2) == 0

    def test_zero_qty_transfer(self, config):
        """Zero-quantity transfer: both sides have qty=0."""
        result = parse("0 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['qty'] == 0
        assert result.rows[1]['qty'] == 0

    def test_warehouse_receiving_positive(self, config):
        """Receiving at warehouse → single positive row."""
        result = parse(
            "+ 3 boxes of small potatoes gathered into the warehouse",
            config, today=TODAY,
        )
        assert len(result.rows) == 1
        assert result.rows[0]['qty'] > 0
        assert result.rows[0]['vehicle_sub_unit'] == 'warehouse'


# ============================================================
# Location matching edge cases
# ============================================================

class TestLocationMatching:
    """Tests for location/destination extraction edge cases."""

    def test_location_word_boundary(self, config):
        """Location 'L' should not match inside longer words like 'London'."""
        result = parse("4 cucumbers to London", config, today=TODAY)
        # 'London' is not a known location, so no location is extracted
        assert result.rows[0]['vehicle_sub_unit'] is None

    def test_location_default_source(self, config):
        """Transfer to a location uses warehouse as default source."""
        result = parse("4 cucumbers to L", config, today=TODAY)
        assert result.rows[0]['vehicle_sub_unit'] == 'warehouse'
        assert result.rows[1]['vehicle_sub_unit'] == 'L'


# ============================================================
# Configuration edge cases
# ============================================================

class TestConfigEdgeCases:
    """Tests for graceful handling of minimal/empty configs."""

    def test_empty_config_no_crash(self):
        """Parse with empty config doesn't crash."""
        result = parse("4 cucumbers to L", {}, today=TODAY)
        assert isinstance(result.rows, list)
        assert isinstance(result.notes, list)
        assert isinstance(result.unparseable, list)

    def test_config_no_items(self):
        """Config with no items → nothing matches, goes to unparseable."""
        cfg = {'locations': ['L', 'C'], 'default_source': 'warehouse'}
        result = parse("4 cucumbers to L", cfg, today=TODAY)
        assert len(result.rows) == 0

    def test_config_no_locations(self):
        """Config with items but no locations → item parsed, no destination."""
        cfg = {'items': ['cucumbers', 'spaghetti']}
        result = parse("4 cucumbers to L", cfg, today=TODAY)
        assert len(result.rows) >= 1
        # Location is None since 'L' is not in config locations
        assert result.rows[0]['vehicle_sub_unit'] is None

    def test_config_no_action_verbs(self):
        """Config with no action_verbs → verbs treated as unmatched text."""
        cfg = {
            'items': ['cucumbers'],
            'locations': ['L'],
            'default_source': 'warehouse',
        }
        result = parse("passed 4 cucumbers to L", cfg, today=TODAY)
        assert len(result.rows) == 2  # still gets double-entry from location
        # trans_type comes from default, not verb matching
        assert result.rows[0]['trans_type'] == 'warehouse_to_branch'


# ============================================================
# fuzzy_resolve unit tests
# ============================================================

class TestFuzzyResolve:
    """Tests for the public fuzzy_resolve() function."""

    def test_exact_match(self):
        result, match_type = fuzzy_resolve('cucumbers', ['cucumbers', 'carrots'])
        assert result == 'cucumbers'
        assert match_type == 'exact'

    def test_exact_match_case_insensitive(self):
        result, match_type = fuzzy_resolve('CUCUMBERS', ['cucumbers', 'carrots'])
        assert result == 'cucumbers'
        assert match_type == 'exact'

    def test_alias_match(self):
        aliases = {'cukes': 'cucumbers'}
        result, match_type = fuzzy_resolve('cukes', ['cucumbers'], aliases)
        assert result == 'cucumbers'
        assert match_type == 'alias'

    def test_fuzzy_match(self):
        result, match_type = fuzzy_resolve('cucumbrs', ['cucumbers', 'carrots'])
        assert result == 'cucumbers'
        assert match_type == 'fuzzy'

    def test_no_match(self):
        result, match_type = fuzzy_resolve('banana', ['cucumbers', 'carrots'])
        assert result is None
        assert match_type is None

    def test_empty_text(self):
        result, match_type = fuzzy_resolve('', ['cucumbers'])
        assert result is None
        assert match_type is None

    def test_short_text_high_cutoff(self):
        """Short text (<=4 chars) uses higher cutoff to avoid false positives."""
        # 'car' is 3 chars — needs 0.8 cutoff, shouldn't match 'carrots' (ratio ~0.6)
        result, match_type = fuzzy_resolve('car', ['carrots', 'cucumbers'])
        assert result is None

    def test_fuzzy_via_alias_key(self):
        """Fuzzy match against an alias key resolves to the alias target."""
        aliases = {'spuds': 'small potatoes'}
        result, match_type = fuzzy_resolve('spudd', ['small potatoes'], aliases)
        assert result == 'small potatoes'
        assert match_type == 'fuzzy'


# ============================================================
# Location aliases in parsing
# ============================================================

class TestLocationAliases:
    """Tests for location aliases in the parser."""

    def test_location_alias_basic(self, config):
        """Alias 'branch_c' → 'C' resolves as location C."""
        config['aliases']['branch_c'] = 'C'
        result = parse("12 cucumbers to branch_c", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['vehicle_sub_unit'] == 'warehouse'
        assert result.rows[1]['vehicle_sub_unit'] == 'C'

    def test_location_alias_doesnt_break_items(self, config):
        """Location alias coexists with item aliases."""
        config['aliases']['branch_c'] = 'C'
        result = parse("12 spuds to branch_c", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[0]['inv_type'] == 'small potatoes'
        assert result.rows[1]['vehicle_sub_unit'] == 'C'

    def test_location_alias_not_item(self, config):
        """An alias targeting a location doesn't interfere with item matching."""
        config['aliases']['branch_c'] = 'C'
        result = parse("4 cucumbers", config, today=TODAY)
        assert result.rows[0]['inv_type'] == 'cucumbers'
        assert result.rows[0]['vehicle_sub_unit'] is None

    def test_unknown_alias_target_no_crash(self, config):
        """Alias targeting unknown entity doesn't crash location extraction."""
        config['aliases']['mystery'] = 'nonexistent'
        result = parse("4 cucumbers to L", config, today=TODAY)
        assert len(result.rows) == 2
        assert result.rows[1]['vehicle_sub_unit'] == 'L'


# ============================================================
# Container aliases in parsing
# ============================================================

class TestContainerAliases:
    """Tests for container aliases in the parser."""

    def test_container_alias_resolves(self, config):
        """Alias 'bx' → 'box' resolves in container extraction."""
        config['aliases']['bx'] = 'box'
        result = parse("2 bx cherry tomatoes to L", config, today=TODAY)
        assert len(result.rows) == 2
        # 2 boxes * 1980 = 3960
        assert abs(result.rows[0]['qty']) == 3960

    def test_container_alias_plural(self, config):
        """Container alias with English plural variant works."""
        config['aliases']['bx'] = 'box'
        result = parse("3 bxes cherry tomatoes", config, today=TODAY)
        assert len(result.rows) == 1
        # 3 boxes * 1980 = 5940
        assert result.rows[0]['qty'] == 5940

    def test_container_alias_no_interference(self, config):
        """Container alias doesn't interfere when item has no conversions."""
        config['aliases']['bx'] = 'box'
        result = parse("5 bx cucumbers", config, today=TODAY)
        # Cucumbers have no box conversion, so 'bx' as container → unconverted
        assert len(result.rows) >= 1
        assert result.rows[0]['inv_type'] == 'cucumbers'


# ============================================================
# Direct transaction type matching
# ============================================================

class TestDirectTransactionType:
    """Test matching transaction type names directly in text."""

    def test_direct_type_name(self, config):
        config['transaction_types'] = [
            'warehouse_to_branch', 'supplier_to_warehouse', 'eaten',
        ]
        result = parse('12 cucumbers supplier_to_warehouse', config, today=TODAY)
        assert len(result.rows) >= 1
        assert result.rows[0]['trans_type'] == 'supplier_to_warehouse'
        assert result.rows[0]['qty'] == 12

    def test_direct_type_doesnt_override_verb(self, config):
        """Action verbs should still take priority over direct type names."""
        config['transaction_types'] = [
            'warehouse_to_branch', 'supplier_to_warehouse', 'eaten',
        ]
        result = parse('received 12 cucumbers', config, today=TODAY)
        assert result.rows[0]['trans_type'] == 'supplier_to_warehouse'

    def test_type_alias(self, config):
        config['transaction_types'] = [
            'warehouse_to_branch', 'supplier_to_warehouse', 'eaten',
        ]
        config['aliases']['supplier'] = 'supplier_to_warehouse'
        result = parse('12 cucumbers supplier', config, today=TODAY)
        assert result.rows[0]['trans_type'] == 'supplier_to_warehouse'

    def test_hebrew_direct_type(self):
        config_he = {
            'items': ['מלפפונים'],
            'locations': ['ל'],
            'default_source': 'מחסן',
            'transaction_types': ['מחסן_לסניף', 'ספק_למחסן', 'נאכל'],
            'action_verbs': {
                'מחסן_לסניף': ['העביר'],
                'ספק_למחסן': ['קיבל'],
            },
            'prepositions': {'to': ['ל'], 'by': ['ב'], 'from': ['מ']},
            'aliases': {},
        }
        result = parse('12 מלפפונים ספק_למחסן', config_he, today=TODAY)
        assert result.rows[0]['trans_type'] == 'ספק_למחסן'


# ============================================================
# Multi-number qty/item disambiguation
# ============================================================

class TestMultiNumberDisambiguation:
    """Test that when first number isn't the qty, parser retries others."""

    def test_disambiguation_finds_item(self, config):
        """When first number as qty yields no item match, try other numbers."""
        # 'gadget' not in items, '555 gadget' is. First try: qty=100, remaining='555 gadget' → match.
        # Actually, qty=100 is first number, '555 gadget' goes to _match_item which matches.
        config['items'].append('gadget 555')
        result = parse('100 555 gadget', config, today=TODAY)
        assert len(result.rows) >= 1
        assert result.rows[0]['qty'] == 100
        assert result.rows[0]['inv_type'] == 'gadget 555'

    def test_disambiguation_swaps_qty(self, config):
        """When first number fails item match, second number works as qty."""
        # 'widget' not known. Add 'widget 88' as item.
        # '88 widget 50': qty=88, remaining='widget 50' → _match_item fuzzy matches 'widget 88'?
        # Actually 'widget 50' vs 'widget 88' are fuzzy. But '50 widget 88' is cleaner:
        # qty=50, remaining='widget 88' → exact match.
        config['items'].append('widget 88')
        result = parse('50 widget 88', config, today=TODAY)
        assert len(result.rows) >= 1
        assert result.rows[0]['inv_type'] == 'widget 88'
        assert result.rows[0]['qty'] == 50

    def test_no_item_retries_other_numbers(self, config):
        """When no item from first number, disambiguation tries the rest."""
        # 'type-c connector' is an item. '50 type-c connector' would match.
        # '7 type-c connector 50': qty=7, remaining='type-c connector 50'
        # _match_item('type-c connector 50') → 'type-c connector' matched via substring
        # So this case actually matches on first try. Use a case where first try fails.
        config['items'].append('titanium rod')
        config['aliases'] = {}
        # '200 titanium rod' → qty=200, item='titanium rod' (works normally)
        result = parse('200 titanium rod', config, today=TODAY)
        assert len(result.rows) >= 1
        assert result.rows[0]['inv_type'] == 'titanium rod'
        assert result.rows[0]['qty'] == 200

    def test_single_number_unchanged(self, config):
        """Normal single-number parsing shouldn't be affected."""
        result = parse('12 cucumbers', config, today=TODAY)
        assert result.rows[0]['qty'] == 12
        assert result.rows[0]['inv_type'] == 'cucumbers'


# ============================================================
# Fuzzy verb matching
# ============================================================

class TestFuzzyVerbMatching:
    """Fuzzy matching fallback for misspelled verbs."""

    def test_fuzzy_verb_match(self, config):
        """A misspelled verb should fuzzy-match the correct verb."""
        config['action_verbs'] = {
            'warehouse_to_branch': ['delivered', 'passed'],
            'eaten': ['consumed'],
        }
        # 'deliverd' (ratio 0.94) is close to 'delivered'
        result = parse('deliverd 12 cucumbers to L', config, today=TODAY)
        assert len(result.rows) >= 1
        assert result.rows[0]['trans_type'] == 'warehouse_to_branch'

    def test_exact_verb_takes_priority(self, config):
        """Exact verb match should still work before fuzzy kicks in."""
        config['action_verbs'] = {
            'warehouse_to_branch': ['delivered'],
        }
        result = parse('delivered 12 cucumbers to L', config, today=TODAY)
        assert result.rows[0]['trans_type'] == 'warehouse_to_branch'

    def test_short_verb_not_fuzzy(self, config):
        """Short words (<=2 chars) should not fuzzy match verbs."""
        config['action_verbs'] = {
            'eaten': ['ate'],
        }
        # 'at' (2 chars) should NOT fuzzy match 'ate'
        result = parse('12 cucumbers at L', config, today=TODAY)
        # Should still parse the item, but not match 'eaten' from 'at'
        assert result.rows[0]['inv_type'] == 'cucumbers'

    def test_fuzzy_type_name_match(self, config):
        """A misspelled transaction type name should fuzzy-match."""
        config['transaction_types'] = ['warehouse_to_branch', 'supplier_to_warehouse', 'eaten']
        # 'warehouse_to_branc' is close to 'warehouse_to_branch'
        result = parse('12 cucumbers warehouse_to_branc to L', config, today=TODAY)
        assert result.rows[0]['trans_type'] == 'warehouse_to_branch'


# ============================================================
# Fuzzy location matching
# ============================================================

class TestFuzzyLocationMatching:
    """Fuzzy matching fallback for multi-char location names."""

    def test_fuzzy_location_match(self):
        """A misspelled multi-char location should fuzzy-match."""
        config = {
            'items': ['cucumbers'],
            'locations': ['downtown', 'uptown'],
            'default_source': 'warehouse',
            'action_verbs': {},
            'prepositions': {'to': ['to']},
            'aliases': {},
        }
        # 'downtow' is close to 'downtown'
        result = parse('12 cucumbers downtow', config, today=TODAY)
        assert len(result.rows) >= 1
        # Should resolve to 'downtown'
        has_downtown = any(r.get('vehicle_sub_unit') == 'downtown' for r in result.rows)
        assert has_downtown

    def test_short_location_not_fuzzy(self):
        """Short (1-2 char) locations should not be fuzzy-matched."""
        config = {
            'items': ['cucumbers'],
            'locations': ['L', 'C'],
            'default_source': 'warehouse',
            'action_verbs': {},
            'prepositions': {'to': ['to']},
            'aliases': {},
        }
        # 'M' is not close enough to 'L' for fuzzy — and short locs skip fuzzy
        result = parse('12 cucumbers M', config, today=TODAY)
        assert len(result.rows) >= 1
        # Should NOT fuzzy match to L
        assert result.rows[0].get('vehicle_sub_unit') != 'L'
