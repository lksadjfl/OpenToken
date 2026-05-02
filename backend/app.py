import json
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / 'data.db'
STATIC = BASE / 'static'


def init_db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        key_mask TEXT NOT NULL,
        permissions TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT NOT NULL,
        prompt TEXT NOT NULL,
        response TEXT NOT NULL,
        status TEXT NOT NULL,
        tokens INTEGER NOT NULL,
        latency_ms INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.commit(); c.close()


def db(q, args=(), one=False):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cur = c.execute(q, args)
    c.commit()
    rows = cur.fetchall()
    c.close()
    return (dict(rows[0]) if rows else None) if one else [dict(r) for r in rows]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code=200, body='', ctype='application/json'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            return self._send(200, json.dumps({'ok': True}))
        if self.path == '/api/keys':
            return self._send(200, json.dumps(db('SELECT * FROM api_keys ORDER BY id DESC')))
        if self.path == '/api/logs':
            return self._send(200, json.dumps(db('SELECT * FROM logs ORDER BY id DESC LIMIT 20')))
        if self.path in ['/', '/index.html']:
            return self._send(200, (STATIC / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/styles.css':
            return self._send(200, (STATIC / 'styles.css').read_bytes(), 'text/css; charset=utf-8')
        if self.path == '/app.js':
            return self._send(200, (STATIC / 'app.js').read_bytes(), 'application/javascript; charset=utf-8')
        return self._send(404, json.dumps({'error': 'not found'}))

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length) or '{}')
        now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'

        if self.path == '/api/keys':
            name = (body.get('name') or 'default-key').strip() or 'default-key'
            permissions = body.get('permissions', 'All')
            mask = 'sk-****' + str(int(datetime.utcnow().timestamp()))[-4:]
            db('INSERT INTO api_keys(name,key_mask,permissions,status,created_at) VALUES(?,?,?,?,?)',
               (name, mask, permissions, 'Active', now))
            row = db('SELECT * FROM api_keys ORDER BY id DESC LIMIT 1', one=True)
            return self._send(201, json.dumps(row))

        if self.path == '/api/playground':
            prompt = (body.get('prompt') or '').strip()
            model = body.get('model', 'deepseek-chat')
            if not prompt:
                return self._send(400, json.dumps({'error': 'prompt is required'}))
            response = f'[Mock:{model}] 已收到你的请求：{prompt[:120]}'
            tokens = max(20, len(prompt) // 2)
            db('INSERT INTO logs(model,prompt,response,status,tokens,latency_ms,created_at) VALUES(?,?,?,?,?,?,?)',
               (model, prompt, response, 'success', tokens, 320, now))
            return self._send(200, json.dumps({'model': model, 'response': response, 'tokens': tokens, 'latency_ms': 320}))

        return self._send(404, json.dumps({'error': 'not found'}))


if __name__ == '__main__':
    init_db()
    HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
