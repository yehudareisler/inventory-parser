"""
Test cases for the inventory message parser.

Each test case defines:
- Input text (messy WhatsApp-style message)
- Expected parsed output (list of row dicts)
- Notes on what the test is exercising

These tests serve as the living specification for parser behavior.
They should be runnable as actual tests once the parser is implemented.
"""

# === Test 1: Simple consumption ===
#
# Input:
#   eaten by L 15.3.25
#   2 small boxes cherry tomatoes
#   4 cucumbers
#
# Expected output:
#   DATE=15.3.25  INV_TYPE=cherry tomatoes  QTY=2   TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#   DATE=15.3.25  INV_TYPE=cucumbers        QTY=4   TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#
# Exercises:
#   - Date extraction from message content (DD.M.YY format)
#   - "eaten by <unit>" pattern → TRANS_TYPE=eaten
#   - Quantity with container type ("2 small boxes")
#   - Multiple items under one header line
#   - Single batch for same destination


# === Test 2: Transfer with math expression ===
#
# Input:
#   passed 2x17 spaghetti noodles to L
#
# Expected output:
#   DATE=today  INV_TYPE=spaghetti  QTY=-34  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=spaghetti  QTY=+34  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=L          BATCH=1
#
# Exercises:
#   - Math expression evaluation: "2x17" → 34
#   - "passed X to Y" pattern → warehouse_to_branch
#   - Double-entry: auto-generates both source (warehouse) and destination rows
#   - Alias: "spaghetti noodles" → "spaghetti"
#   - Default source = warehouse


# === Test 3: Multiple destinations ===
#
# Input:
#   8 boxes of small pot to C
#   7 boxes of small potatoes to L
#
# Expected output:
#   DATE=today  INV_TYPE=small potatoes  QTY=-8  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=small potatoes  QTY=+8  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=C          BATCH=1
#   DATE=today  INV_TYPE=small potatoes  QTY=-7  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=2
#   DATE=today  INV_TYPE=small potatoes  QTY=+7  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=L          BATCH=2
#
# Exercises:
#   - Abbreviation: "small pot" → "small potatoes"
#   - Different destinations → different batches
#   - "X to Y" pattern
#   - Container type: "boxes" (quantity is count of boxes)


# === Test 4: Unparseable input ===
#
# Input:
#   4 82 95 3 1
#      37 19
#      70 3
#
# Expected behavior:
#   - Parser returns no rows
#   - Warning: "Could not parse this section"
#   - Raw text preserved for user to edit and retry
#
# Exercises:
#   - Graceful failure on incomprehensible input
#   - No crash, no garbage output
