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
    get_closed_set_fields, get_field_order, get_required_fields,
    get_closed_set_options, row_has_warning,
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
#raw-input.stale { border-color: #806020; }
#reparse-hint {
    display: none;
    color: #e0a040;
    font-size: 12px;
    margin-top: 2px;
}
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
.btn-parsed { background: #1a3a1a; border-color: #2a5a2a; color: #6a6; cursor: default; }
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
/* Modal overlay */
.modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
}
.modal {
    background: #1a1a1a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 20px;
    min-width: 320px;
    max-width: 500px;
    max-height: 80vh;
    overflow-y: auto;
    direction: rtl;
}
.modal h3 { margin-bottom: 12px; color: #ddd; }
.modal .context { color: #888; font-size: 12px; margin-bottom: 10px; word-wrap: break-word; }
.modal label { display: block; margin-bottom: 6px; color: #aaa; }
.modal input[type=text], .modal input[type=number] {
    width: 100%;
    background: #111;
    border: 1px solid #555;
    border-radius: 4px;
    color: #ccc;
    font-family: inherit;
    font-size: inherit;
    padding: 6px 8px;
    margin-bottom: 10px;
    direction: rtl;
}
.modal .modal-buttons { display: flex; gap: 8px; justify-content: flex-start; margin-top: 12px; }
.modal .fuzzy-confirm { color: #e0a040; margin: 6px 0; }
/* Help panel */
#help-panel {
    display: none;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 12px;
    margin-bottom: 8px;
    font-size: 13px;
    max-height: 60vh;
    overflow-y: auto;
}
#help-panel h4 { color: #ddd; margin: 8px 0 4px 0; }
#help-panel h4:first-child { margin-top: 0; }
#help-panel .help-list { color: #aaa; margin: 2px 0 2px 16px; }
</style>
</head>
<body>
<div id="main">
    <div id="left-pane">
        <textarea id="raw-input" autofocus></textarea>
        <div id="reparse-hint"></div>
        <div id="buttons"></div>
    </div>
    <div id="right-pane">
        <div id="help-panel"></div>
        <div id="output"></div>
    </div>
</div>
<script>
const $ = s => document.querySelector(s);
const output = $('#output');
const rawInput = $('#raw-input');
const buttons = $('#buttons');
const reparseHint = $('#reparse-hint');
const helpPanel = $('#help-panel');

let state = { rows: [], notes: [], unparseable: [], phase: 'idle' };
let cfg = { items: [], locations: [], transaction_types: [], aliases: {}, ui: {}, field_options: {}, required_fields: [], field_order: [] };
let editingCell = null;
let parsedText = '';  // track what was last parsed

// Fetch config on load
async function loadConfig() {
    try {
        const r = await fetch('/api/config');
        cfg = await r.json();
        rawInput.placeholder = cfg.ui.paste_prompt || '';
        renderButtons();
        buildHelp();
    } catch(e) { console.error('loadConfig failed', e); }
}
loadConfig();

function s(key, vars) {
    let t = (cfg.ui && cfg.ui.strings && cfg.ui.strings[key]) || key;
    if (vars) {
        for (const [k, v] of Object.entries(vars)) {
            t = t.replace(new RegExp('\\{' + k + '\\}', 'g'), v);
        }
    }
    return t;
}

function cmd(key) {
    return (cfg.ui && cfg.ui.commands && cfg.ui.commands[key]) || key;
}

// ---- Auto-reparse on newline ----
let parseTimer = null;
rawInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        // Debounce: wait a tick so the newline is inserted first
        clearTimeout(parseTimer);
        parseTimer = setTimeout(() => doParse(), 50);
    }
});

// ---- Re-parse indicator (B2) ----
rawInput.addEventListener('input', () => {
    if (state.phase === 'parsed' && rawInput.value.trim() !== parsedText) {
        rawInput.classList.add('stale');
        reparseHint.style.display = 'block';
        reparseHint.textContent = s('review_parse_btn') + ' \u2190';
    } else {
        rawInput.classList.remove('stale');
        reparseHint.style.display = 'none';
    }
});

