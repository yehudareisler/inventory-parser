"""Web-based interface for the inventory parser.

Side-by-side SPA: left pane for message editing, right pane for parsed results.
Run with: python inventory_web.py
"""

import http.server
import json
import socketserver
import sys
import threading
import webbrowser
from datetime import date

from inventory_parser import parse, fuzzy_resolve
from inventory_tui import (
    UIStrings, load_config, save_config,
    format_rows_for_clipboard, find_partner,
    check_alias_opportunity, check_conversion_opportunity,
    empty_row, eval_qty, parse_date,
)

_state_lock = threading.Lock()
_state = {
    'config': None,
    'config_path': None,
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
# HTML SPA
# ============================================================

_HTML = r'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>inventory parser</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0c0c0c;
    color: #cccccc;
    font-family: 'Cascadia Mono', Consolas, 'Courier New', monospace;
    font-size: 14px;
    padding: 20px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
#main {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
}
#left-pane {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
}
#right-pane {
    flex: 1.2;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow-y: auto;
}
#raw-input {
    flex: 1;
    width: 100%;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    color: #cccccc;
    font-family: inherit;
    font-size: inherit;
    padding: 10px;
    resize: none;
    direction: rtl;
    outline: none;
    word-wrap: break-word;
    overflow-wrap: break-word;
}
#raw-input:focus { border-color: #555; }
#raw-input::placeholder { color: #666; }
#buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
}
.btn {
    background: #222;
    border: 1px solid #444;
    border-radius: 4px;
    color: #ccc;
    font-family: inherit;
    font-size: 13px;
    padding: 6px 14px;
    cursor: pointer;
    transition: background 0.15s;
}
.btn:hover { background: #333; border-color: #666; }
.btn-primary { background: #1a4a1a; border-color: #2a6a2a; }
.btn-primary:hover { background: #2a5a2a; }
.btn-danger { background: #4a1a1a; border-color: #6a2a2a; }
.btn-danger:hover { background: #5a2a2a; }
table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
    table-layout: auto;
}
th {
    background: #1a1a1a;
    border: 1px solid #333;
    padding: 6px 8px;
    text-align: right;
    font-weight: bold;
    white-space: nowrap;
}
td {
    border: 1px solid #333;
    padding: 4px 8px;
    cursor: pointer;
    word-wrap: break-word;
    overflow-wrap: break-word;
    max-width: 200px;
}
td:hover { background: #1a1a1a; }
td.editing { padding: 2px; }
td.editing input, td.editing select {
    width: 100%;
    background: #111;
    border: 1px solid #555;
    color: #ccc;
    font-family: inherit;
    font-size: inherit;
    padding: 3px 5px;
    direction: rtl;
}
.warn { color: #e0a040; }
.note { color: #80a0c0; margin: 4px 0; word-wrap: break-word; }
.unparse { color: #c08060; margin: 4px 0; word-wrap: break-word; }
.status { color: #60c060; margin: 8px 0; word-wrap: break-word; }
.error { color: #c06060; margin: 8px 0; word-wrap: break-word; }
#cmd-input {
    width: 100%;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    color: #ccc;
    font-family: inherit;
    font-size: inherit;
    padding: 6px 10px;
    margin-top: 8px;
    direction: rtl;
    outline: none;
}
#cmd-input:focus { border-color: #555; }
.row-num {
    text-align: center;
    cursor: default;
    min-width: 30px;
}
.delete-btn {
    color: #c06060;
    cursor: pointer;
    text-align: center;
    min-width: 24px;
}
.delete-btn:hover { color: #ff6060; background: #2a1a1a; }
</style>
</head>
<body>
<div id="main">
    <div id="left-pane">
        <textarea id="raw-input" autofocus></textarea>
        <div id="buttons"></div>
    </div>
    <div id="right-pane">
        <div id="output"></div>
        <input id="cmd-input" autocomplete="off" style="display:none">
    </div>
</div>
<script>
const $ = s => document.querySelector(s);
const output = $('#output');
const rawInput = $('#raw-input');
const buttons = $('#buttons');
const cmdInput = $('#cmd-input');

let state = { rows: [], notes: [], unparseable: [], phase: 'idle' };
let cfg = { items: [], locations: [], transaction_types: [], aliases: {}, ui: {} };
let editingCell = null;

// Fetch config on load
async function loadConfig() {
    try {
        const r = await fetch('/api/config');
        cfg = await r.json();
        rawInput.placeholder = cfg.ui.paste_prompt || '';
        renderButtons();
    } catch(e) { console.error('loadConfig failed', e); }
}
loadConfig();

function s(key, vars) {
    let t = (cfg.ui.strings && cfg.ui.strings[key]) || key;
    if (vars) {
        for (const [k, v] of Object.entries(vars)) {
            t = t.replace(new RegExp('\\{' + k + '\\}', 'g'), v);
        }
    }
    return t;
}

function cmd(key) {
    return (cfg.ui.commands && cfg.ui.commands[key]) || key;
}

// ---- Buttons ----
function renderButtons() {
    buttons.innerHTML = '';
    const mkBtn = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn ' + (cls || '');
        b.textContent = label;
        b.onclick = fn;
        buttons.appendChild(b);
        return b;
    };

    if (state.phase === 'idle' || state.phase === 'parsed') {
        mkBtn(s('review_parse_btn') || 'Parse', 'btn-primary', doParse);
    }
    if (state.phase === 'parsed' && state.rows.length > 0) {
        mkBtn(s('review_confirm_btn') || cmd('confirm'), 'btn-primary', doConfirm);
        mkBtn(s('review_add_row_btn') || '+', '', doAddRow);
    }
    // Always show alias/convert
    mkBtn(s('cmd_alias') || 'alias', '', () => showAliasDialog());
    mkBtn(s('cmd_convert') || 'convert', '', () => showConvertDialog());
}

// ---- Parse ----
async function doParse() {
    const text = rawInput.value.trim();
    if (!text) return;
    try {
        const r = await fetch('/api/parse', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text})
        });
        const d = await r.json();
        state.rows = d.rows || [];
        state.notes = d.notes || [];
        state.unparseable = d.unparseable || [];
        state.phase = 'parsed';
        renderAll();
    } catch(e) { showError('Parse failed: ' + e); }
}

// ---- Confirm ----
async function doConfirm() {
    if (!state.rows.length) return;
    try {
        const r = await fetch('/api/confirm', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rows: state.rows})
        });
        const d = await r.json();
        if (d.clip) {
            try { await navigator.clipboard.writeText(d.clip); }
            catch(e) { console.warn('clipboard failed', e); }
        }
        showStatus(s('clipboard_copied', {count: d.count}) || d.count + ' rows copied');

        // Check for alias/conversion learning opportunities
        if (d.alias_prompts && d.alias_prompts.length) {
            for (const [orig, canon] of d.alias_prompts) {
                const yes = cmd('yes'), no = cmd('no');
                if (confirm(s('save_alias_prompt', {original: orig, canonical: canon, yes, no}))) {
                    await fetch('/api/alias', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({alias: orig, target: canon})
                    });
                }
            }
        }
        if (d.conv_prompts && d.conv_prompts.length) {
            for (const [item, container] of d.conv_prompts) {
                const factor = prompt(s('save_conversion_prompt', {item, container}));
                if (factor && !isNaN(parseFloat(factor))) {
                    await fetch('/api/conversion', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({item, container, factor: parseFloat(factor)})
                    });
                }
            }
        }

        state.rows = [];
        state.notes = [];
        state.unparseable = [];
        state.phase = 'idle';
        rawInput.value = '';
        await loadConfig();
        renderAll();
    } catch(e) { showError('Confirm failed: ' + e); }
}

// ---- Add row ----
async function doAddRow() {
    try {
        const r = await fetch('/api/add-row', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rows: state.rows})
        });
        const d = await r.json();
        state.rows = d.rows;
        renderAll();
    } catch(e) { showError(e); }
}

