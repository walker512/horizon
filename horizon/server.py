"""Single-user, loopback-only interface. Source URLs are never fetched."""
import argparse
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .model import Store
from .export import markdown, html_brief

ROOT=Path(__file__).resolve().parent.parent

def bounded_json(raw):
    try:
        data = json.loads(raw)
    except RecursionError:
        raise ValueError('JSON nesting exceeds the maximum depth of 32.') from None
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if isinstance(value, (dict, list)):
            if depth >= 32:
                raise ValueError('JSON nesting exceeds the maximum depth of 32.')
            pending.extend((child, depth + 1) for child in (value.values() if isinstance(value, dict) else value))
    return data

def serve(host='127.0.0.1',port=8769,data=None):
    if host!='127.0.0.1':raise ValueError('This single-user preview only binds to 127.0.0.1.')
    store=Store(Path(data or Path.home()/'.horizon')/'workspace.sqlite3')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not log source URLs, imported text, query strings or request payloads.
            print(f'Horizon {self.command} {self.path.split("?")[0]}')
        def reply(self,status,payload,mime='application/json',filename=None):
            body=json.dumps(payload,ensure_ascii=False).encode() if mime=='application/json' else payload.encode() if isinstance(payload,str) else payload
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers();self.wfile.write(body)
        def allowed(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                self.reply(403,{'error':'Invalid local Host header.'});return False
            return True
        def do_GET(self):
            if not self.allowed():return
            try:
                u=urlsplit(self.path)
                if u.path=='/api/state':return self.reply(200,store.state())
                if u.path=='/api/export':
                    fmt=parse_qs(u.query).get('format',['json'])[0]
                    if fmt=='json':return self.reply(200,store.portable(),filename='horizon-project.json')
                    if fmt=='markdown':return self.reply(200,markdown(store.state()),'text/markdown; charset=utf-8','horizon-brief.md')
                    if fmt=='html':return self.reply(200,html_brief(store.state()),'text/html; charset=utf-8','horizon-brief.html')
                    raise ValueError('Unknown export format.')
                routes={'/':('index.html','text/html; charset=utf-8'),'/index.html':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
                if u.path not in routes:return self.reply(404,{'error':'Not found.'})
                name,mime=routes[u.path];self.reply(200,(ROOT/'public'/name).read_bytes(),mime)
            except (ValueError,sqlite3.Error,OSError) as e:self.reply(400,{'error':str(e)[:1000]})
        def do_POST(self):
            if not self.allowed():return
            if self.headers.get('Origin') not in {None,f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:
                return self.reply(403,{'error':'Cross-origin writes are blocked.'})
            if self.headers.get_content_type()!='application/json':return self.reply(415,{'error':'JSON requests required.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=12*1024*1024:raise ValueError('Request must be between 1 byte and 12 MB.')
                data=bounded_json(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
                u=urlsplit(self.path)
                if not u.path.startswith('/api/'):return self.reply(404,{'error':'Not found.'})
                self.reply(200,store.apply(u.path[5:],data))
            except (ValueError,TypeError,KeyError,sqlite3.Error,OSError) as e:
                self.reply(400,{'error':str(e)[:1000]})
    server=ThreadingHTTPServer((host,port),Handler)
    print(f'Horizon by walker512: http://{host}:{port}\nLocal data: {store.path}\nNo source fetching, AI calls, subscriptions or external publishing.')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

def main():
    parser=argparse.ArgumentParser(description='Horizon local editorial evidence workbench')
    parser.add_argument('--port',type=int,default=8769)
    parser.add_argument('--data-dir',default=os.environ.get('HORIZON_DATA'))
    args=parser.parse_args()
    serve(port=args.port,data=args.data_dir)

if __name__=='__main__':main()