// ---- Closed-set fields from config (A4) ----
function getClosedFields() {
    if (cfg.field_options && Object.keys(cfg.field_options).length) {
        return Object.keys(cfg.field_options);
    }
    return ['inv_type', 'trans_type', 'vehicle_sub_unit'];
}

function getFieldOptions(field) {
    const fo = cfg.field_options || {};
    const configKey = fo[field];
    if (configKey && cfg[configKey]) {
        const options = [...cfg[configKey]];
        if (field === 'vehicle_sub_unit' && cfg.default_source && !options.includes(cfg.default_source)) {
            options.unshift(cfg.default_source);
        }
        return options;
    }
    // Legacy fallback
    if (field === 'inv_type') return cfg.items || [];
    if (field === 'trans_type') return cfg.transaction_types || [];
    if (field === 'vehicle_sub_unit') {
        const locs = [...(cfg.locations || [])];
        if (cfg.default_source && !locs.includes(cfg.default_source)) locs.unshift(cfg.default_source);
        return locs;
    }
    return [];
}

// ---- Warning check from config (A2) ----
function rowHasWarning(row) {
    const required = cfg.required_fields || ['trans_type', 'vehicle_sub_unit'];
    return required.some(f => row[f] == null || row[f] === '???');
}

function getIncompleteRows() {
    const incomplete = [];
    const required = cfg.required_fields || ['trans_type', 'vehicle_sub_unit'];
    for (let i = 0; i < state.rows.length; i++) {
        const row = state.rows[i];
        if (row.inv_type === '???' || required.some(f => row[f] == null)) {
            incomplete.push(i + 1);
        }
    }
    return incomplete;
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
        const parseLabel = s('review_parse_btn') || 'Parse';
        const isStale = state.phase === 'parsed' && rawInput.value.trim() !== parsedText;
        const isParsed = state.phase === 'parsed' && !isStale;
        const parseCls = isParsed ? 'btn-parsed' : 'btn-primary';
        const btn = mkBtn(isParsed ? '\u2713 ' + parseLabel : parseLabel, parseCls, doParse);
        if (isParsed) btn.title = 'Already parsed';
    }
    if (state.phase === 'parsed' && state.rows.length > 0) {
        mkBtn(s('review_confirm_btn') || cmd('confirm'), 'btn-primary', doConfirm);
    }
    mkBtn(s('cmd_alias') || 'alias', '', () => showAliasModal());
    mkBtn(s('cmd_convert') || 'convert', '', () => showConvertModal());
    mkBtn('?', '', toggleHelp);
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
        parsedText = text;
        rawInput.classList.remove('stale');
        reparseHint.style.display = 'none';
        renderAll();
    } catch(e) { showError('Parse failed: ' + e); }
}

// ---- Confirm (B1: incomplete warning) ----
async function doConfirm() {
    if (!state.rows.length) return;

    // B1: Check for incomplete fields before confirming
    const incomplete = getIncompleteRows();
    if (incomplete.length) {
        const rowList = incomplete.join(', ');
        const msg = s('confirm_incomplete_warning', {
            row_list: rowList,
            yes: cmd('yes'),
            no: cmd('no')
        });
        if (!confirm(msg)) return;
    }

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
        showStatus(s('clipboard_copied', {count: String(d.count)}) || d.count + ' rows copied');

        // Alias learning
        if (d.alias_prompts && d.alias_prompts.length) {
            for (const [orig, canon] of d.alias_prompts) {
                if (confirm(s('save_alias_prompt', {original: orig, canonical: canon, yes: cmd('yes'), no: cmd('no')}))) {
                    await fetch('/api/alias', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({alias: orig, target: canon})
                    });
                }
            }
        }
        // Conversion learning — use modal
        if (d.conv_prompts && d.conv_prompts.length) {
            for (const [item, container] of d.conv_prompts) {
                await showConvertLearnModal(item, container);
            }
        }

        state.rows = [];
        state.notes = [];
        state.unparseable = [];
        state.phase = 'idle';
        parsedText = '';
        rawInput.value = '';
        await loadConfig();
        renderAll();
    } catch(e) { showError('Confirm failed: ' + e); }
}

