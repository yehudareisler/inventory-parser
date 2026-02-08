"""Inventory message parser — Text User Interface.

Interactive review/edit workflow:
  paste message → parse → review table → edit if needed → confirm → done
"""

import re
import sys
from datetime import date

import yaml

from inventory_parser import parse


# ============================================================
# UI Strings — all user-facing text, configurable per language
# ============================================================

_EN_DEFAULTS = {
    'commands': {
        'confirm': 'c',
        'quit': 'q',
        'retry': 'r',
        'edit': 'e',
        'save_note': 'n',
        'skip': 's',
        'delete_prefix': 'x',
        'add_row': '+',
        'help': '?',
        'yes': 'y',
        'no': 'n',
    },
    'field_codes': {
        'd': 'date',
        'i': 'inv_type',
        'q': 'qty',
        't': 'trans_type',
        'l': 'vehicle_sub_unit',
        'n': 'notes',
        'b': 'batch',
    },
    'field_display_names': {
        'inv_type': 'ITEM',
        'trans_type': 'TRANS TYPE',
        'vehicle_sub_unit': 'LOCATION',
        'qty': 'QTY',
        'date': 'DATE',
        'notes': 'NOTES',
        'batch': 'BATCH',
    },
    'table_headers': ['#', 'DATE', 'ITEM', 'QTY', 'TYPE', 'LOCATION', 'BATCH', 'NOTES'],
    'option_letters': 'abcdefghijklmnopqrstuvwxyz',
    'strings': {
        'paste_prompt': "\nPaste message (empty line to finish, 'exit' to quit):",
        'exit_word': 'exit',
        'nothing_to_display': '\nNothing to display.',
        'note_prefix': 'Note',
        'unparseable_prefix': 'Could not parse',
        'saved_note_prefix': 'Saved note',
        'no_transactions': '\nNo transactions found.',
        'review_prompt': '\n[c]onfirm / edit (e.g. 1i) / [r]etry / [q]uit  (? for help)',
        'notes_only_prompt': 'Save as [n]ote / [e]dit and retry / [s]kip  (? for help)',
        'unparseable_prompt': '\n[e]dit and retry / [s]kip  (? for help)',
        'confirm_incomplete_warning': '  Warning: Row(s) {row_list} have incomplete fields (???). Confirm anyway? [{yes}/{no}] ',
        'enter_letter_prompt': 'Enter letter (or Enter to cancel)> ',
        'edit_cancelled': '  Edit cancelled.',
        'invalid_choice': '  Invalid choice. Enter a letter ({first}-{last}).',
        'open_field_prompt': '\n{display_name} (current: {current}, Enter to cancel)',
        'invalid_quantity': '  Invalid quantity.',
        'invalid_date': '  Invalid date. Use DD.MM.YY or YYYY-MM-DD.',
        'invalid_batch': '  Invalid batch number.',
        'row_deleted': '  Row {num} deleted.',
        'invalid_row': '  Invalid row number.',
        'row_updated': '  Row {num} {field} \u2192 {value}',
        'unknown_command': '  Unknown command. Type ? for help, or try e.g. 1{example_field} to edit {example_name} on row 1.',
        'original_text_label': '\nOriginal text:\n{text}\n',
        'enter_corrected_text': 'Enter corrected text (empty line to finish):',
        'save_alias_prompt': 'Save "{original}" \u2192 "{canonical}" as alias? [{yes}/{no}] ',
        'title': '=== Inventory Message Parser ===',
        'subtitle': "Paste a WhatsApp message to parse. Type 'exit' to quit.\n",
        'goodbye': 'Goodbye.',
        'discarded': '  Discarded.',
        'confirmed_title': '\n=== Confirmed transactions ===',
        'confirmed_count': '\n({count} row(s) confirmed)',
        'config_not_found': 'Config file not found: {path}',
        'config_hint': 'Create one based on config.yaml.example',
        # Help text building blocks
        'help_commands_header': 'Commands:',
        'help_field_codes_header': 'Field codes:',
        'help_examples_header': 'Examples:',
        'help_confirm_desc': 'Confirm and save all rows',
        'help_quit_desc': 'Quit (discard this parse)',
        'help_retry_desc': 'Edit raw text and re-parse',
        'help_edit_desc': 'Edit a field (e.g., {example})',
        'help_delete_desc': 'Delete a row (e.g., {example})',
        'help_add_desc': 'Add a new empty row',
        'help_help_desc': 'Show this help',
        'help_save_note_desc': 'Save as note (keep the text for reference)',
        'help_skip_desc': 'Skip (discard this input)',
        'help_items_header': 'Known items:',
        'help_aliases_header': 'Aliases:',
    },
}