// ---- Delete row ----
async function doDelete(idx) {
    try {
        const r = await fetch('/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rows: state.rows, row_idx: idx})
        });
        const d = await r.json();
        state.rows = d.rows;
        if (d.warning) showStatus(d.warning);
        renderAll();
    } catch(e) { showError(e); }
}

// ---- Edit cell ----
function startEdit(td, rowIdx, field) {
    if (editingCell) cancelEdit();
    editingCell = { td, rowIdx, field };
    td.classList.add('editing');

    const closedFields = ['inv_type', 'trans_type', 'vehicle_sub_unit'];
    const currentVal = state.rows[rowIdx][field];

    if (closedFields.includes(field)) {
        // Dropdown
        const sel = document.createElement('select');
        const options = getFieldOptions(field);
        for (const opt of options) {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            if (opt === currentVal) o.selected = true;
            sel.appendChild(o);
        }
        sel.onchange = () => commitEdit(sel.value);
        sel.onkeydown = e => { if (e.key === 'Escape') cancelEdit(); };
        td.textContent = '';
        td.appendChild(sel);
        sel.focus();
    } else {
        // Text input
        const inp = document.createElement('input');
        inp.value = currentVal != null ? String(currentVal) : '';
        inp.onkeydown = e => {
            if (e.key === 'Enter') { e.preventDefault(); commitEdit(inp.value); }
            if (e.key === 'Escape') cancelEdit();
        };
        inp.onblur = () => setTimeout(() => { if (editingCell) cancelEdit(); }, 100);
        td.textContent = '';
        td.appendChild(inp);
        inp.focus();
        inp.select();
    }
}