// ---- Add row ----
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

    const closedFields = getClosedFields();
    const currentVal = state.rows[rowIdx][field];

    if (closedFields.includes(field)) {
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

// ============================================================
// Modal system (B4: replaces prompt() with context-rich dialogs)
// ============================================================

function createModal(title) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const modal = document.createElement('div');
    modal.className = 'modal';
    const h3 = document.createElement('h3');
    h3.textContent = title;
    modal.appendChild(h3);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    return { overlay, modal };
}

function addContext(modal, label, items) {
    if (!items || !items.length) return;
    const ctx = document.createElement('div');
    ctx.className = 'context';
    ctx.textContent = label + ' ' + items.join(', ');
    modal.appendChild(ctx);
}

function addInput(modal, label, id, type) {
    const lbl = document.createElement('label');
    lbl.textContent = label;
    modal.appendChild(lbl);
    const inp = document.createElement('input');
    inp.type = type || 'text';
    inp.id = id;
    modal.appendChild(inp);
    return inp;
}

function addButtons(modal, overlay, onOk, okLabel, cancelLabel) {
    const div = document.createElement('div');
    div.className = 'modal-buttons';
    const okBtn = document.createElement('button');
    okBtn.className = 'btn btn-primary';
    okBtn.textContent = okLabel || 'OK';
    okBtn.onclick = () => onOk(overlay);
    div.appendChild(okBtn);
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn';
    cancelBtn.textContent = cancelLabel || s('edit_cancelled').trim() || 'Cancel';
    cancelBtn.onclick = () => overlay.remove();
    div.appendChild(cancelBtn);
    modal.appendChild(div);
}

// ---- Alias modal (B4 + B5) ----
function showAliasModal() {
    const { overlay, modal } = createModal(s('cmd_alias'));
    addContext(modal, s('help_items_header'), cfg.items);
    addContext(modal, s('help_locations_header'), cfg.locations);
    if (cfg.aliases && Object.keys(cfg.aliases).length) {
        const aliasLines = Object.entries(cfg.aliases).map(([a,t]) => a + ' \u2192 ' + t);
        addContext(modal, s('help_aliases_header'), aliasLines);
    }
    const aliasInp = addInput(modal, s('alias_short_prompt'), 'modal-alias', 'text');
    const targetInp = addInput(modal, s('alias_maps_to_prompt'), 'modal-target', 'text');

    const fuzzyDiv = document.createElement('div');
    fuzzyDiv.className = 'fuzzy-confirm';
    fuzzyDiv.style.display = 'none';
    modal.appendChild(fuzzyDiv);

    addButtons(modal, overlay, async (ov) => {
        const alias = aliasInp.value.trim();
        const target = targetInp.value.trim();
        if (!alias || !target) return;

        const r = await fetch('/api/alias', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({alias, target})
        });
        const d = await r.json();

        // B5: fuzzy match confirmation
        if (d.ok && d.match_type === 'fuzzy') {
            const confirmMsg = s('fuzzy_confirm', {resolved: d.resolved, yes: cmd('yes'), no: cmd('no')});
            if (!confirm(confirmMsg)) {
                // Undo: re-save without this alias
                // For simplicity, just warn and let user fix manually
                ov.remove();
                return;
            }
        }

        if (d.ok) {
            showStatus(s('alias_saved', {alias, item: d.resolved || target}));
            await loadConfig();
        }
        ov.remove();
    }, s('review_confirm_btn'));

    aliasInp.focus();
}

// ---- Convert modal (B4) ----
function showConvertModal() {
    const { overlay, modal } = createModal(s('cmd_convert'));
    addContext(modal, s('help_items_header'), cfg.items);
    // Show known containers
    const containers = new Set();
    for (const convs of Object.values(cfg.unit_conversions || {})) {
        for (const k of Object.keys(convs)) {
            if (k !== 'base_unit') containers.add(k);
        }
    }
    if (containers.size) {
        addContext(modal, s('convert_container_prompt').replace(':','') + ':', [...containers]);
    }
    const itemInp = addInput(modal, s('convert_item_prompt'), 'modal-conv-item', 'text');
    const contInp = addInput(modal, s('convert_container_prompt'), 'modal-conv-cont', 'text');
    const factorInp = addInput(modal, s('convert_factor_prompt', {container: '...'}), 'modal-conv-factor', 'number');

    addButtons(modal, overlay, async (ov) => {
        const item = itemInp.value.trim();
        const container = contInp.value.trim();
        const factor = factorInp.value.trim();
        if (!item || !container || !factor || isNaN(parseFloat(factor))) return;

        const r = await fetch('/api/conversion', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({item, container, factor: parseFloat(factor)})
        });
        const d = await r.json();
        if (d.ok) {
            showStatus(s('conversion_saved', {item: d.item || item, container: d.container || container, factor}));
            await loadConfig();
        }
        ov.remove();
    }, s('review_confirm_btn'));

    itemInp.focus();
}

