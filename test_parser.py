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
# RESOLVED: TRANS_TYPE is ambiguous here. Parser should present best guess
# but flag for user to confirm. Source isn't specified so we can't distinguish
# supplier_to_warehouse from between_warehouses or a return from a branch.


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
# RESOLVED: TRANS_TYPE is ambiguous — parser should present what it can
# (item, qty) and flag TRANS_TYPE + VEHICLE_SUB_UNIT for user to fill in.


# === Test 9: Request / need (not a transaction) ===
#
# Input:
#   A need for 80 aluminum pans and 10000 amall potatoes
#
# Expected behavior:
#   - Parser detects this as a REQUEST, not a transaction
#   - Parses items and quantities (typo: "amall potatoes" → "small potatoes")
#   - Outputs to a SEPARATE request list, not the transaction table
#   - Still corrects typos, resolves aliases, converts units
#
# Exercises:
#   - "need for" pattern → detected as request
#   - Multiple items in one line ("X and Y")
#   - Typo correction in request context
#
# RESOLVED: Requests are a real feature but lower priority. They go to a
# separate output from transactions. Not in first iteration scope.


# === Test 10: Edited message with WhatsApp metadata ===
#
# Input:
#   8 boxes of small pot to C <This message was edited>
#
# Expected output:
#   DATE=today  INV_TYPE=small potatoes  QTY=-8  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=small potatoes  QTY=+8  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=C          BATCH=1
#
# Exercises:
#   - Strip WhatsApp metadata ("<This message was edited>")
#   - Abbreviation: "small pot" → "small potatoes"
#   - Normal transfer parsing after metadata removal
#   - Container: "boxes" — convert if conversion known


# === Test 11: Item list with no context ===
#
# Input:
#   4 froot loops
#   189 cornflakes
#   117 cheerios
#   3 cocoa puffs
#   1 trix
#
# Expected output:
#   DATE=???  INV_TYPE=froot loops   QTY=4    TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  BATCH=1
#   DATE=???  INV_TYPE=cornflakes    QTY=189  TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  BATCH=1
#   DATE=???  INV_TYPE=cheerios      QTY=117  TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  BATCH=1
#   DATE=???  INV_TYPE=cocoa puffs   QTY=3    TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  BATCH=1
#   DATE=???  INV_TYPE=trix          QTY=1    TRANS_TYPE=???  VEHICLE_SUB_UNIT=???  BATCH=1
#
# Exercises:
#   - No header line — no date, no truck, no transaction type
#   - Parser extracts what it can (items + quantities)
#   - All other fields flagged for user to fill in
#   - All items grouped in one batch (same implicit context)


# === Test 12: Fractional container transfer ===
#
# Input:
#   passed half a box of cherry tomatoes to L
#
# Expected output:
#   DATE=today  INV_TYPE=cherry tomatoes  QTY=-990   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=cherry tomatoes  QTY=+990   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=L          BATCH=1
#
# Exercises:
#   - Fractional container: "half a box" → 0.5 * box conversion
#   - If box→count conversion known (1 box = 1980), QTY = 990
#   - If conversion unknown, ask user
#   - "passed X to Y" → warehouse_to_branch with double-entry
#
# NOTE: Low priority — parser may optionally flag fractional containers
# with extra confidence warning since "half" is imprecise. But user
# reviews everything anyway so not critical.


# === Test 13: Communication note (not inventory) ===
#
# Input:
#   Rimon to N via naor by phone
#
# Expected behavior:
#   - Not a transaction, not a request
#   - Save as an unstructured note (preserved for reference)
#   - No rows generated in the transaction table
#
# Exercises:
#   - Parser recognizes this has no quantity, no item → not a transaction
#   - Doesn't crash or produce garbage rows
#   - Content is preserved as a note, not silently discarded


# === Test 14: Cryptic numbers without context ===
#
# Input:
#   4 82 95 3 1
#      37 19
#      70 3
#
# Expected behavior:
#   - Unparseable — numbers without item names or context
#   - Warn: "Could not parse this section"
#   - Display the raw text
#   - Offer option to EDIT the raw text and retry parsing
#     (user could add "these are cereals" or rewrite it entirely)
#
# Exercises:
#   - Graceful failure on ambiguous input
#   - Edit-and-retry workflow (user adds context, re-submits)
#
# NOTE: The tool processes one message at a time. It does NOT look at
# subsequent messages for context. If the user later pastes "these are
# the numbers of cereals", that's a separate parse. The user can instead
# edit this message to add that context before retrying.


# === Test 15: Mixed destinations in one paste ===
#
# Input:
#   passed 2x 17 spagetti noodles to L
#   passed half a box of cherry tomatoes to L
#   14 box of spuds to C
#
# Expected output:
#   Batch 1 (to L):
#   DATE=today  INV_TYPE=spaghetti        QTY=-34   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=spaghetti        QTY=+34   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=L          BATCH=1
#   DATE=today  INV_TYPE=cherry tomatoes  QTY=-990  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=1
#   DATE=today  INV_TYPE=cherry tomatoes  QTY=+990  TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=L          BATCH=1
#
#   Batch 2 (to C):
#   DATE=today  INV_TYPE=small potatoes   QTY=-14   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=warehouse  BATCH=2
#   DATE=today  INV_TYPE=small potatoes   QTY=+14   TRANS_TYPE=warehouse_to_branch  VEHICLE_SUB_UNIT=C          BATCH=2
#
# Exercises:
#   - Two destinations in one paste → two batches
#   - Same destination (L) groups into one batch
#   - Math: "2x 17" → 34 (space between multiplier and value)
#   - Alias: "spagetti" → "spaghetti", "spuds" → "small potatoes"
#   - Fractional container: "half a box" (conversion if known)
#   - Container: "14 box" = 14 boxes (convert if known)
#   - Double-entry for all three transfers