class UIStrings:
    """All user-facing strings, commands, and field codes.

    Reads from config['ui'] if present; falls back to English defaults.
    """

    def __init__(self, config):
        ui = config.get('ui', {})
        self.commands = {**_EN_DEFAULTS['commands'], **ui.get('commands', {})}
        self.field_codes = ui.get('field_codes', _EN_DEFAULTS['field_codes'])
        self.field_display_names = {
            **_EN_DEFAULTS['field_display_names'],
            **ui.get('field_display_names', {}),
        }
        self.table_headers = ui.get('table_headers', _EN_DEFAULTS['table_headers'])
        self.option_letters = ui.get('option_letters', _EN_DEFAULTS['option_letters'])
        self.strings = {**_EN_DEFAULTS['strings'], **ui.get('strings', {})}
        self.items = config.get('items', [])
        self.aliases = config.get('aliases', {})

        # Pre-build regex helpers
        self._field_code_chars = ''.join(re.escape(c) for c in self.field_codes.keys())
        self._delete_prefix = re.escape(self.commands['delete_prefix'])

        # Reverse lookup: field code letter → internal field name
        self._field_code_to_field = dict(self.field_codes)

        # Build help texts
        self.help_text = self._build_help()
        self.help_text_notes = self._build_help_notes()
        self.help_text_unparseable = self._build_help_unparseable()

    def s(self, key, **kwargs):
        """Get a UI string, with optional format substitution."""
        template = self.strings.get(key, key)
        if kwargs:
            return template.format(**kwargs)
        return template

    def field_name(self, internal_name):
        return self.field_display_names.get(internal_name, internal_name.upper())

    def _first_field_code_for(self, internal_name):
        """Find the letter code for a given internal field name."""
        for letter, field in self.field_codes.items():
            if field == internal_name:
                return letter
        return '?'

    def _build_help(self):
        c = self.commands
        # Find example field code for item
        item_code = self._first_field_code_for('inv_type')
        type_code = self._first_field_code_for('trans_type')
        qty_code = self._first_field_code_for('qty')
        del_pfx = c['delete_prefix']

        # Build field code display lines
        fc_lines = []
        for letter, field in self.field_codes.items():
            fc_lines.append(f'  {letter} = {self.field_name(field).lower()}')

        lines = [
            self.s('help_commands_header'),
            f'  {c["confirm"]:14s} {self.s("help_confirm_desc")}',
            f'  {c["quit"]:14s} {self.s("help_quit_desc")}',
            f'  {c["retry"]:14s} {self.s("help_retry_desc")}',
            f'  {"<#><field>":14s} {self.s("help_edit_desc", example=f"1{item_code}")}',
            f'  {del_pfx + "<#>":14s} {self.s("help_delete_desc", example=f"{del_pfx}1")}',
            f'  {c["add_row"]:14s} {self.s("help_add_desc")}',
            f'  {c["help"]:14s} {self.s("help_help_desc")}',
            '',
            self.s('help_field_codes_header'),
            *fc_lines,
            '',
            self.s('help_examples_header'),
            f'  1{type_code}   {self.s("help_edit_desc", example=f"1{type_code}")}',
            f'  2{qty_code}   {self.s("help_edit_desc", example=f"2{qty_code}")}',
            f'  {del_pfx}3   {self.s("help_delete_desc", example=f"{del_pfx}3")}',
        ]
        if self.items:
            lines.append('')
            lines.append(self.s('help_items_header'))
            for item in self.items:
                aliases_for = [a for a, canon in self.aliases.items()
                               if canon == item]
                if aliases_for:
                    lines.append(f'  {item}  ({", ".join(aliases_for)})')
                else:
                    lines.append(f'  {item}')
        return '\n'.join(lines)

    def _build_help_notes(self):
        c = self.commands
        edit_cmd = c.get('edit', c['retry'])
        lines = [
            self.s('help_commands_header'),
            f'  {c["save_note"]:6s} {self.s("help_save_note_desc")}',
            f'  {edit_cmd:6s} {self.s("help_retry_desc")}',
            f'  {c["skip"]:6s} {self.s("help_skip_desc")}',
            f'  {c["help"]:6s} {self.s("help_help_desc")}',
        ]
        return '\n'.join(lines)

    def _build_help_unparseable(self):
        c = self.commands
        edit_cmd = c.get('edit', c['retry'])
        lines = [
            self.s('help_commands_header'),
            f'  {edit_cmd:6s} {self.s("help_retry_desc")}',
            f'  {c["skip"]:6s} {self.s("help_skip_desc")}',
            f'  {c["help"]:6s} {self.s("help_help_desc")}',
        ]
        return '\n'.join(lines)


