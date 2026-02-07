"""Inventory message parser — Text User Interface.

Interactive review/edit workflow:
  paste message → parse → review table → edit if needed → confirm → done
"""

import re
import sys
from datetime import date
from string import ascii_lowercase

import yaml

from inventory_parser import parse


# ============================================================
# Config loading / saving
# ============================================================

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def save_config(config, path):
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)


# ============================================================
# Multi-line input
# ============================================================

def get_input():
    """Read multi-line paste. Empty line or Ctrl-D to finish."""
    print("\nPaste message (empty line to finish, 'exit' to quit):")
    lines = []
    try:
        while True:
            line = input()
            if line.strip().lower() == 'exit':
                return None
            if line.strip() == '' and lines:
                break
            if line.strip() != '':
                lines.append(line)
    except EOFError:
        pass
    return '\n'.join(lines) if lines else None


# ============================================================
# Table display
# ============================================================

FIELD_HEADERS = ['#', 'DATE', 'ITEM', 'QTY', 'TYPE', 'LOCATION', 'BATCH', 'NOTES']


def _format_date(d):
    if isinstance(d, date):
        return d.strftime('%Y-%m-%d')
    return str(d) if d else '???'


def _format_qty(q):
    if q is None:
        return '???'
    if isinstance(q, float) and q == int(q):
        return str(int(q))
    return str(q)


def _row_has_warning(row):
    return (row.get('trans_type') is None
            or row.get('vehicle_sub_unit') is None)


def _row_to_cells(i, row):
    warn = '\u26a0 ' if _row_has_warning(row) else ''
    return [
        f'{warn}{i + 1}',
        _format_date(row.get('date')),
        row.get('inv_type', '???'),
        _format_qty(row.get('qty')),
        row.get('trans_type') or '???',
        row.get('vehicle_sub_unit') or '???',
        str(row.get('batch', '')),
        row.get('notes') or '',
    ]


def display_result(rows, notes=None, unparseable=None):
    """Print the result table, notes, and warnings."""
    if not rows and not notes and not unparseable:
        print("\nNothing to display.")
        return

    if rows:
        # Build table data
        table = [FIELD_HEADERS]
        for i, row in enumerate(rows):
            table.append(_row_to_cells(i, row))

        # Calculate column widths
        widths = [max(len(r[c]) for r in table) for c in range(len(FIELD_HEADERS))]

        # Print header
        header = ' | '.join(h.ljust(w) for h, w in zip(FIELD_HEADERS, widths))
        print(f"\n{header}")
        print('-' * len(header))

        # Print rows
        for row_cells in table[1:]:
            line = ' | '.join(c.ljust(w) for c, w in zip(row_cells, widths))
            print(line)

    if notes:
        print()
        for note in notes:
            print(f'\U0001f4dd Note: "{note}"')

    if unparseable:
        print()
        for text in unparseable:
            print(f'\u26a0 Could not parse: "{text}"')


# ============================================================
# Math expression evaluator (for QTY editing)
# ============================================================

def eval_qty(text):
    """Evaluate a quantity expression: plain number, or NxN / N*N."""
    text = text.strip()
    m = re.match(r'^(\d+)\s*[x\u00d7*]\s*(\d+)$', text)
    if m:
        return int(m.group(1)) * int(m.group(2))
    try:
        val = float(text)
        return int(val) if val == int(val) else val
    except ValueError:
        return None


# ============================================================
# Date parsing (for DATE editing)
# ============================================================

def parse_date(text):
    """Parse a date string. Supports DD.MM.YY, DD.MM.YYYY, MM/DD/YY."""
    text = text.strip()

    m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})$', text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass

    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})$', text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # ISO format
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass

    return None


# ============================================================
# Field editing
# ============================================================

FIELD_CODES = {
    'd': 'date',
    'i': 'inv_type',
    'q': 'qty',
    't': 'trans_type',
    'l': 'vehicle_sub_unit',
    'n': 'notes',
    'b': 'batch',
}

CLOSED_SET_FIELDS = {'inv_type', 'trans_type', 'vehicle_sub_unit'}

