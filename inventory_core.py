"""Inventory core — shared I/O-free logic used by both TUI and web.

Config loading, UI strings, field metadata, row formatting,
double-entry partner detection, learning checks, clipboard export.
"""

import re
import subprocess
import shutil
from datetime import date

import yaml


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
        'paste_prompt': "\nPaste message ('exit' to quit, 'alias'/'convert' to add):",
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
        'delete_partner_warning': '  Note: Row {partner_num} is the double-entry partner and now standalone.',
        'invalid_row': '  Invalid row number.',
        'row_updated': '  Row {num} {field} \u2192 {value}',
        'unknown_command': '  Unknown command. Type ? for help, or try e.g. 1{example_field} to edit {example_name} on row 1.',
        'original_text_label': '\nOriginal text:\n{text}\n',
        'enter_corrected_text': 'Enter corrected text (empty line to finish):',
        'edit_line_prompt': 'Line # to edit (Enter to re-parse):',
        'edit_line_new': '  New text (Enter to delete line):',
        'edit_line_updated': '  Line {num} updated.',
        'edit_line_deleted': '  Line {num} deleted.',
        'save_alias_prompt': 'Save "{original}" \u2192 "{canonical}" as alias? [{yes}/{no}] ',
        'title': '=== Inventory Message Parser ===',
        'subtitle': "Paste a WhatsApp message to parse. Type 'exit' to quit.\n",
        'goodbye': 'Goodbye.',
        'discarded': '  Discarded.',
        'confirmed_title': '\n=== Confirmed transactions ===',
        'confirmed_count': '\n({count} row(s) confirmed)',
        'clipboard_copied': '\n({count} row(s) copied to clipboard)',
        'clipboard_failed': '\nCould not copy to clipboard. Showing table instead:',
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
        # Unit conversion & direct commands
        'save_conversion_prompt': 'Save unit conversion? 1 {container} of {item} = ? ',
        'conversion_saved': '  Saved: 1 {container} of {item} = {factor}',
        'cmd_alias': 'alias',
        'cmd_convert': 'convert',
        'alias_short_prompt': 'Alias (short name): ',
        'alias_maps_to_prompt': 'Maps to: ',
        'alias_saved': '  Saved: {alias} \u2192 {item}',
        'convert_item_prompt': 'Item name: ',
        'convert_container_prompt': 'Container name: ',
        'convert_factor_prompt': 'How many units in 1 {container}: ',
        'fuzzy_confirm': '  \u2192 {resolved}? [{yes}/{no}] ',
        'help_locations_header': 'Known locations:',
        'review_parse_btn': 'Parse',
        'review_confirm_btn': 'Confirm',
        'review_add_row_btn': '+ Row',
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
# Field metadata
# ============================================================

_DEFAULT_FIELD_ORDER = ['date', 'inv_type', 'qty', 'trans_type', 'vehicle_sub_unit', 'batch', 'notes']

_DEFAULT_FIELD_OPTIONS = {
    'inv_type': 'items',
    'trans_type': 'transaction_types',
    'vehicle_sub_unit': 'locations',
}


def get_closed_set_fields(config):
    """Get set of closed-set field names from config, with fallback."""
    fo = config.get('field_options', _DEFAULT_FIELD_OPTIONS)
    return set(fo.keys())


def get_field_order(config):
    """Get display field order from config, with fallback."""
    return config.get('ui', {}).get('field_order', _DEFAULT_FIELD_ORDER)


def get_required_fields(config):
    """Get list of required field names from config, with fallback."""
    return config.get('required_fields', ['trans_type', 'vehicle_sub_unit'])


def get_closed_set_options(field, config):
    """Get the list of options for a closed-set field."""
    field_options = config.get('field_options', _DEFAULT_FIELD_OPTIONS)
    config_key = field_options.get(field)

    if config_key:
        options = list(config.get(config_key, []))
        # For locations, include default_source if not already present
        if field == 'vehicle_sub_unit':
            src = config.get('default_source', 'warehouse')
            if src not in options:
                options.insert(0, src)
        return options

    # Legacy fallback
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
# Row formatting
# ============================================================

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


def row_has_warning(row, config=None):
    if config:
        required = get_required_fields(config)
        return any(row.get(f) is None for f in required)
    return (row.get('trans_type') is None
            or row.get('vehicle_sub_unit') is None)


def _format_cell(row, field):
    if field == 'date':
        return format_date(row.get('date'))
    if field == 'qty':
        qty_str = format_qty(row.get('qty'))
        if row.get('_container'):
            qty_str = f"{qty_str} [{row['_container']}?]"
        return qty_str
    if field == 'batch':
        return str(row.get('batch', ''))
    if field == 'notes':
        return row.get('notes') or ''
    # Default: show value or ???
    val = row.get(field)
    return val if val is not None else '???'


def _row_to_cells(i, row, config=None):
    warn = '\u26a0 ' if row_has_warning(row, config) else ''
    field_order = get_field_order(config) if config else _DEFAULT_FIELD_ORDER
    cells = [f'{warn}{i + 1}']
    for field in field_order:
        cells.append(_format_cell(row, field))
    return cells


def format_rows_for_clipboard(rows, config=None):
    """Format confirmed rows as TSV for pasting into Excel/Google Sheets.

    Returns a tab-separated string with one line per row (no header).
    Empty rows list returns empty string.
    """
    if not rows:
        return ''

    field_order = get_field_order(config) if config else _DEFAULT_FIELD_ORDER

    lines = []
    for row in rows:
        cells = [_format_cell(row, f) for f in field_order]
        lines.append('\t'.join(cells))

    return '\n'.join(lines)


# ============================================================
# Clipboard export
# ============================================================

# Pluggable clipboard — web interface overrides this
_clipboard_fn = None


def copy_to_clipboard(text):
    """Copy text to system clipboard. Returns True on success, False otherwise."""
    if _clipboard_fn is not None:
        return _clipboard_fn(text)

    # WSL: clip.exe can't handle Unicode; use PowerShell Set-Clipboard
    if shutil.which('powershell.exe'):
        try:
            subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                 '$input | Set-Clipboard'],
                input=text.encode('utf-8'), check=True,
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            pass

    commands = [
        ['xclip', '-selection', 'clipboard'],  # Linux
        ['pbcopy'],                            # macOS
    ]
    for cmd in commands:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode('utf-8'), check=True)
                return True
            except (subprocess.CalledProcessError, OSError):
                continue
    return False


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

    # DDMMYY (6 digits, no separators)
    m = re.match(r'(\d{6})$', text)
    if m:
        s = m.group(1)
        day, month, year = int(s[:2]), int(s[2:4]), int(s[4:6]) + 2000
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


# ============================================================
# Unit conversion learning
# ============================================================

def check_conversion_opportunity(rows, config):
    """Check if any rows have unconverted containers that could be saved."""
    convs = config.get('unit_conversions', {})
    seen = set()
    prompts = []

    for row in rows:
        container = row.get('_container')
        item = row.get('inv_type', '???')
        if not container or item == '???':
            continue

        key = (item, container)
        if key in seen:
            continue
        seen.add(key)

        # Skip if conversion already exists
        if convs.get(item, {}).get(container) is not None:
            continue

        prompts.append((item, container))

    return prompts


# ============================================================
# Utilities
# ============================================================

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
