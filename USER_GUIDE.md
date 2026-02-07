# Inventory Message Parser — User Guide

## What is this?

A tool that parses messy inventory messages (WhatsApp-style) into structured transaction rows. You paste a message, review the parsed table, fix anything that's wrong, and confirm.

## Quick start

```
python3 inventory_tui.py
```

## Workflow

### 1. Paste a message

When prompted, paste the inventory message. Press Enter on an empty line to finish.

```
Paste message (empty line to finish, 'exit' to quit):
eaten by L 15.3.25
2 small boxes cherry tomatoes
4 cucumbers

```

### 2. Review the table

The parser outputs a table of transactions:

```
#  | DATE       | ITEM            | QTY  | TYPE  | LOCATION | BATCH | NOTES
---------------------------------------------------------------------------
1  | 2025-03-15 | cherry tomatoes | 1980 | eaten | L        | 1     |
2  | 2025-03-15 | cucumbers       | 4    | eaten | L        | 1     |

[c]onfirm / edit (e.g. 1i) / [r]etry / [q]uit  (? for help)
>
```

- Rows with missing data show `???` and a `⚠` warning flag
- Notes (non-transaction text) appear below the table
- Unparseable lines are shown as warnings

### 3. Choose an action

| Command | What it does |
|---------|-------------|
| `c` | **Confirm** — accept the rows as shown |
| `q` | **Quit** — discard and start over |
| `r` | **Retry** — edit the raw text and re-parse |
| `?` | **Help** — show all available commands |

### 4. Edit fields (if needed)

To edit a specific cell, type the **row number** followed by a **field code**:

```
> 1t
```

This means: edit the **t**ype (transaction type) on row **1**.

**Field codes:**

| Code | Field |
|------|-------|
| `d` | Date |
| `i` | Item name |
| `q` | Quantity |
| `t` | Transaction type |
| `l` | Location |
| `n` | Notes |
| `b` | Batch |

**For item, type, and location** — you'll see a list of options:
```
TRANS TYPE:
  [a] starting_point
  [b] recount
  [c] warehouse_to_branch
  ...
Enter letter (or Enter to cancel)> e
```
Type the letter next to your choice. Press Enter with no input to cancel.

**For quantity** — type a number or math expression:
```
QTY (current: 4, Enter to cancel)
> 2x17
  Row 1 qty → 34
```

### 5. Row operations

| Command | What it does |
|---------|-------------|
| `x1` | Delete row 1 |
| `+` | Add a new empty row |

### 6. Special cases

**Note-only input** (no items or quantities detected):
```
No transactions found.
Save as [n]ote / [e]dit and retry / [s]kip
```

**Unparseable input** (numbers without item names):
```
⚠ Could not parse: "4 82 95 3 1"
[e]dit and retry / [s]kip
```

## What the parser understands

- **Items**: Matches against a configured list. Handles typos (fuzzy match), abbreviations ("small pot" → "small potatoes"), and learned aliases ("spuds" → "small potatoes")
- **Quantities**: Plain numbers, math (`2x17` → 34, `11*920` → 10120), containers (`8 boxes` × conversion factor), fractions (`half a box`)
- **Dates**: `15.3.25`, `3/15/25` — extracted from the message, or defaults to today
- **Actions**: "passed to L" → transfer, "eaten by L" → consumption, "received" → supplier delivery
- **Destinations**: Matched against configured locations (L, C, N, warehouse, etc.)
- **Double-entry**: Transfers automatically generate both source and destination rows (source row shows negative quantity, destination shows positive)
- **Batches**: Items within the same delivery/action are grouped by batch number. The batch increments when the destination or date changes

## Configuration

Edit `config.yaml` to customize:
- `items` — canonical item names
- `aliases` — learned nickname mappings
- `locations` — branch/vehicle identifiers
- `action_verbs` — words that map to transaction types
- `unit_conversions` — container-to-base-unit conversion factors