function getFieldOptions(field) {
    if (field === 'inv_type') return cfg.items || [];
    if (field === 'trans_type') return cfg.transaction_types || [];
    if (field === 'vehicle_sub_unit') {
        const locs = [...(cfg.locations || [])];
        if (cfg.default_source && !locs.includes(cfg.default_source)) locs.unshift(cfg.default_source);
        return locs;
    }
    return [];
}

async function commitEdit(value) {
    if (!editingCell) return;
    const { rowIdx, field } = editingCell;
    editingCell = null;
    try {
        const r = await fetch('/api/edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rows: state.rows, row_idx: rowIdx, field, value})
        });
        const d = await r.json();
        if (d.error) { showError(d.error); renderAll(); return; }
        state.rows = d.rows;
        renderAll();
    } catch(e) { showError(e); renderAll(); }
}

function cancelEdit() {
    editingCell = null;
    renderAll();
}

// ---- Alias dialog ----
function showAliasDialog() {
    const alias = prompt(s('alias_short_prompt'));
    if (!alias) return;
    const target = prompt(s('alias_maps_to_prompt'));
    if (!target) return;
    fetch('/api/alias', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({alias, target})
    }).then(r => r.json()).then(d => {
        if (d.ok) {
            showStatus(s('alias_saved', {alias, item: d.resolved || target}));
            loadConfig();
        }
    });
}

// ---- Convert dialog ----
function showConvertDialog() {
    const item = prompt(s('convert_item_prompt'));
    if (!item) return;
    const container = prompt(s('convert_container_prompt'));
    if (!container) return;
    const factor = prompt(s('convert_factor_prompt', {container}));
    if (!factor || isNaN(parseFloat(factor))) return;
    fetch('/api/conversion', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({item, container, factor: parseFloat(factor)})
    }).then(r => r.json()).then(d => {
        if (d.ok) {
            showStatus(s('conversion_saved', {item: d.item || item, container: d.container || container, factor}));
            loadConfig();
        }
    });
}

// ---- Render ----
function renderAll() {
    renderTable();
    renderButtons();
}

