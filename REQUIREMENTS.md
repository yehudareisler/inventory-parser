# Inventory Message Parser — Requirements Document

## 1. Problem Statement

Managing inventory for a distributed network of branches/vehicles. Data arrives via unstructured WhatsApp messages with:
- Misspellings and typos
- Item nicknames (e.g., "spuds" for "small potatoes")
- Mixed units (count, boxes, kg, fractions like "half a box")
- Math expressions (e.g., "2x17", "11*920")
- Multiple entities in one message
- Implicit context (follow-up messages clarifying previous ones)
- Varying date formats

Currently: manual entry into Google Sheets. This is slow and error-prone.

Goal: Reduce friction by parsing messy text into structured data ready for review and sheet entry.

---

## 2. Users & Context

**Primary user:** Inventory manager (the developer of this tool)
**Secondary users:** Colleagues who view the Google Sheet

**Constraints:**
- Google Sheets remains the backend (colleagues need visibility)
- Must handle Hebrew-to-English translated content with flexibility
- Domain is confidential — tool must be configurable, not hardcoded to specific items

---

## 3. Scope

### Short-term (Python desktop tool)
- Paste messy text
- Parse into structured rows
- Display for review
- Allow editing with minimal keystrokes
- Output structured data (print/display, no Sheets integration)

### Long-term (Android app)
- Input via copy-paste, share intent, or direct typing
- Parse, display, edit (same as above)
- Push to Google Sheets via API (append only, never delete)

---

## 4. Data Schema

| Column | Type | Description |
|--------|------|-------------|
| DATE | date | Transaction date (prefer in-message date, else current time) |
| INV_TYPE | string (closed list) | Canonical item name (~50 items) |
| QTY | number | Quantity (positive or negative, supports expressions) |
| TRANS_TYPE | string (closed list) | Transaction type |
| VEHICLE_SUB_UNIT | string | Branch or vehicle identifier |
| NOTES | string (free text) | Optional notes |
| BATCH | integer | Auto-incrementing (previous batch + 1), groups related transactions |

### Transaction Types (configurable)
- `starting_point` — initial baseline (non-zero-sum: items appear)
- `recount` — inventory count adjustment (non-zero-sum, unless moved to "lost")
- `warehouse_to_branch`
- `supplier_to_warehouse`
- `eaten` — consumption (non-zero-sum: items leave the system)
- `between_branch`
- `between_warehouses`
- `inside_branch`

### Non-Zero-Sum Transactions
Three transaction types don't require double-entry:
- **starting_point**: Items appear from initial baseline
- **eaten**: Items leave the system (consumed)
- **recount**: Discrepancies can either:
  - Create non-zero-sum entries (items appear/disappear), OR
  - Move items to/from a "lost" location (zero-sum, preserves audit trail) — user chooses

### Hierarchy
- Branches contain vehicles
- VEHICLE_SUB_UNIT granularity varies (sometimes branch, sometimes specific vehicle)

---

## 5. Parsing Requirements

### Input formats
- Free-form text (WhatsApp message style)
- May contain multiple lines
- May reference multiple trucks/branches in one message

### The parser must handle:

**Item name variations:**
- Misspellings: "smalal potatoes" → "small potatoes"
- Nicknames: "spuds" → "small potatoes"
- Abbreviations: "small pot" → "small potatoes"
- System learns aliases over time (no predefined alias list)
- Output always uses canonical names

**Quantities:**
- Plain numbers: "4 cucumbers"
- With units: "8 boxes", "2 small boxes", "half a box"
- Math expressions: "2x17" → 34, "11*920" → 10120
- Unit shortcuts during editing: possibly "5b" = 5 boxes

**Container/unit types:**
- A single item may have multiple container types (e.g., "small box" vs "large box" of cherry tomatoes)
- Learn container types as they come up (similar to alias learning)
- If ambiguous which container type is meant, ask the user for clarification
- Store learned container types per item in config

**Dates:**
- Various formats: "15.3.25", "3/16/25"
- Prefer date written in message content
- Fall back to current time if no date specified

**Transaction type inference:**
- "eaten by L" → TRANS_TYPE = eaten, VEHICLE_SUB_UNIT = L
- "to C" → TRANS_TYPE = warehouse_to_branch (default source = warehouse)
- "from supplier" → TRANS_TYPE = supplier_to_warehouse
- "gathered into warehouse" → receiving at warehouse

