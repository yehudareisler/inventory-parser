"""Inventory message parser — Text User Interface.

Interactive review/edit workflow:
  paste message → parse → review table → edit if needed → confirm → done
"""

import re
import sys
from datetime import date

from inventory_parser import parse
from inventory_core import (
    UIStrings, load_config, save_config,
    get_closed_set_fields, get_field_order, get_required_fields,
    get_closed_set_options,
    _row_to_cells,
    format_rows_for_clipboard,
    copy_to_clipboard,
    eval_qty, parse_date,
    find_partner, update_partner,
    check_alias_opportunity,
    check_conversion_opportunity,
    empty_row,
)


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

def display_result(rows, notes=None, unparseable=None, ui=None, config=None):
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
            table.append(_row_to_cells(i, row, config))

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


# ============================================================
# Alias learning (interactive)
# ============================================================

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
# Unit conversion learning (interactive)
# ============================================================

def prompt_save_conversions(prompts, config, ui):
    """Ask user to define conversion factors for unconverted containers."""
    saved = False
    for item, container in prompts:
        print(ui.s('save_conversion_prompt',
                   item=item, container=container), end='')
        resp = input().strip()
        if not resp:
            continue
        try:
            factor = float(resp)
            if factor == int(factor):
                factor = int(factor)
        except ValueError:
            continue
        if 'unit_conversions' not in config:
            config['unit_conversions'] = {}
        if item not in config['unit_conversions']:
            config['unit_conversions'][item] = {}
        config['unit_conversions'][item][container] = factor
        print(ui.s('conversion_saved', item=item, container=container, factor=factor))
        saved = True
    return saved


# ============================================================
# Direct add commands
# ============================================================

def add_alias_interactive(config, ui):
    """Interactively add an alias with fuzzy matching."""
    from inventory_parser import fuzzy_resolve

    items = config.get('items', [])
    locations = config.get('locations', [])
    if items:
        print(f'  {ui.s("help_items_header")} {", ".join(items)}')
    if locations:
        print(f'  {ui.s("help_locations_header")} {", ".join(locations)}')
    print(ui.s('alias_short_prompt'), end='')
    alias = input().strip()
    if not alias:
        return False
    print(ui.s('alias_maps_to_prompt'), end='')
    target_text = input().strip()
    if not target_text:
        return False

    # Fuzzy resolve against all known entities
    all_entities = items + locations
    resolved, match_type = fuzzy_resolve(target_text, all_entities,
                                          config.get('aliases', {}))
    if resolved and match_type == 'fuzzy':
        yes = ui.commands['yes']
        no = ui.commands['no']
        print(ui.s('fuzzy_confirm', resolved=resolved, yes=yes, no=no), end='')
        if input().strip().lower() != yes:
            print(ui.s('edit_cancelled'))
            return False
        target = resolved
    elif resolved:
        target = resolved
    else:
        target = target_text

    if 'aliases' not in config:
        config['aliases'] = {}
    config['aliases'][alias] = target
    print(ui.s('alias_saved', alias=alias, item=target))
    return True


