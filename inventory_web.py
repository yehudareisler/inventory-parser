"""Web-based terminal for the inventory parser.

Same text workflow as the CLI, rendered in a browser for proper Hebrew RTL.
Run with: python inventory_web.py
"""

import http.server
import json
import queue
import socketserver
import sys
import threading
import webbrowser

from inventory_tui import main as tui_main

_output_buf = []
_output_lock = threading.Lock()
_input_queue = queue.Queue()
_clipboard_queue = queue.Queue()


class _WebOut:
    def write(self, s):
        if s:
            with _output_lock:
                _output_buf.append(s)
        return len(s) if s else 0

    def flush(self):
        pass


class _WebIn:
    def readline(self):
        line = _input_queue.get()
        if line is None:
            raise EOFError
        return line + '\n'


_HTML = r'''<!DOCTYPE html>
<html lang="he">
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
    padding: 12px;
    height: 100vh;
    display: flex;
    flex-direction: column;
}
#term { flex: 1; overflow-y: auto; }
.ln { white-space: pre; min-height: 1.3em; }
#input {
    width: 100%;
    background: transparent;
    border: none;
    color: #cccccc;
    font-family: inherit;
    font-size: inherit;
    outline: none;
    direction: rtl;
    caret-color: #cccccc;
    padding: 2px 0;
}
</style>
</head>
<body>
<div id="term"></div>
<input id="input" autofocus autocomplete="off">
<script>
const term = document.getElementById('term');
const inp = document.getElementById('input');
let cur = '';
const curEl = document.createElement('div');
curEl.className = 'ln';
curEl.dir = 'auto';
term.appendChild(curEl);

function finalize() {
    const d = document.createElement('div');
    d.className = 'ln';
    d.dir = 'auto';
    d.textContent = cur;
    term.insertBefore(d, curEl);
    cur = '';
    curEl.textContent = '';
}

async function poll() {
    try {
        const r = await fetch('/o');
        const d = await r.json();
        if (d.t) {
            for (const ch of d.t) {
                if (ch === '\n') { finalize(); }
                else { cur += ch; curEl.textContent = cur; }
            }
            term.scrollTop = term.scrollHeight;
        }
        if (d.clip) {
            try { await navigator.clipboard.writeText(d.clip); }
            catch(e) { console.warn('clipboard write failed', e); }
        }
    } catch(e) {}
    setTimeout(poll, 80);
}
poll();

inp.addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const v = inp.value; inp.value = '';
    cur += v; finalize();
    term.scrollTop = term.scrollHeight;
    await fetch('/i', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({t: v})
    });
});

inp.addEventListener('paste', e => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text.includes('\n')) return;
    e.preventDefault();
    const lines = text.split('\n');
    (async () => {
        for (const line of lines) {
            cur += line; finalize();
            await fetch('/i', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({t: line})
            });
            await new Promise(r => setTimeout(r, 30));
        }
        term.scrollTop = term.scrollHeight;
    })();
});

document.addEventListener('click', () => inp.focus());
</script>
</body>
</html>'''


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self._ok('text/html', _HTML.encode())
        elif self.path == '/o':
            with _output_lock:
                t = ''.join(_output_buf)
                _output_buf.clear()
            clip = None
            try:
                clip = _clipboard_queue.get_nowait()
            except queue.Empty:
                pass
            payload = {'t': t}
            if clip is not None:
                payload['clip'] = clip
            self._ok('application/json', json.dumps(payload, ensure_ascii=False).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/i':
            body = json.loads(
                self.rfile.read(int(self.headers.get('Content-Length', 0))))
            _input_queue.put(body.get('t', ''))
            self._ok('application/json', b'{}')
        else:
            self.send_error(404)

    def _ok(self, ct, body):
        self.send_response(200)
        self.send_header('Content-Type', ct + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    port = 8765
    config = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.yaml') else 'config_he.yaml'

    real_out = sys.__stdout__
    sys.stdout = _WebOut()
    sys.stdin = _WebIn()

    # Route clipboard through the browser instead of system tools
    import inventory_tui
    def _web_clipboard(text):
        _clipboard_queue.put(text)
        return True
    inventory_tui._clipboard_fn = _web_clipboard

    threading.Thread(target=tui_main, args=(config,), daemon=True).start()

    class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = _ThreadedServer(('127.0.0.1', port), _H)
    real_out.write(f'http://localhost:{port}\n')
    real_out.flush()
    webbrowser.open(f'http://localhost:{port}')

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
