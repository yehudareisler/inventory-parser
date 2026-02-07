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

### Future scope (not first iteration)
- **Request/need tracking:** Parser detects requests ("need for 80 aluminum pans") and outputs to a separate list from transactions. Same item resolution and alias handling. Potentially includes priority ranking. Separate table/output from transaction data.

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

### Input format
- Loose structure — parts (qty, item, destination, action verb) can appear in any order
- Parser identifies parts by matching against configurable term lists
- NOT fully freeform prose — there's an expected set of tokens, but order is flexible
- Multi-line input: each line parsed independently, then context is broadcast (see below)

### Part identification

The parser tokenizes each line and identifies parts by matching against config:

- **Quantity**: numbers, math expressions (`2x17`, `11*920`), fractions (`half`)
  - If no quantity found but a known item is found, default qty = 1
- **Item**: matched against canonical item list + learned aliases (fuzzy for typos)
- **Destination/source**: matched against location list (`L`, `C`, `N`, `warehouse`, etc.)
- **Action verb**: matched against configurable verb lists per transaction type

### Action verb lists (configurable)

```yaml
action_verbs:
  warehouse_to_branch: [passed, gave, sent, delivered]
  supplier_to_warehouse: [received, got]
  eaten: [eaten, consumed, used]
  # no verb → default action (warehouse_to_branch)
```

All verb lists live in config. User can edit them in one central location.

### Parse outcome classification

Each line falls into one of three categories:

1. **Successful parse**: qty + known item identified → generate rows
2. **Partial parse**: qty or known item found, but something is missing/unknown → generate rows with warnings (⚠ flags on unknown fields)
3. **Note**: no qty AND no known item → suggest saving as a note

### Context broadcasting

When parsing multi-line input:
- Context (destination, source, date, action verb) is extracted from every line
- Lines without their own context inherit from the **last seen** value
- Lines with explicit context keep their own
- A note line can still contribute context (e.g., "Rimon to N via naor by phone" provides destination N)
- Batch number changes when destination changes

### The parser must handle:

**Item name variations:**
- Misspellings: "smalal potatoes" → "small potatoes" (fuzzy match)
- Abbreviations: "small pot" → "small potatoes" (prefix/substring match)
- Nicknames: "spuds" → "small potatoes" (only if previously learned as alias)
- Unrecognized items: flagged with ⚠, user corrects during review
- Output always uses canonical names

**Quantities:**
- Plain numbers: "4 cucumbers"
- With units: "8 boxes", "2 small boxes", "half a box"
- Math expressions: "2x17" → 34, "11*920" → 10120
- Default qty = 1 when item is recognized but no number present
- Unit shortcuts during editing: possibly "5b" = 5 boxes

**Container/unit types and conversion:**
- A single item may have multiple container types (e.g., "small box" vs "large box" of cherry tomatoes)
- Learn container types as they come up (similar to alias learning)
- If ambiguous which container type is meant, ask the user for clarification
- Store learned container types per item in config
- Each item has a base unit (e.g., count); QTY is always stored in the base unit
- Conversion factors are stored per item per container type (e.g., 1 box of small potatoes = 920 count)
- If conversion factor is known, auto-convert (e.g., "8 boxes" → QTY=7360)
- If conversion factor is unknown, ask the user and save for future reuse

**Dates:**
- Various formats: "15.3.25", "3/16/25"
- Prefer date written in message content
- Fall back to current time if no date specified

**Transaction type inference:**
- Determined by action verb matching against configurable verb lists
- "eaten by L" → TRANS_TYPE = eaten, VEHICLE_SUB_UNIT = L
- "to C" → TRANS_TYPE = warehouse_to_branch (default source = warehouse)
- "from supplier" → TRANS_TYPE = supplier_to_warehouse
- "gathered into warehouse" → receiving at warehouse
- No verb → default transaction type (configurable, default: warehouse_to_branch)

**Multi-entity messages:**
- "truck A: 3 items... truck B: 4 items..." → separate by entity
- Infer entity scope from context

**WhatsApp metadata:**
- Strip known metadata patterns (e.g., `<This message was edited>`) before parsing

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
- Batch ID = auto-incrementing integer, new batch on change of destination OR date
- Transfer transactions must sum to zero per batch (sanity check)
- Non-zero-sum transactions (starting_point, eaten, recount without "lost") are single-row

---

## 7. UX / Interaction Model

### Overall flow

Every parse goes through review. No auto-commit.

```
paste message → parse → review → edit if needed → confirm → done
```

### Parse result display

Three possible outcomes after parsing:

**1. Successful parse — table shown:**
```
[1] today | spaghetti | -34 | warehouse_to_branch | warehouse | 1
[2] today | spaghetti | +34 | warehouse_to_branch | L         | 1
[c]onfirm / [e]dit / [q]uit
```

**2. Partial parse — table with warnings:**
```
[1] today | ⚠ spud | -1 | warehouse_to_branch | warehouse | 1
[2] today | ⚠ spud | +1 | warehouse_to_branch | C         | 1

⚠ Unknown item: "spud"
[c]onfirm / [e]dit / [q]uit
```

**3. Not a transaction — note suggestion:**
```
⚠ Could not parse as transaction (no quantity, no known item)
Save as [n]ote / [e]dit and retry / [s]kip
```

Notes extracted alongside transactions are shown below the table:
```
[1] today | cucumber       | -1 | warehouse_to_branch | warehouse | 1
[2] today | cucumber       | +1 | warehouse_to_branch | N         | 1

📝 Note: "Rimon to N via naor by phone"
[c]onfirm / [e]dit / [q]uit
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

### Edit and retry (raw text)

When input is fully unparseable:
- User can edit the raw text and re-submit for parsing
- If the user changes a token (e.g., replaces "spuds" with "small potatoes") while the rest of the line structure stays the same, prompt to save as alias

### Alias learning during review

When the user corrects an unknown item during review (either via field edit or raw text edit-and-retry):
1. Compare original token to the corrected canonical name
2. If the line structure remained the same (item substitution only, even if multiple fields changed), prompt:
   ```
   Save "spuds" → "small pototes"? [y/n]
   ```
3. If yes, alias is stored in config for future use
4. Editing item on one row of a double-entry pair auto-updates the other row

---

## 8. Alias Learning

- User maintains a config file with ~50 canonical item names
- **Typos** (close to a canonical name): fuzzy-matched automatically (e.g., "spagetti" → "spaghetti")
- **Abbreviations** (prefix of canonical name): matched automatically (e.g., "small pot" → "small potatoes")
- **Nicknames** (unrelated words): NOT auto-matched. Parser flags as unknown item. User corrects during review, then prompted to save as alias.
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

unit_conversions:
  cherry tomatoes:
    base_unit: count
    small box: 990    # 1 small box = 990 count
    large box: 1980
  small potatoes:
    base_unit: count
    box: 920
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