# ============================================================
# Config loading / saving
# ============================================================

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_config(config, path):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)


# ============================================================
# Multi-line input
# ============================================================

def get_input(ui):
    """Read multi-line paste. Empty line or Ctrl-D to finish."""
    print(ui.s('paste_prompt'))
    exit_word = ui.s('exit_word').lower()
    lines = []
    try:
        while True:
            line = input()
            if line.strip().lower() == exit_word:
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

CLOSED_SET_FIELDS = {'inv_type', 'trans_type', 'vehicle_sub_unit'}


def format_date(d):
    if isinstance(d, date):
        return d.strftime('%Y-%m-%d')
    return str(d) if d else '???'


def format_qty(q):
    if q is None:
        return '???'
    if isinstance(q, float) and q == int(q):
        return str(int(q))
    return str(q)


def row_has_warning(row):
    return (row.get('trans_type') is None
            or row.get('vehicle_sub_unit') is None)


def _row_to_cells(i, row):
    warn = '\u26a0 ' if row_has_warning(row) else ''
    return [
        f'{warn}{i + 1}',
        format_date(row.get('date')),
        row.get('inv_type', '???'),
        format_qty(row.get('qty')),
        row.get('trans_type') or '???',
        row.get('vehicle_sub_unit') or '???',
        str(row.get('batch', '')),
        row.get('notes') or '',
    ]


def display_result(rows, notes=None, unparseable=None, ui=None):
    """Print the result table, notes, and warnings."""
    if ui is None:
        ui = UIStrings({})

    if not rows and not notes and not unparseable:
        print(ui.s('nothing_to_display'))
        return

    headers = ui.table_headers

    if rows:
        table = [headers]
        for i, row in enumerate(rows):
            table.append(_row_to_cells(i, row))

        widths = [max(len(r[c]) for r in table) for c in range(len(headers))]

        header_line = ' | '.join(h.ljust(w) for h, w in zip(headers, widths))
        print(f"\n{header_line}")
        print('-' * len(header_line))

        for row_cells in table[1:]:
            line = ' | '.join(c.ljust(w) for c, w in zip(row_cells, widths))
            print(line)

    if notes:
        print()
        note_prefix = ui.s('note_prefix')
        for note in notes:
            print(f'\U0001f4dd {note_prefix}: "{note}"')

    if unparseable:
        print()
        unparse_prefix = ui.s('unparseable_prefix')
        for text in unparseable:
            print(f'\u26a0 {unparse_prefix}: "{text}"')
        if ui.items:
            items_hint = ', '.join(ui.items)
            print(f'  {ui.s("help_items_header")} {items_hint}')


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

def edit_closed_set(field, options, ui):
    """Show lettered options, return selected value."""
    display_name = ui.field_name(field)
    opt_letters = ui.option_letters
    print(f"\n{display_name}:")
    for i, opt in enumerate(options):
        letter = opt_letters[i] if i < len(opt_letters) else str(i)
        print(f"  [{letter}] {opt}")
    print()

    while True:
        print(ui.s('enter_letter_prompt'), end='')
        choice = input().strip()
        # For case-insensitive matching on ASCII; no-op for Hebrew
        choice_lower = choice.lower()
        if not choice_lower:
            print(ui.s('edit_cancelled'))
            return None

        # Try letter lookup
        idx = opt_letters.find(choice_lower[0]) if len(choice_lower) == 1 else -1
        if idx == -1 and len(choice) == 1:
            # Also try the original case (Hebrew letters have no case)
            idx = opt_letters.find(choice[0])
        if 0 <= idx < len(options):
            return options[idx]

        # Try typing the value directly
        for opt in options:
            if opt.lower().startswith(choice_lower):
                return opt

        first = opt_letters[0] if opt_letters else '?'
        last = opt_letters[min(len(options) - 1, len(opt_letters) - 1)]
        print(ui.s('invalid_choice', first=first, last=last))