# User-facing display names for internal field names
FIELD_DISPLAY_NAMES = {
    'inv_type': 'ITEM',
    'trans_type': 'TRANS TYPE',
    'vehicle_sub_unit': 'LOCATION',
    'qty': 'QTY',
    'date': 'DATE',
    'notes': 'NOTES',
    'batch': 'BATCH',
}


def edit_closed_set(field, options):
    """Show lettered options, return selected value."""
    display_name = FIELD_DISPLAY_NAMES.get(field, field.upper())
    print(f"\n{display_name}:")
    for i, opt in enumerate(options):
        letter = ascii_lowercase[i] if i < 26 else str(i)
        print(f"  [{letter}] {opt}")
    print()

    while True:
        choice = input("Enter letter (or Enter to cancel)> ").strip().lower()
        if not choice:
            print("  Edit cancelled.")
            return None  # cancel

        # Try letter
        idx = ord(choice[0]) - ord('a') if len(choice) == 1 and choice.isalpha() else -1
        if 0 <= idx < len(options):
            return options[idx]

        # Try typing the value directly
        for opt in options:
            if opt.lower().startswith(choice):
                return opt

        print(f"  Invalid choice. Enter a letter (a-{ascii_lowercase[min(len(options)-1, 25)]}).")


def edit_open_field(field, current_value):
    """Prompt for direct input. Returns new value or None to cancel."""
    display_name = FIELD_DISPLAY_NAMES.get(field, field.upper())
    current_display = current_value if current_value is not None else ''
    print(f"\n{display_name} (current: {current_display}, Enter to cancel)")
    raw = input("> ").strip()
    if not raw:
        print("  Edit cancelled.")
        return None  # cancel

    if field == 'qty':
        val = eval_qty(raw)
        if val is None:
            print("  Invalid quantity.")
            return None
        return val

    if field == 'date':
        val = parse_date(raw)
        if val is None:
            print("  Invalid date. Use DD.MM.YY or YYYY-MM-DD.")
            return None
        return val

    if field == 'batch':
        try:
            return int(raw)
        except ValueError:
            print("  Invalid batch number.")
            return None

    return raw  # notes


def get_closed_set_options(field, config):
    """Get the list of options for a closed-set field."""
    if field == 'inv_type':
        return config.get('items', [])
    if field == 'trans_type':
        return config.get('transaction_types', [])
    if field == 'vehicle_sub_unit':
        locs = list(config.get('locations', []))
        src = config.get('default_source', 'warehouse')
        if src not in locs:
            locs.insert(0, src)
        return locs
    return []


# ============================================================
# Double-entry partner detection
# ============================================================

def find_partner(rows, idx):
    """Find the double-entry partner of row at idx.

    Partner = same batch, same inv_type, opposite sign qty.
    Returns partner index or None.
    """
    row = rows[idx]
    batch = row.get('batch')
    item = row.get('inv_type')
    qty = row.get('qty')
    if batch is None or item is None or qty is None or qty == 0:
        return None

    for i, other in enumerate(rows):
        if i == idx:
            continue
        if (other.get('batch') == batch
                and other.get('inv_type') == item
                and other.get('qty') is not None
                and other['qty'] * qty < 0):
            return i
    return None


def update_partner(rows, idx, field, new_value):
    """Auto-update the double-entry partner after an edit."""
    partner_idx = find_partner(rows, idx)
    if partner_idx is None:
        return

    partner = rows[partner_idx]
    if field in ('inv_type', 'date', 'trans_type', 'batch'):
        partner[field] = new_value
    elif field == 'qty':
        # Partner gets the negated value
        if isinstance(new_value, (int, float)):
            partner['qty'] = -new_value
    # vehicle_sub_unit: don't auto-update (source/dest differ)


# ============================================================
# Alias learning
# ============================================================