function renderTable() {
    output.innerHTML = '';
    if (!state.rows.length && !state.notes.length && !state.unparseable.length) {
        if (state.phase === 'parsed') {
            output.innerHTML = '<div class="warn">' + s('nothing_to_display') + '</div>';
        }
        return;
    }

    if (state.rows.length) {
        const headers = cfg.ui.table_headers || ['#','DATE','ITEM','QTY','TYPE','LOCATION','BATCH','NOTES'];
        const fields = ['date','inv_type','qty','trans_type','vehicle_sub_unit','batch','notes'];
        const tbl = document.createElement('table');

        // Header
        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        // Row # header
        const thNum = document.createElement('th');
        thNum.textContent = headers[0] || '#';
        hr.appendChild(thNum);
        // Field headers
        for (let i = 0; i < fields.length; i++) {
            const th = document.createElement('th');
            th.textContent = headers[i + 1] || fields[i];
            hr.appendChild(th);
        }
        // Delete column
        const thDel = document.createElement('th');
        thDel.textContent = '';
        thDel.style.width = '30px';
        hr.appendChild(thDel);
        thead.appendChild(hr);
        tbl.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        for (let ri = 0; ri < state.rows.length; ri++) {
            const row = state.rows[ri];
            const tr = document.createElement('tr');
            const hasWarning = !row.trans_type || !row.vehicle_sub_unit;

            // Row number
            const tdNum = document.createElement('td');
            tdNum.className = 'row-num';
            tdNum.textContent = (hasWarning ? '\u26a0 ' : '') + (ri + 1);
            tr.appendChild(tdNum);

            // Fields
            for (const field of fields) {
                const td = document.createElement('td');
                let val = row[field];
                if (val == null) val = '???';
                if (field === 'qty' && row._container) {
                    td.textContent = val + ' [' + row._container + '?]';
                } else {
                    td.textContent = String(val);
                }
                if (String(val) === '???' || val == null) td.classList.add('warn');
                td.onclick = () => startEdit(td, ri, field);
                tr.appendChild(td);
            }

            // Delete button
            const tdDel = document.createElement('td');
            tdDel.className = 'delete-btn';
            tdDel.textContent = '\u00d7';
            tdDel.title = 'Delete row';
            tdDel.onclick = () => doDelete(ri);
            tr.appendChild(tdDel);

            tbody.appendChild(tr);
        }
        tbl.appendChild(tbody);
        output.appendChild(tbl);
    }

    // Notes
    for (const note of (state.notes || [])) {
        const d = document.createElement('div');
        d.className = 'note';
        d.textContent = '\ud83d\udcdd ' + s('note_prefix') + ': "' + note + '"';
        output.appendChild(d);
    }

    // Unparseable
    for (const u of (state.unparseable || [])) {
        const d = document.createElement('div');
        d.className = 'unparse';
        d.textContent = '\u26a0 ' + s('unparseable_prefix') + ': "' + u + '"';
        output.appendChild(d);
    }
}

function showStatus(msg) {
    const d = document.createElement('div');
    d.className = 'status';
    d.textContent = msg;
    output.appendChild(d);
    setTimeout(() => d.remove(), 5000);
}

function showError(msg) {
    const d = document.createElement('div');
    d.className = 'error';
    d.textContent = String(msg);
    output.appendChild(d);
    setTimeout(() => d.remove(), 5000);
}

// ---- Keyboard shortcuts ----
rawInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        doParse();
    }
});
</script>
</body>
</html>'''


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
            '/api/add-row': self._handle_add_row,
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
        payload = {
            'items': config.get('items', []),
            'locations': config.get('locations', []),
            'default_source': config.get('default_source', ''),
            'transaction_types': config.get('transaction_types', []),
            'aliases': config.get('aliases', {}),
            'ui': {
                'commands': ui.commands,
                'field_codes': ui.field_codes,
                'field_display_names': ui.field_display_names,
                'table_headers': ui.table_headers,
                'option_letters': ui.option_letters,
                'strings': ui.strings,
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
        with _state_lock:
            config = _state['config']
            rows = _state['rows']

        # Check learning opportunities before stripping metadata
        alias_prompts = check_alias_opportunity(rows, _state.get('original_tokens', {}), config)
        conv_prompts = check_conversion_opportunity(rows, config)

        # Strip metadata
        for row in rows:
            row.pop('_container', None)
            row.pop('_raw_qty', None)

        tsv = format_rows_for_clipboard(rows)

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
            'conv_prompts': conv_prompts,
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

    def _handle_add_row(self, body):
        rows = _deserialize_rows(body.get('rows', []))
        rows.append(empty_row())
        with _state_lock:
            _state['rows'] = rows
        self._json({'rows': _serialize_rows(rows)})

    def _handle_alias(self, body):
        alias = body.get('alias', '').strip()
        target = body.get('target', '').strip()
        if not alias or not target:
            self._json({'ok': False})
            return

        with _state_lock:
            config = _state['config']

        # Fuzzy resolve target
        items = config.get('items', [])
        locations = config.get('locations', [])
        all_entities = items + locations + config.get('transaction_types', [])
        resolved, match_type = fuzzy_resolve(target, all_entities, config.get('aliases', {}))
        final_target = resolved if resolved else target

        if 'aliases' not in config:
            config['aliases'] = {}
        config['aliases'][alias] = final_target

        with _state_lock:
            save_config(config, _state['config_path'])

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

        if 'unit_conversions' not in config:
            config['unit_conversions'] = {}
        if final_item not in config['unit_conversions']:
            config['unit_conversions'][final_item] = {}
        config['unit_conversions'][final_item][final_container] = factor_val

        with _state_lock:
            save_config(config, _state['config_path'])

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

    config = load_config(config_path)
    with _state_lock:
        _state['config'] = config
        _state['config_path'] = config_path

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
