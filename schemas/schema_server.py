"""Локальный сервер для просмотра и редактирования схемы.

GET  — статика из папки, для редактируемых файлов отдает ETag (sha1 содержимого).
PUT  /schema.mmd с заголовком If-Match: <etag> — атомарно перезаписывает файл.
     Если файл успел измениться, отвечает 409 и присылает актуальные текст и etag.
Запуск: python3 schemas/schema_server.py [папка] [порт]. По умолчанию отдает папку со скриптом на порту 8765.
Слушает только 127.0.0.1.
"""
import hashlib
import http.server
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
EDITABLE = {'schema.mmd'}


def etag_of(data: bytes) -> str:
    return '"' + hashlib.sha1(data).hexdigest() + '"'


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if self.command != 'GET':
            sys.stderr.write('%s %s\n' % (self.command, fmt % args))

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _name(self):
        name = self.path.split('?', 1)[0].lstrip('/')
        return name if name in EDITABLE else None

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        name = self._name()
        if not name:
            return super().do_GET()
        with open(os.path.join(ROOT, name), 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('ETag', etag_of(data))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self):
        name = self._name()
        if not name:
            return self._json(403, {'error': 'файл нельзя редактировать'})
        path = os.path.join(ROOT, name)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        with open(path, 'rb') as f:
            current = f.read()
        if self.headers.get('If-Match') != etag_of(current):
            return self._json(409, {'etag': etag_of(current), 'text': current.decode('utf-8')})
        fd, tmp = tempfile.mkstemp(dir=ROOT, prefix='.schema-', suffix='.tmp')
        with os.fdopen(fd, 'wb') as f:
            f.write(body)
        os.replace(tmp, path)
        self._json(200, {'etag': etag_of(body)})


if __name__ == '__main__':
    print(f'Serving {ROOT} on http://127.0.0.1:{PORT}', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