def check_alias_opportunity(rows, original_tokens, config):
    """Check if any edited items should be saved as aliases.

    original_tokens: dict mapping row index → original raw item token from parser.
    """
    aliases = config.get('aliases', {})
    items = [i.lower() for i in config.get('items', [])]
    prompts = []

    for idx, original in original_tokens.items():
        if idx >= len(rows):
            continue
        canonical = rows[idx].get('inv_type', '')
        if not original or not canonical:
            continue
        # Don't offer to save placeholder values as aliases
        if original == '???' or canonical == '???':
            continue

        orig_lower = original.lower()
        canon_lower = canonical.lower()

        # Skip if already known
        if orig_lower == canon_lower:
            continue
        if orig_lower in (a.lower() for a in aliases):
            continue
        if orig_lower in items:
            continue

        prompts.append((original, canonical))

    return prompts


def prompt_save_aliases(prompts, config):
    """Ask user whether to save new aliases."""
    saved = False
    for original, canonical in prompts:
        resp = input(f'Save "{original}" \u2192 "{canonical}" as alias? [y/n] ').strip().lower()
        if resp == 'y':
            if 'aliases' not in config:
                config['aliases'] = {}
            config['aliases'][original] = canonical
            saved = True
    return saved


# ============================================================
# Help text
# ============================================================

HELP_TEXT = """\
Commands:
  c             Confirm and save all rows
  q             Quit (discard this parse)
  r             Edit raw text and re-parse
  <row><field>  Edit a field (e.g., 1i = edit item on row 1)
  x<row>        Delete a row (e.g., x1)
  +             Add a new empty row
  ?             Show this help

Field codes:
  d = date    i = item    q = qty      t = type
  l = location   n = notes   b = batch

Examples:
  1t   Edit transaction type on row 1
  2q   Edit quantity on row 2
  x3   Delete row 3
"""

HELP_TEXT_NOTES = """\
Commands:
  n   Save as note (keep the text for reference)
  e   Edit the raw text and re-parse
  s   Skip (discard this input)
  ?   Show this help
"""

HELP_TEXT_UNPARSEABLE = """\
Commands:
  e   Edit the raw text and re-parse
  s   Skip (discard this input)
  ?   Show this help
"""


# ============================================================
# Review loop
# ============================================================