def edit_open_field(field, current_value, ui):
    """Prompt for direct input. Returns new value or None to cancel."""
    display_name = ui.field_name(field)
    current_display = current_value if current_value is not None else ''
    print(ui.s('open_field_prompt', display_name=display_name, current=current_display))
    raw = input("> ").strip()
    if not raw:
        print(ui.s('edit_cancelled'))
        return None

    if field == 'qty':
        val = eval_qty(raw)
        if val is None:
            print(ui.s('invalid_quantity'))
            return None
        return val

    if field == 'date':
        val = parse_date(raw)
        if val is None:
            print(ui.s('invalid_date'))
            return None
        return val

    if field == 'batch':
        try:
            return int(raw)
        except ValueError:
            print(ui.s('invalid_batch'))
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
        if isinstance(new_value, (int, float)):
            partner['qty'] = -new_value


# ============================================================
# Alias learning
# ============================================================

def check_alias_opportunity(rows, original_tokens, config):
    """Check if any edited items should be saved as aliases."""
    aliases = config.get('aliases', {})
    items = [i.lower() for i in config.get('items', [])]
    prompts = []

    for idx, original in original_tokens.items():
        if idx >= len(rows):
            continue
        canonical = rows[idx].get('inv_type', '')
        if not original or not canonical:
            continue
        if original == '???' or canonical == '???':
            continue

        orig_lower = original.lower()
        canon_lower = canonical.lower()

        if orig_lower == canon_lower:
            continue
        if orig_lower in (a.lower() for a in aliases):
            continue
        if orig_lower in items:
            continue

        prompts.append((original, canonical))

    return prompts


def prompt_save_aliases(prompts, config, ui):
    """Ask user whether to save new aliases."""
    yes = ui.commands['yes']
    saved = False
    for original, canonical in prompts:
        print(ui.s('save_alias_prompt',
                   original=original, canonical=canonical,
                   yes=ui.commands['yes'], no=ui.commands['no']), end='')
        resp = input().strip().lower()
        if resp == yes:
            if 'aliases' not in config:
                config['aliases'] = {}
            config['aliases'][original] = canonical
            saved = True
    return saved


# ============================================================
# Review loop
# ============================================================