**Multi-entity messages:**
- "truck A: 3 items... truck B: 4 items..." → separate by entity
- Infer entity scope from context

---

## 6. Double-Entry Bookkeeping

For **transfer** transactions, auto-generate **both** sides:

Example: "passed 34 spaghetti to L"
```
| DATE  | INV_TYPE  | QTY | TRANS_TYPE          | VEHICLE_SUB_UNIT | BATCH     |
|-------|-----------|-----|---------------------|------------------|-----------|
| 3/19  | spaghetti | -34 | warehouse_to_branch | warehouse        | batch_001 |
| 3/19  | spaghetti | +34 | warehouse_to_branch | L                | batch_001 |
```

**Rules:**
- Default source = warehouse (unless explicitly stated)
- Batch ID = auto-incrementing integer, assigned by destination within same message
- Transfer transactions must sum to zero per batch (sanity check)
- Non-zero-sum transactions (starting_point, eaten, recount without "lost") are single-row

---

## 7. UX / Interaction Model

### Display
Compact table view:
```
[1] 3/19 | spaghetti     | -34  | warehouse_to_branch | warehouse | batch_001
[2] 3/19 | spaghetti     | +34  | warehouse_to_branch | L         | batch_001
[3] 3/19 | cherry tom    | -0.5 | warehouse_to_branch | warehouse | batch_001
[4] 3/19 | cherry tom    | +0.5 | warehouse_to_branch | L         | batch_001
```

### Editing (minimal keystrokes)

**Select field to edit:** `<row><field>` e.g., `1t` = edit TRANS_TYPE on row 1

**Field codes:**
- `d` = DATE
- `i` = INV_TYPE
- `q` = QTY
- `t` = TRANS_TYPE
- `v` = VEHICLE_SUB_UNIT
- `n` = NOTES
- `b` = BATCH

**Closed-set fields (INV_TYPE, TRANS_TYPE, VEHICLE_SUB_UNIT):**
```
TRANS_TYPE: [a] eaten [b] warehouse_to_branch [c] between_branch [d] ...
> _
```
Single keypress to select.

**Open fields (QTY, NOTES):**
- Direct input
- QTY accepts expressions: `2x17` → 34

**Row operations:**
- `x1` = delete row 1
- `+` = add new row
- `c` = confirm and proceed

### Error handling for unparseable input
- Skip unparseable sections
- Warn user with the unparseable text shown
- Option to edit the raw text and retry parsing

---

## 8. Alias Learning

- User maintains a config file with ~50 canonical item names
- When parser encounters unknown term:
  1. Fuzzy match against canonical names
  2. Suggest best match
  3. If user confirms/corrects, store the alias
- Aliases stored in config file for future use
- Canonical names are the only values that appear in output

---

## 9. Configuration

The tool must be configurable (not hardcoded). Config file(s) define:

```yaml
items:
  - small potatoes
  - cherry tomatoes
  - sweet cherry tomatoes
  - spaghetti
  - ...

transaction_types:
  - starting_point
  - recount
  - warehouse_to_branch
  - supplier_to_warehouse
  - eaten
  - between_branch
  - between_warehouses
  - inside_branch

locations:
  warehouse: true  # default source
  branches:
    - L
    - C
    - N
    - ...

learned_aliases:
  spuds: small potatoes
  small pot: small potatoes
  cherry tom: cherry tomatoes
  ...

container_types:
  cherry tomatoes:
    - small box
    - large box
  small potatoes:
    - box
    - bag
  ...
```

---

## 10. Success Criteria

1. **Faster than manual entry** — pasting a typical message and confirming should take < 30 seconds
2. **Fewer errors** — parser catches typos and suggests corrections
3. **Handles real messiness** — the example messages from the conversation should parse correctly
4. **Minimal keystrokes** — editing a field should take 2-3 keypresses
5. **Learnable** — aliases improve over time with use
6. **Auditable** — user always reviews before committing

---

## 11. Development Approach

1. **Write Python tests first** — example conversations/interactions that define expected behavior
2. **Implement parser** — handles the messy input → structured output
3. **Implement TUI** — text-based interface for review and editing
4. **Iterate** — refine based on real usage

---

## 12. Test Cases

All test cases live in `test_parser.py` (single source of truth).

---

## Next Steps

1. Expand test cases in `test_parser.py`
2. Implement the short-term desktop tool