// ---- Convert learn modal (post-confirm) ----
function showConvertLearnModal(item, container) {
    return new Promise(resolve => {
        const { overlay, modal } = createModal(s('save_conversion_prompt', {item, container}));
        const factorInp = addInput(modal, s('convert_factor_prompt', {container}), 'modal-learn-factor', 'number');
        addButtons(modal, overlay, async (ov) => {
            const factor = factorInp.value.trim();
            if (factor && !isNaN(parseFloat(factor))) {
                await fetch('/api/conversion', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({item, container, factor: parseFloat(factor)})
                });
            }
            ov.remove();
            resolve();
        }, s('review_confirm_btn'));
        const skipBtn = modal.querySelector('.modal-buttons .btn:not(.btn-primary)');
        if (skipBtn) {
            const origClick = skipBtn.onclick;
            skipBtn.onclick = () => { origClick(); resolve(); };
        }
        factorInp.focus();
    });
}

// ---- Help panel (B3) ----
function toggleHelp() {
    helpPanel.style.display = helpPanel.style.display === 'none' ? 'block' : 'none';
}

function buildHelp() {
    helpPanel.innerHTML = '';
    const addSection = (title, items) => {
        if (!items || !items.length) return;
        const h4 = document.createElement('h4');
        h4.textContent = title;
        helpPanel.appendChild(h4);
        for (const item of items) {
            const d = document.createElement('div');
            d.className = 'help-list';
            d.textContent = item;
            helpPanel.appendChild(d);
        }
    };

    addSection(s('help_items_header'), (cfg.items || []).map(item => {
        const itemAliases = Object.entries(cfg.aliases || {}).filter(([,v]) => v === item).map(([k]) => k);
        return itemAliases.length ? item + '  (' + itemAliases.join(', ') + ')' : item;
    }));
    addSection(s('help_locations_header'), cfg.locations || []);
    addSection(s('help_commands_header'), [
        'Ctrl+Enter: ' + s('review_parse_btn'),
    ]);

    // Field codes
    if (cfg.ui && cfg.ui.field_codes) {
        const codes = Object.entries(cfg.ui.field_codes).map(([letter, field]) => {
            const name = (cfg.ui.field_display_names && cfg.ui.field_display_names[field]) || field;
            return letter + ' = ' + name;
        });
        addSection(s('help_field_codes_header'), codes);
    }
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
        const fields = cfg.field_order || cfg.ui.field_order || ['date','inv_type','qty','trans_type','vehicle_sub_unit','batch','notes'];
        const headers = cfg.ui.table_headers || ['#','DATE','ITEM','QTY','TYPE','LOCATION','BATCH','NOTES'];
        const tbl = document.createElement('table');

        // Header
        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        const thNum = document.createElement('th');
        thNum.textContent = headers[0] || '#';
        hr.appendChild(thNum);
        for (let i = 0; i < fields.length; i++) {
            const th = document.createElement('th');
            th.textContent = headers[i + 1] || fields[i];
            hr.appendChild(th);
        }
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
            const hasWarning = rowHasWarning(row);

            const tdNum = document.createElement('td');
            tdNum.className = 'row-num';
            tdNum.textContent = (hasWarning ? '\u26a0 ' : '') + (ri + 1);
            tr.appendChild(tdNum);

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

    for (const note of (state.notes || [])) {
        const d = document.createElement('div');
        d.className = 'note';
        d.textContent = '\ud83d\udcdd ' + s('note_prefix') + ': "' + note + '"';
        output.appendChild(d);
    }

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
            'unit_conversions': config.get('unit_conversions', {}),
            'field_options': config.get('field_options', {}),
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

        tsv = format_rows_for_clipboard(rows, config)

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
