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
    "platform":           None,
}
_lock = threading.Lock()

# Cache de sub-manifiestos
_sub_manifest_cache = {}  # url -> rewritten_content

def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)

def update_sub_manifest(url, content):
    """Guarda un sub-manifiesto en cache"""
    with _lock:
        _sub_manifest_cache[url] = content

def get_sub_manifest(url):
    """Obtiene un sub-manifiesto del cache"""
    with _lock:
        return _sub_manifest_cache.get(url)

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

        # ── Manifiesto principal ──────────────────────────────────────────────
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

        # ── Resolver URL destino ──────────────────────────────────────────────
        target = self._resolve(path)
        if not target:
            self.send_error(400, "No se pudo resolver URL")
            return

        # ── Sub-manifiesto (m3u8) ─────────────────────────────────────────────
        if '.m3u8' in target or '.mpd' in target:
            self._handle_manifest(target, method)
            return

        # ── Segmentos de video ────────────────────────────────────────────────
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
        self._fetch_and_serve_segment(target, method, label)

    def _handle_manifest(self, target, method):
        """Maneja peticiones de sub-manifiestos m3u8/mpd"""
        # Verificar si ya lo tenemos en cache
        cached = get_sub_manifest(target)
        if cached:
            print(f"📄 Sub-manifiesto cacheado: {target[-50:]}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Content-Length', str(len(cached)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(cached.encode('utf-8'))
            return

        # Descargar el sub-manifiesto
        print(f"📄 Descargando sub-manifiesto: {target[-50:]}...")
        with _lock:
            hdrs = dict(_state["captured_headers"])
            platform = _state["platform"]
            lip = _state.get("local_ip", "127.0.0.1")
            proxy_port = _state.get("proxy_port", 8888)

        try:
            skip = {'host', 'content-length', 'connection', 'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in hdrs.items() if k.lower() not in skip}
            req = urllib.request.Request(target, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=30)
            raw = resp.read()

            # Reescribir URLs del sub-manifiesto
            from proxy.rewriter import rewrite_m3u8
            rewritten = rewrite_m3u8(raw, target, lip, proxy_port)

            # Guardar en cache
            update_sub_manifest(target, rewritten)

            print(f"   ✅ Sub-manifiesto reescrito ({len(rewritten)} bytes)")

            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Content-Length', str(len(rewritten)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(rewritten.encode('utf-8'))

        except urllib.error.HTTPError as e:
            print(f"   ❌ HTTP {e.code} {e.reason}")
            self.send_error(e.code, e.reason)
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.send_error(502, str(e))

    def _fetch_and_serve_segment(self, target, method, label):
        """Descarga y sirve un segmento de video"""
        with _lock:
            hdrs = dict(_state["captured_headers"])
            platform = _state["platform"]

        try:
            skip = {'host', 'content-length', 'connection',
                    'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in hdrs.items() if k.lower() not in skip}
            req = urllib.request.Request(target, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            raw = resp.read()

            transform = platform.transform_segment if platform else lambda d, u: ('video/mp2t', d)
            ct, data = transform(raw, target)

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