def review_loop(result, raw_text, config):
    """Interactive review. Returns confirmed rows or None (quit)."""
    ui = UIStrings(config)
    rows = list(result.rows)
    notes = list(result.notes)
    unparseable = list(result.unparseable)

    original_tokens = {}

    cmd_confirm = ui.commands['confirm']
    cmd_quit = ui.commands['quit']
    cmd_retry = ui.commands['retry']
    cmd_edit = ui.commands.get('edit', ui.commands['retry'])
    cmd_save_note = ui.commands['save_note']
    cmd_skip = ui.commands['skip']
    cmd_add = ui.commands['add_row']
    cmd_help = ui.commands['help']

    # Build regex patterns from configured codes
    delete_pattern = re.compile(rf'^{ui._delete_prefix}(\d+)$')
    field_pattern = re.compile(rf'^(\d+)([{ui._field_code_chars}])$')

    while True:
        display_result(rows, notes, unparseable, ui)

        if not rows and not notes and unparseable:
            print(ui.s('unparseable_prompt'))
            cmd = input("> ").strip().lower()
            if cmd == cmd_help:
                print(ui.help_text_unparseable)
                continue
            if cmd == cmd_skip:
                return None
            if cmd == cmd_edit:
                rows, notes, unparseable = _edit_retry(raw_text, config, ui)
                continue
            continue

        if not rows and notes and not unparseable:
            print(ui.s('no_transactions'))
            print(ui.s('notes_only_prompt'))
            cmd = input("> ").strip().lower()
            if cmd == cmd_help:
                print(ui.help_text_notes)
                continue
            if cmd == cmd_save_note:
                return {'rows': [], 'notes': notes}
            if cmd == cmd_skip:
                return None
            if cmd == cmd_edit:
                rows, notes, unparseable = _edit_retry(raw_text, config, ui)
                continue
            continue

        # Normal review
        print(ui.s('review_prompt'))
        cmd = input("> ").strip().lower()

        if cmd == cmd_help:
            print(ui.help_text)
            continue

        if cmd == cmd_confirm:
            # Warn about incomplete rows
            incomplete = [i + 1 for i, r in enumerate(rows)
                          if r.get('inv_type') == '???' or r.get('trans_type') is None
                          or r.get('vehicle_sub_unit') is None]
            if incomplete:
                row_list = ', '.join(str(n) for n in incomplete)
                print(ui.s('confirm_incomplete_warning',
                           row_list=row_list,
                           yes=ui.commands['yes'],
                           no=ui.commands['no']), end='')
                resp = input().strip().lower()
                if resp != ui.commands['yes']:
                    continue

            if original_tokens:
                prompts = check_alias_opportunity(rows, original_tokens, config)
                if prompts:
                    prompt_save_aliases(prompts, config, ui)
            return {'rows': rows, 'notes': notes}

        if cmd == cmd_quit:
            return None

        if cmd == cmd_retry:
            rows, notes, unparseable = _edit_retry(raw_text, config, ui)
            continue

        if cmd == cmd_add:
            rows.append(empty_row())
            continue

        # Delete row
        m = delete_pattern.match(cmd)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(rows):
                rows.pop(idx)
                print(ui.s('row_deleted', num=idx + 1))
            else:
                print(ui.s('invalid_row'))
            continue

        # Edit field: <row><field_code>
        m = field_pattern.match(cmd)
        if m:
            row_num = int(m.group(1)) - 1
            field_code = m.group(2)
            field = ui._field_code_to_field[field_code]

            if row_num < 0 or row_num >= len(rows):
                print(ui.s('invalid_row'))
                continue

            old_value = rows[row_num].get(field)
            old_item_token = rows[row_num].get('inv_type') if field == 'inv_type' else None

            if field in CLOSED_SET_FIELDS:
                options = get_closed_set_options(field, config)
                new_value = edit_closed_set(field, options, ui)
            else:
                new_value = edit_open_field(field, old_value, ui)

            if new_value is not None:
                partner_idx = find_partner(rows, row_num)
                rows[row_num][field] = new_value
                if partner_idx is not None:
                    if field in ('inv_type', 'date', 'trans_type', 'batch'):
                        rows[partner_idx][field] = new_value
                    elif field == 'qty' and isinstance(new_value, (int, float)):
                        rows[partner_idx]['qty'] = -new_value

                if field == 'inv_type' and old_item_token and old_item_token != new_value:
                    original_tokens[row_num] = old_item_token

                print(ui.s('row_updated',
                           num=row_num + 1,
                           field=ui.field_name(field).lower(),
                           value=new_value))
            continue

        # Unknown command
        item_code = ui._first_field_code_for('inv_type')
        item_name = ui.field_name('inv_type').lower()
        print(ui.s('unknown_command', example_field=item_code, example_name=item_name))

    return None


def empty_row():
    return {
        'date': date.today(),
        'inv_type': '???',
        'qty': 0,
        'trans_type': None,
        'vehicle_sub_unit': None,
        'batch': 1,
        'notes': None,
    }


def _edit_retry(raw_text, config, ui):
    """Show raw text, let user edit, re-parse."""
    print(ui.s('original_text_label', text=raw_text))
    print(ui.s('enter_corrected_text'))
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
        new_text = raw_text
    else:
        new_text = '\n'.join(lines)

    result = parse(new_text, config)
    return list(result.rows), list(result.notes), list(result.unparseable)


# ============================================================
# Main
# ============================================================

def main(config_path='config_he.yaml'):
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Create one based on config.yaml.example")
        sys.exit(1)

    ui = UIStrings(config)

    print(ui.s('title'))
    print(ui.s('subtitle'))

    while True:
        raw_text = get_input(ui)
        if raw_text is None:
            print(ui.s('goodbye'))
            break

        result = parse(raw_text, config)

        outcome = review_loop(result, raw_text, config)

        if outcome is None:
            print(ui.s('discarded'))
            continue

        confirmed_rows = outcome.get('rows', [])
        confirmed_notes = outcome.get('notes', [])

        if confirmed_rows:
            print(ui.s('confirmed_title'))
            display_result(confirmed_rows, ui=ui)
            print(ui.s('confirmed_count', count=len(confirmed_rows)))

        if confirmed_notes:
            saved_prefix = ui.s('saved_note_prefix')
            for note in confirmed_notes:
                print(f'\U0001f4dd {saved_prefix}: "{note}"')

        save_config(config, config_path)


if __name__ == '__main__':
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config_he.yaml'
    main(config_path)