def review_loop(result, raw_text, config):
    """Interactive review. Returns confirmed rows or None (quit)."""
    rows = list(result.rows)
    notes = list(result.notes)
    unparseable = list(result.unparseable)

    # Track original item tokens for alias learning
    # We need to get these from the parser — for now, track from initial state
    original_tokens = {}

    while True:
        display_result(rows, notes, unparseable)

        if not rows and not notes and unparseable:
            # Only unparseable content
            print("\n[e]dit and retry / [s]kip  (? for help)")
            cmd = input("> ").strip().lower()
            if cmd == '?' or cmd == 'h':
                print(HELP_TEXT_UNPARSEABLE)
                continue
            if cmd == 's':
                return None
            if cmd == 'e':
                rows, notes, unparseable = _edit_retry(raw_text, config)
                continue
            continue

        if not rows and notes and not unparseable:
            # Only notes
            print("\nNo transactions found.")
            print("Save as [n]ote / [e]dit and retry / [s]kip  (? for help)")
            cmd = input("> ").strip().lower()
            if cmd == '?' or cmd == 'h':
                print(HELP_TEXT_NOTES)
                continue
            if cmd == 'n':
                return {'rows': [], 'notes': notes}
            if cmd == 's':
                return None
            if cmd == 'e':
                rows, notes, unparseable = _edit_retry(raw_text, config)
                continue
            continue

        # Normal review
        print("\n[c]onfirm / edit (e.g. 1i) / [r]etry / [q]uit  (? for help)")
        cmd = input("> ").strip().lower()

        if cmd == '?' or cmd == 'h':
            print(HELP_TEXT)
            continue

        if cmd == 'c':
            # Warn about incomplete rows
            incomplete = [i + 1 for i, r in enumerate(rows)
                          if r.get('inv_type') == '???' or r.get('trans_type') is None
                          or r.get('vehicle_sub_unit') is None]
            if incomplete:
                row_list = ', '.join(str(n) for n in incomplete)
                resp = input(f"  Warning: Row(s) {row_list} have incomplete fields (???). Confirm anyway? [y/n] ").strip().lower()
                if resp != 'y':
                    continue

            if original_tokens:
                prompts = check_alias_opportunity(rows, original_tokens, config)
                if prompts:
                    prompt_save_aliases(prompts, config)
            return {'rows': rows, 'notes': notes}

        if cmd == 'q':
            return None

        if cmd == 'r':
            rows, notes, unparseable = _edit_retry(raw_text, config)
            continue

        if cmd == '+':
            rows.append(_empty_row())
            continue

        # Delete row: x<n>
        m = re.match(r'^x(\d+)$', cmd)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(rows):
                rows.pop(idx)
                print(f"  Row {idx + 1} deleted.")
            else:
                print(f"  Invalid row number.")
            continue

        # Edit field: <row><field_code>
        m = re.match(r'^(\d+)([diqtlnb])$', cmd)
        if m:
            row_num = int(m.group(1)) - 1
            field_code = m.group(2)
            field = FIELD_CODES[field_code]

            if row_num < 0 or row_num >= len(rows):
                print(f"  Invalid row number.")
                continue

            old_value = rows[row_num].get(field)
            old_item_token = rows[row_num].get('inv_type') if field == 'inv_type' else None

            if field in CLOSED_SET_FIELDS:
                options = get_closed_set_options(field, config)
                new_value = edit_closed_set(field, options)
            else:
                new_value = edit_open_field(field, old_value)

            if new_value is not None:
                # Find partner BEFORE changing the field (matching needs old value)
                partner_idx = find_partner(rows, row_num)
                rows[row_num][field] = new_value
                # Update partner directly
                if partner_idx is not None:
                    if field in ('inv_type', 'date', 'trans_type', 'batch'):
                        rows[partner_idx][field] = new_value
                    elif field == 'qty' and isinstance(new_value, (int, float)):
                        rows[partner_idx]['qty'] = -new_value

                # Track for alias learning
                if field == 'inv_type' and old_item_token and old_item_token != new_value:
                    original_tokens[row_num] = old_item_token

                display_name = FIELD_DISPLAY_NAMES.get(field, field)
                print(f"  Row {row_num + 1} {display_name.lower()} \u2192 {new_value}")
            continue

        print("  Unknown command. Type ? for help, or try e.g. 1i to edit item on row 1.")

    return None


def _empty_row():
    return {
        'date': date.today(),
        'inv_type': '???',
        'qty': 0,
        'trans_type': None,
        'vehicle_sub_unit': None,
        'batch': 1,
        'notes': None,
    }


def _edit_retry(raw_text, config):
    """Show raw text, let user edit, re-parse."""
    print(f"\nOriginal text:\n{raw_text}\n")
    print("Enter corrected text (empty line to finish):")
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == '' and lines:
                break
            if line.strip() != '':
                lines.append(line)
    except EOFError:
        pass

    if not lines:
        # No edit, re-parse original
        new_text = raw_text
    else:
        new_text = '\n'.join(lines)

    result = parse(new_text, config)
    return list(result.rows), list(result.notes), list(result.unparseable)


# ============================================================
# Main
# ============================================================

def main(config_path='config.yaml'):
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Create one based on config.yaml.example")
        sys.exit(1)

    print("=== Inventory Message Parser ===")
    print("Paste a WhatsApp message to parse. Type 'exit' to quit.\n")

    while True:
        raw_text = get_input()
        if raw_text is None:
            print("Goodbye.")
            break

        result = parse(raw_text, config)

        outcome = review_loop(result, raw_text, config)

        if outcome is None:
            print("  Discarded.")
            continue

        confirmed_rows = outcome.get('rows', [])
        confirmed_notes = outcome.get('notes', [])

        if confirmed_rows:
            print("\n=== Confirmed transactions ===")
            display_result(confirmed_rows)
            print(f"\n({len(confirmed_rows)} row(s) confirmed)")

        if confirmed_notes:
            for note in confirmed_notes:
                print(f'\U0001f4dd Saved note: "{note}"')

        # Save config if aliases were learned
        # (aliases are added to config dict in-place during review)
        save_config(config, config_path)


if __name__ == '__main__':
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'
    main(config_path)