def add_conversion_interactive(config, ui):
    """Interactively add a unit conversion with fuzzy matching."""
    from inventory_parser import fuzzy_resolve, get_all_containers

    items = config.get('items', [])
    if items:
        print(f'  {ui.s("help_items_header")} {", ".join(items)}')

    # Item name (fuzzy resolved)
    print(ui.s('convert_item_prompt'), end='')
    item_text = input().strip()
    if not item_text:
        return False
    resolved, match_type = fuzzy_resolve(item_text, items,
                                          config.get('aliases', {}))
    if resolved and match_type == 'fuzzy':
        yes, no = ui.commands['yes'], ui.commands['no']
        print(ui.s('fuzzy_confirm', resolved=resolved, yes=yes, no=no), end='')
        if input().strip().lower() != yes:
            print(ui.s('edit_cancelled'))
            return False
        item = resolved
    elif resolved:
        item = resolved
    else:
        item = item_text

    # Container name (fuzzy resolved)
    print(ui.s('convert_container_prompt'), end='')
    cont_text = input().strip()
    if not cont_text:
        return False
    containers = list(get_all_containers(config))
    if containers:
        resolved_c, match_c = fuzzy_resolve(cont_text, containers)
        if resolved_c and match_c == 'fuzzy':
            yes, no = ui.commands['yes'], ui.commands['no']
            print(ui.s('fuzzy_confirm', resolved=resolved_c, yes=yes, no=no), end='')
            if input().strip().lower() != yes:
                print(ui.s('edit_cancelled'))
                return False
            container = resolved_c
        elif resolved_c:
            container = resolved_c
        else:
            container = cont_text
    else:
        container = cont_text

    # Factor
    print(ui.s('convert_factor_prompt', container=container), end='')
    resp = input().strip()
    if not resp:
        return False
    try:
        factor = float(resp)
        if factor == int(factor):
            factor = int(factor)
    except ValueError:
        return False
    if 'unit_conversions' not in config:
        config['unit_conversions'] = {}
    if item not in config['unit_conversions']:
        config['unit_conversions'][item] = {}
    config['unit_conversions'][item][container] = factor
    print(ui.s('conversion_saved', item=item, container=container, factor=factor))
    return True


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
        display_result(rows, notes, unparseable, ui, config)

        if not rows:
            if notes:
                print(ui.s('no_transactions'))
                print(ui.s('notes_only_prompt'))
            elif unparseable:
                print(ui.s('unparseable_prompt'))
            else:
                print(ui.s('unparseable_prompt'))

            cmd = input("> ").strip().lower()

            if cmd == cmd_help:
                print(ui.help_text_notes if notes else ui.help_text_unparseable)
                continue
            if cmd == cmd_save_note and notes:
                return {'rows': [], 'notes': notes}
            if cmd in (cmd_skip, cmd_quit, cmd_confirm):
                return None
            if cmd in (cmd_edit, cmd_retry):
                rows, notes, unparseable = _edit_retry(raw_text, config, ui)
                continue
            if cmd == cmd_add:
                rows.append(empty_row())
                continue
            # Unknown command
            item_code = ui._first_field_code_for('inv_type')
            item_name = ui.field_name('inv_type').lower()
            print(ui.s('unknown_command', example_field=item_code, example_name=item_name))
            continue

        # Normal review
        print(ui.s('review_prompt'))
        cmd = input("> ").strip().lower()

        if cmd == cmd_help:
            print(ui.help_text)
            continue

        if cmd == cmd_confirm:
            # Warn about incomplete rows
            required = get_required_fields(config)
            incomplete = [i + 1 for i, r in enumerate(rows)
                          if r.get('inv_type') == '???'
                          or any(r.get(f) is None for f in required)]
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

            conv_prompts = check_conversion_opportunity(rows, config)
            if conv_prompts:
                prompt_save_conversions(conv_prompts, config, ui)

            # Strip metadata fields before returning
            for row in rows:
                row.pop('_container', None)
                row.pop('_raw_qty', None)

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
                partner_idx = find_partner(rows, idx)
                rows.pop(idx)
                print(ui.s('row_deleted', num=idx + 1))
                if partner_idx is not None:
                    adjusted = partner_idx if partner_idx < idx else partner_idx - 1
                    print(ui.s('delete_partner_warning', partner_num=adjusted + 1))
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

            if field in get_closed_set_fields(config):
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


def _edit_retry(raw_text, config, ui):
    """Show numbered lines, let user edit by line number, re-parse."""
    lines = [l for l in raw_text.split('\n') if l.strip()]

    while True:
        print()
        for i, line in enumerate(lines, 1):
            print(f'  {i}. {line}')
        print()
        print(ui.s('edit_line_prompt'), end=' ')
        choice = input().strip()
        if not choice:
            break
        try:
            num = int(choice)
        except ValueError:
            print(ui.s('invalid_row'))
            continue
        if num < 1 or num > len(lines) + 1:
            print(ui.s('invalid_row'))
            continue
        if num == len(lines) + 1:
            # Add a new line
            print(ui.s('edit_line_new'), end=' ')
            new = input().strip()
            if new:
                lines.append(new)
                print(ui.s('edit_line_updated', num=num))
            continue
        print(f'  {lines[num - 1]}')
        print(ui.s('edit_line_new'), end=' ')
        new = input().strip()
        if new:
            lines[num - 1] = new
            print(ui.s('edit_line_updated', num=num))
        else:
            del lines[num - 1]
            print(ui.s('edit_line_deleted', num=num))

    new_text = '\n'.join(lines) if lines else raw_text
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

        # Direct commands
        cmd = raw_text.strip().lower()
        if cmd == ui.s('cmd_alias').lower():
            add_alias_interactive(config, ui)
            save_config(config, config_path)
            ui = UIStrings(config)
            continue
        if cmd == ui.s('cmd_convert').lower():
            add_conversion_interactive(config, ui)
            save_config(config, config_path)
            continue

        result = parse(raw_text, config)

        outcome = review_loop(result, raw_text, config)

        if outcome is None:
            print(ui.s('discarded'))
            continue

        confirmed_rows = outcome.get('rows', [])
        confirmed_notes = outcome.get('notes', [])

        if confirmed_rows:
            tsv = format_rows_for_clipboard(confirmed_rows, config)
            if copy_to_clipboard(tsv):
                print(ui.s('clipboard_copied', count=len(confirmed_rows)))
            else:
                print(ui.s('clipboard_failed'))
                display_result(confirmed_rows, ui=ui, config=config)
                print(ui.s('confirmed_count', count=len(confirmed_rows)))

        if confirmed_notes:
            saved_prefix = ui.s('saved_note_prefix')
            for note in confirmed_notes:
                print(f'\U0001f4dd {saved_prefix}: "{note}"')

        save_config(config, config_path)


if __name__ == '__main__':
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config_he.yaml'
    main(config_path)
