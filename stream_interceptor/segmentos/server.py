import os
import re
import ssl
import urllib.request
import urllib.error
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urljoin

from proxy.cache import (
    CACHE_DIR, ctx_no_verify,
    get_cached, get_downloading_event, segment_cache
)

# Estado inyectado desde main.py
_state = {
    "manifest_rewritten": None,
    "manifest_url":       None,
    "cdn_token_base":     None,
    "captured_headers":   {},
    "platform":           None,   # instancia de BasePlatform
}
_lock = threading.Lock()

def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self._handle('HEAD')

    def do_GET(self):
        self._handle('GET')

    def _handle(self, method='GET'):
        path = self.path

        # ── Manifiesto ────────────────────────────────────────────────────────
        if path in ('/', '/live', '/live.m3u8', '/live.mpd'):
            with _lock:
                body = _state["manifest_rewritten"]
                murl = _state["manifest_url"]
            if not murl or body is None:
                self.send_error(503, "Sin stream capturado aun")
                return
            encoded = body.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(encoded)
            return

        # ── Segmentos ─────────────────────────────────────────────────────────
        target = self._resolve(path)
        if not target:
            self.send_error(400, "No se pudo resolver URL")
            return

        frag = re.search(r'[Ff]rag-(\d+)|[Ss]eg-(\d+)|[Cc]hunk-(\d+)', target)
        n    = next((g for g in (frag.groups() if frag else []) if g), None)
        label = f"Seg-{n}" if n else target[-35:]

        # 1. Desde cache (pausa/seek)
        cached = get_cached(target)
        if cached and os.path.exists(cached):
            print(f"💾 {label}")
            self._serve_file(cached, method)
            return

        # 2. Esperando descarga en curso
        ev = get_downloading_event(target)
        if ev:
            print(f"⏳ {label} esperando...")
            ev.wait(timeout=60)
            cached = get_cached(target)
            if cached and os.path.exists(cached):
                self._serve_file(cached, method)
                return

        # 3. On-demand
        print(f"🔗 {label} on-demand")
        with _lock:
            hdrs     = dict(_state["captured_headers"])
            platform = _state["platform"]

        try:
            skip  = {'host', 'content-length', 'connection',
                     'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in hdrs.items() if k.lower() not in skip}
            req    = urllib.request.Request(target, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            raw  = resp.read()

            transform = platform.transform_segment if platform else lambda d, u: ('video/mp2t', d)
            ct, data  = transform(raw, target)

            if ct is None:
                self.send_error(502, "Segmento invalido")
                return

            print(f"    ✅ {ct} | {len(data):,} bytes")

            # Cachear on-demand
            cpath = os.path.join(CACHE_DIR, f"od_{abs(hash(target)) % 999999:06d}")
            with open(cpath, 'wb') as f:
                f.write(data)
            segment_cache[target] = cpath

            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(data)

        except urllib.error.HTTPError as e:
            print(f"    ❌ HTTP {e.code} {e.reason}")
            try:
                self.send_error(e.code, e.reason)
            except Exception:
                pass
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"    ⚠️  {type(e).__name__}: {e}")

    def _serve_file(self, path, method):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(data)
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"    ⚠️  serve_file: {e}")

    def _resolve(self, path):
        if path.startswith('/https://'):
            return path[1:]
        if path.startswith('/http://'):
            return path[1:]
        if path.startswith('/'):
            with _lock:
                base = _state["cdn_token_base"] or _state["manifest_url"]
            if base:
                base_dir = base if base.endswith('/') else base.rsplit('/', 1)[0] + '/'
                return urljoin(base_dir, path.lstrip('/'))
        return None


def start(port: int):
    server = ThreadingHTTPServer(('0.0.0.0', port), ProxyHandler)
    print(f"🎬 Proxy local (threading) en puerto {port}")
    server.serve_forever()
