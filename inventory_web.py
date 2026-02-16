"""Web-based interface for the inventory parser.

Side-by-side SPA: left pane for message editing, right pane for parsed results.
Run with: python inventory_web.py
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import webbrowser
from datetime import date

from inventory_parser import parse, fuzzy_resolve
from inventory_core import (
    UIStrings, load_config, save_config,
    load_config_with_sheets,
    save_learned_alias, save_learned_conversion,
    format_rows_for_clipboard, find_partner,
    check_alias_opportunity, check_conversion_opportunity,
    empty_row, eval_qty, parse_date,
    get_closed_set_fields, get_field_order, get_required_fields,
    get_closed_set_options, row_has_warning,
)

_state_lock = threading.Lock()
_state = {
    'config': None,
    'config_path': None,
    'sheets_client': None,
    'rows': [],
    'notes': [],
    'unparseable': [],
    'original_tokens': {},
}


def _json_serial(obj):
    """JSON serializer for date objects."""
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


# ============================================================
# HTML SPA — loaded from index.html
# ============================================================

_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
with open(_HTML_PATH, 'r', encoding='utf-8') as _f:
    _HTML = _f.read()


# ============================================================
# API handlers
# ============================================================

class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self._ok('text/html', _HTML.encode())
        elif self.path == '/api/config':
            self._handle_config()
        else:
            self.send_error(404)

    def do_POST(self):
        body = {}
        cl = int(self.headers.get('Content-Length', 0))
        if cl > 0:
            body = json.loads(self.rfile.read(cl))

        handlers = {
            '/api/parse': self._handle_parse,
            '/api/confirm': self._handle_confirm,
            '/api/edit': self._handle_edit,
            '/api/delete': self._handle_delete,
            '/api/alias': self._handle_alias,
            '/api/conversion': self._handle_conversion,
            '/api/fuzzy': self._handle_fuzzy,
        }
        handler = handlers.get(self.path)
        if handler:
            handler(body)
        else:
            self.send_error(404)

    def _handle_config(self):
        with _state_lock:
            config = _state['config']
        ui = UIStrings(config)

        # Pre-resolve closed-set options so JS doesn't re-derive them
        closed_set_options = {}
        for field in get_closed_set_fields(config):
            closed_set_options[field] = get_closed_set_options(field, config)

        payload = {
            'items': config.get('items', []),
            'locations': config.get('locations', []),
            'default_source': config.get('default_source', ''),
            'transaction_types': config.get('transaction_types', []),
            'aliases': config.get('aliases', {}),
            'unit_conversions': config.get('unit_conversions', {}),
            'closed_set_options': closed_set_options,
            'required_fields': get_required_fields(config),
            'field_order': get_field_order(config),
            'ui': {
                'commands': ui.commands,
                'field_codes': ui.field_codes,
                'field_display_names': ui.field_display_names,
                'table_headers': ui.table_headers,
                'option_letters': ui.option_letters,
                'strings': ui.strings,
                'field_order': get_field_order(config),
            },
        }
        self._json(payload)

    def _handle_parse(self, body):
        text = body.get('text', '')
        with _state_lock:
            config = _state['config']
        result = parse(text, config)
        rows = []
        for row in result.rows:
            r = dict(row)
            # Ensure date is serializable
            if 'date' in r and isinstance(r['date'], date):
                r['date'] = r['date'].isoformat()
            rows.append(r)
        notes = list(result.notes)
        unparseable = list(result.unparseable)
        with _state_lock:
            _state['rows'] = list(result.rows)  # keep original (with date objects)
            _state['notes'] = notes
            _state['unparseable'] = unparseable
        self._json({'rows': rows, 'notes': notes, 'unparseable': unparseable})

    def _handle_confirm(self, body):
        target = body.get('target', 'both')  # 'sheet', 'clipboard', 'both'

        with _state_lock:
            config = _state['config']
            sheets_client = _state['sheets_client']

        # Use rows from JS (may have updated qty from pre-confirm conversions)
        if body.get('rows'):
            rows = _deserialize_rows(body['rows'])
        else:
            with _state_lock:
                rows = _state['rows']

        # Check learning opportunities before stripping metadata
        alias_prompts = check_alias_opportunity(rows, _state.get('original_tokens', {}), config)

        # Strip metadata
        for row in rows:
            row.pop('_container', None)
            row.pop('_raw_qty', None)

        # Generate TSV for clipboard targets
        tsv = None
        if target in ('clipboard', 'both'):
            tsv = format_rows_for_clipboard(rows, config)

        # Write to Google Sheet for sheet targets
        sheets_count = 0
        sheets_error = None
        if target in ('sheet', 'both'):
            gs = config.get('google_sheets', {})
            gs_output = gs.get('output', {})
            if sheets_client and gs_output.get('transactions'):
                from inventory_sheets import append_rows
                try:
                    sheets_count = append_rows(
                        sheets_client, gs['spreadsheet_id'],
                        gs_output['transactions']['sheet'],
                        rows, get_field_order(config))
                except Exception as e:
                    sheets_error = str(e)

        with _state_lock:
            _state['rows'] = []
            _state['notes'] = []
            _state['unparseable'] = []
            _state['original_tokens'] = {}
            save_config(config, _state['config_path'])

        self._json({
            'ok': True,
            'count': len(rows),
            'clip': tsv,
            'alias_prompts': alias_prompts,
            'sheets_count': sheets_count,
            'sheets_error': sheets_error,
        })

    def _handle_edit(self, body):
        rows = body.get('rows', [])
        row_idx = body.get('row_idx', 0)
        field = body.get('field', '')
        value = body.get('value', '')

        with _state_lock:
            config = _state['config']

        # Reconstruct rows with proper types
        rows = _deserialize_rows(rows)

        if row_idx < 0 or row_idx >= len(rows):
            self._json({'error': 'Invalid row', 'rows': _serialize_rows(rows)})
            return

        # Parse value based on field type
        if field == 'qty':
            parsed = eval_qty(value)
            if parsed is None:
                self._json({'error': 'Invalid quantity', 'rows': _serialize_rows(rows)})
                return
            value = parsed
        elif field == 'date':
            parsed = parse_date(value) if not isinstance(value, str) or len(value) > 0 else None
            if isinstance(value, str) and value:
                parsed = parse_date(value)
                if parsed is None:
                    # Try ISO format
                    try:
                        parsed = date.fromisoformat(value)
                    except ValueError:
                        pass
                if parsed is None:
                    self._json({'error': 'Invalid date', 'rows': _serialize_rows(rows)})
                    return
                value = parsed
        elif field == 'batch':
            try:
                value = int(value)
            except (ValueError, TypeError):
                self._json({'error': 'Invalid batch', 'rows': _serialize_rows(rows)})
                return

        # Track original token for alias learning
        old_item = rows[row_idx].get('inv_type')
        rows[row_idx][field] = value

        # Update partner
        partner_idx = find_partner(rows, row_idx)
        if partner_idx is not None:
            if field in ('inv_type', 'date', 'trans_type', 'batch'):
                rows[partner_idx][field] = value
            elif field == 'qty' and isinstance(value, (int, float)):
                rows[partner_idx]['qty'] = -value

        if field == 'inv_type' and old_item and old_item != value:
            with _state_lock:
                _state['original_tokens'][row_idx] = old_item

        with _state_lock:
            _state['rows'] = rows

        self._json({'rows': _serialize_rows(rows)})

    def _handle_delete(self, body):
        rows = _deserialize_rows(body.get('rows', []))
        row_idx = body.get('row_idx', 0)
        warning = None

        if 0 <= row_idx < len(rows):
            partner_idx = find_partner(rows, row_idx)
            rows.pop(row_idx)
            if partner_idx is not None:
                adjusted = partner_idx if partner_idx < row_idx else partner_idx - 1
                ui = UIStrings(_state['config'])
                warning = ui.s('delete_partner_warning', partner_num=adjusted + 1)

        with _state_lock:
            _state['rows'] = rows

        self._json({'rows': _serialize_rows(rows), 'warning': warning})

    def _handle_alias(self, body):
        alias = body.get('alias', '').strip()
        target = body.get('target', '').strip()
        if not alias or not target:
            self._json({'ok': False})
            return

        with _state_lock:
            config = _state['config']
            sheets_client = _state['sheets_client']

        # Fuzzy resolve target
        items = config.get('items', [])
        locations = config.get('locations', [])
        all_entities = items + locations + config.get('transaction_types', [])
        resolved, match_type = fuzzy_resolve(target, all_entities, config.get('aliases', {}))
        final_target = resolved if resolved else target

        save_learned_alias(config, _state['config_path'], sheets_client,
                           alias, final_target)

        self._json({'ok': True, 'resolved': final_target, 'match_type': match_type})

    def _handle_conversion(self, body):
        item = body.get('item', '').strip()
        container = body.get('container', '').strip()
        factor = body.get('factor')
        if not item or not container or factor is None:
            self._json({'ok': False})
            return

        with _state_lock:
            config = _state['config']
            sheets_client = _state['sheets_client']

        # Fuzzy resolve item and container
        items = config.get('items', [])
        resolved_item, _ = fuzzy_resolve(item, items, config.get('aliases', {}))
        final_item = resolved_item or item

        from inventory_parser import get_all_containers
        containers = list(get_all_containers(config))
        resolved_cont, _ = fuzzy_resolve(container, containers)
        final_container = resolved_cont or container

        factor_val = float(factor)
        if factor_val == int(factor_val):
            factor_val = int(factor_val)

        save_learned_conversion(config, _state['config_path'], sheets_client,
                                final_item, final_container, factor_val)

        self._json({'ok': True, 'item': final_item, 'container': final_container})

    def _handle_fuzzy(self, body):
        text = body.get('text', '')
        ctype = body.get('candidates_type', 'items')
        with _state_lock:
            config = _state['config']
        candidates = config.get(ctype, [])
        resolved, match_type = fuzzy_resolve(text, candidates, config.get('aliases', {}))
        self._json({'resolved': resolved, 'match_type': match_type})

    def _ok(self, ct, body):
        self.send_response(200)
        self.send_header('Content-Type', ct + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, default=_json_serial).encode()
        self._ok('application/json', body)

    def log_message(self, *args):
        pass


def _serialize_rows(rows):
    """Convert rows to JSON-safe format."""
    out = []
    for row in rows:
        r = dict(row)
        if 'date' in r and isinstance(r['date'], date):
            r['date'] = r['date'].isoformat()
        out.append(r)
    return out


def _deserialize_rows(rows):
    """Convert JSON rows back to proper Python types."""
    out = []
    for row in rows:
        r = dict(row)
        if 'date' in r and isinstance(r['date'], str):
            try:
                r['date'] = date.fromisoformat(r['date'])
            except (ValueError, TypeError):
                pass
        out.append(r)
    return out


def main():
    port = 8765
    config_path = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.yaml') else 'config_he.yaml'

    config, sheets_client = load_config_with_sheets(config_path)
    with _state_lock:
        _state['config'] = config
        _state['config_path'] = config_path
        _state['sheets_client'] = sheets_client

    class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = _ThreadedServer(('127.0.0.1', port), _H)
    print(f'http://localhost:{port}')
    sys.stdout.flush()
    webbrowser.open(f'http://localhost:{port}')

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
