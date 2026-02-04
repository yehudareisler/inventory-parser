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
#   - Container type: "boxes" — converted to base unit if conversion known
#
# NOTE: If box→count conversion is known (1 box = 920 count), expected QTY
# would be -7360/+7360 and -6440/+6440 instead. This test assumes conversion
# is NOT yet known, so the tool should ask the user for it.


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


# === Test 5: Supplier delivery with typo and math ===
#
# Input:
#   11*920
#   smalal potatoes
#   that's what got from Ran Serah
#
# Expected output:
#   DATE=today  INV_TYPE=small potatoes  QTY=+10120  TRANS_TYPE=supplier_to_warehouse  VEHICLE_SUB_UNIT=warehouse  NOTES=from Ran Serah  BATCH=1
#
# Exercises:
#   - Math expression: "11*920" → 10120
#   - Typo correction: "smalal potatoes" → "small potatoes"
#   - Multi-line context: quantity on one line, item on next, source on third
#   - "got from X" pattern → supplier_to_warehouse
#   - Supplier name extracted into NOTES
#   - Non-zero-sum (single row, items enter the system)


# === Test 6: Multi-date consumption (same truck, different dates) ===
#
# Input:
#   eaten by L 15.3.25
#   2 small boxes cherry tomatoes
#   4 cucumbers
#   8 boxes of small potatoes
#   1 sweet cherry tomatoes
#   4 chicken
#
#   eaten by L 16.3.25
#   1980 cherry tomatoes
#   4 cucumbers
#   1610 small potatoes
#   990 sweet cherry tomatoes
#   4 chicken
#
# Expected output:
#   Batch 1 (L, 15.3.25):
#   DATE=15.3.25  INV_TYPE=cherry tomatoes        QTY=2     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#   DATE=15.3.25  INV_TYPE=cucumbers              QTY=4     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#   DATE=15.3.25  INV_TYPE=small potatoes         QTY=8     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#   DATE=15.3.25  INV_TYPE=sweet cherry tomatoes   QTY=1     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#   DATE=15.3.25  INV_TYPE=chicken                QTY=4     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=1
#
#   Batch 2 (L, 16.3.25):
#   DATE=16.3.25  INV_TYPE=cherry tomatoes        QTY=1980  TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=2
#   DATE=16.3.25  INV_TYPE=cucumbers              QTY=4     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=2
#   DATE=16.3.25  INV_TYPE=small potatoes         QTY=1610  TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=2
#   DATE=16.3.25  INV_TYPE=sweet cherry tomatoes   QTY=990   TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=2
#   DATE=16.3.25  INV_TYPE=chicken                QTY=4     TRANS_TYPE=eaten  VEHICLE_SUB_UNIT=L  BATCH=2
#
# Exercises:
#   - Same truck, different dates → separate batches
#   - "eaten by <unit> <date>" header scopes subsequent lines
#   - Mix of units: "2 small boxes cherry tomatoes" vs "1980 cherry tomatoes"
#     (first uses container, second uses base count — both valid)
#   - "8 boxes of small potatoes" needs unit conversion if known
#   - 5 items per batch, 10 rows total
#
# NOTE on units: "2 small boxes cherry tomatoes" QTY depends on whether
# the small_box→count conversion is known. If known (e.g., 990), QTY=1980.
# If not known, the tool asks. Similarly "8 boxes of small potatoes".


# === Test 7: Warehouse receiving ===
#
# Input:
#   + 3 boxes of small potatoes gathered into the warehouse
#
# Expected output:
#   DATE=today  INV_TYPE=small potatoes  QTY=+3  TRANS_TYPE=supplier_to_warehouse  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#
# Exercises:
#   - "+ X gathered into the warehouse" pattern
#   - QTY is positive (items entering warehouse)
#   - Container: "boxes" — convert if conversion known
#
# NOTE: Is this supplier_to_warehouse or a different trans_type?
# The "+" and "gathered into" suggest receiving, but source isn't specified.


# === Test 8: Partial withdrawal ===
#
# Input:
#   took 5 out of 9 carrots
#
# Expected output:
#   DATE=today  INV_TYPE=carrots  QTY=5  TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  NOTES=had 9 total  BATCH=1
#
# Exercises:
#   - "took X out of Y" pattern — QTY=X (amount taken), Y is context
#   - Y (the total/original count) goes into NOTES as useful context
#   - TRANS_TYPE and VEHICLE_SUB_UNIT are ambiguous — needs user input
#
# OPEN QUESTION: What trans_type is "took 5 out of 9 carrots"?
# Is it warehouse_to_branch? eaten? Does it depend on context?


# === Test 9: Request / need (not a transaction) ===
#
# Input:
#   A need for 80 aluminum pans and 10000 amall potatoes
#
# Expected behavior:
#   - This is a REQUEST, not an actual transaction
#   - Should it be parsed into rows with a special trans_type like "request"?
#   - Or flagged as non-transactional and skipped?
#   - Typo: "amall potatoes" → "small potatoes"
#
# OPEN QUESTION: How should requests/needs be handled?
