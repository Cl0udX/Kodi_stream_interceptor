"""
universal_interceptor.py - Addon para mitmproxy
Intercepta streams HLS/DASH de múltiples plataformas y los envía a Kodi.

Plataformas soportadas:
  - Netu / cfglobalcdn
  - StreamWish (segmentos disfrazados como PNG)
  - VidHide
  - FileMoon (segmentos PNG)
  - VOE.sx
  - Cualquier plataforma que sirva un .m3u8 detectable

Uso:
    mitmdump -s ~/Documents/Kodi/netu_interceptor.py --listen-port 8082 --quiet
"""
import ssl
import json
import re
import urllib.request
import urllib.error
import threading
import socket
import os
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urljoin
from mitmproxy import http

# ─── Config ───────────────────────────────────────────────────────────────────
KODI_IP          = "192.168.128.10"
KODI_PORT        = 8080
LOCAL_PROXY_PORT = 8888

# Directorio temporal para cache
CACHE_DIR = tempfile.mkdtemp(prefix="stream_cache_")

# ─── Dominios CDN a interceptar ───────────────────────────────────────────────
# El interceptor captura cualquier .m3u8 que venga de estos dominios
CDN_PATTERNS = [
    # Netu / cfglobalcdn
    r"cfglobalcdn\.com",
    r"cdnglobalcheck\.com",
    # StreamWish
    r"streamwish\.com",
    r"playerwish\.com",
    r"wishonly\.com",
    r"awish\.one",
    r"dwish\.net",
    # VidHide
    r"vidhide\.com",
    r"vidhidepro\.com",
    r"vidhideplus\.com",
    # FileMoon
    r"filemoon\.sx",
    r"filemoon\.to",
    r"moonplayer\.org",
    # VOE.sx
    r"voe\.sx",
    r"launchrelaying\.com",
    r"dieudurable\.com",
    # Streamtape
    r"streamtape\.com",
    r"streamtape\.net",
    # Genérico: cualquier dominio que sirva un m3u8 con estos patrones
    r"cdn\d*\.",
    r"storage\d*\.",
]

# URLs que son segmentos (no manifiestos)
SEGMENT_PATTERNS = [
    r"/Frag-\d+",
    r"/seg-\d+",
    r"/chunk-\d+",
    r"/fragment-\d+",
    r"\.ts($|\?)",
    r"\.mp4($|\?)",
    r"\.m4s($|\?)",
    r"/index\d+\.ts",
]

# ─── SSL Context ──────────────────────────────────────────────────────────────
ctx_no_verify = ssl._create_unverified_context()

# ─── Estado global ────────────────────────────────────────────────────────────
state_lock         = threading.Lock()
captured_headers   = {}
manifest_url       = None
manifest_rewritten = None
cdn_token_base     = None
local_proxy_ip     = None
kodi_notified      = False
segment_cache      = {}       # { url: cache_path }
segment_downloading = {}      # { url: Event }

# ─── Detección de plataforma ──────────────────────────────────────────────────
def is_cdn_url(url):
    return any(re.search(p, url) for p in CDN_PATTERNS)

def is_segment_url(url):
    return any(re.search(p, url) for p in SEGMENT_PATTERNS)

def is_manifest_url(url):
    """Manifiesto = URL de CDN que termina en m3u8 o no tiene extensión de segmento."""
    if not is_cdn_url(url):
        return False
    if is_segment_url(url):
        return False
    # Debe ser un m3u8 explícito o una URL sin extensión de segmento conocida
    return '.m3u8' in url or not re.search(r'\.(ts|mp4|m4s|png|jpg)($|\?)', url)

# ─── Transformers de segmentos ────────────────────────────────────────────────
PNG_HEADER = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
FF_PADDING = bytes([0xFF])

def strip_png_wrapper(data):
    """
    StreamWish, FileMoon y otros disfrazan los .ts como PNG.
    Detecta y stripea el header PNG falso para devolver MPEG-TS limpio.
    """
    if data[:8] == PNG_HEADER:
        # Buscar el sync byte de MPEG-TS (0x47) después del header PNG
        # Los segmentos reales empiezan con 0x47 cada 188 bytes
        for i in range(8, min(len(data), 512)):
            if data[i] == 0x47:
                # Verificar que es realmente MPEG-TS (sync cada 188 bytes)
                if i + 188 < len(data) and data[i + 188] == 0x47:
                    return data[i:]
        # Fallback: remover solo el header PNG estándar (8 bytes)
        return data[8:]
    
    # Algunos usan padding 0xFF al inicio
    if data and data[0] == 0xFF and len(data) > 188:
        stripped = data.lstrip(b'\xff')
        if stripped and stripped[0] == 0x47:
            return stripped
    
    return data

def detect_segment_type(data, url):
    """Detecta si el segmento es TS, MP4/fMP4, o está envuelto en PNG."""
    if not data:
        return 'video/mp2t', data
    
    # PNG wrapper (StreamWish, FileMoon)
    if data[:8] == PNG_HEADER or (data[0] == 0xFF and len(data) > 188):
        clean = strip_png_wrapper(data)
        if clean and clean[0] == 0x47:
            return 'video/mp2t', clean
    
    # MPEG-TS real (sync byte 0x47)
    if data[0] == 0x47:
        return 'video/mp2t', data
    
    # fMP4 (ISO Base Media)
    if len(data) > 8 and data[4:8] in (b'ftyp', b'moof', b'mdat', b'moov'):
        return 'video/mp4', data
    
    # HTML de error disfrazado — igual forzar mp2t (Kodi lo rechaza de todas formas)
    if data[:15].lower().startswith(b'<!doctype') or data[:6].lower() == b'<html>':
        return None, data  # Error real
    
    # Default: asumir TS
    return 'video/mp2t', data

# ─── Extractor de token base ──────────────────────────────────────────────────
def extract_token_base(url):
    """Extrae la base de la URL con token para reconstruir segmentos relativos."""
    # Netu/cfglobalcdn: .../secip/ID/ID/TOKEN/IP/TIMESTAMP/
    match = re.search(
        r'(https?://[^/]+/(?:silverlight/)?secip/\d+/\d+/[^/]+/[^/]+/\d{9,11}/)',
        url
    )
    if match:
        return match.group(1)
    
    # VOE.sx y similares: timestamp numérico en el path
    parts = url.split('/')
    for i, part in enumerate(parts):
        if re.match(r'^\d{9,11}$', part):
            return '/'.join(parts[:i+1]) + '/'
    
    # Fallback: directorio padre
    return url.rsplit('/', 1)[0] + '/'

# ─── Reescritor de M3U8 ───────────────────────────────────────────────────────
def rewrite_m3u8(content_bytes, base_url, proxy_ip, proxy_port):
    text     = content_bytes.decode('utf-8', errors='ignore')
    lines    = text.split('\n')
    out      = []
    base_dir = base_url.rsplit('/', 1)[0] + '/'

    for line in lines:
        s = line.strip()
        if not s:
            out.append('')
            continue
        if s.startswith('#'):
            if 'URI="' in s:
                def replace_uri(m):
                    uri = m.group(1)
                    full = uri if uri.startswith('http') else urljoin(base_dir, uri)
                    return f'URI="http://{proxy_ip}:{proxy_port}/{full}"'
                s = re.sub(r'URI="([^"]+)"', replace_uri, s)
            out.append(s)
            continue
        full = s if s.startswith('http') else urljoin(base_dir, s)
        out.append(f"http://{proxy_ip}:{proxy_port}/{full}")

    return '\n'.join(out)

def extract_segment_urls(content_bytes, base_url):
    text     = content_bytes.decode('utf-8', errors='ignore')
    base_dir = base_url.rsplit('/', 1)[0] + '/'
    urls     = []
    for line in text.split('\n'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        full = s if s.startswith('http') else urljoin(base_dir, s)
        urls.append(full)
    return urls

# ─── Pre-descarga en background ───────────────────────────────────────────────
def prefetch_segments(segment_urls, headers):
    total = len(segment_urls)
    print(f"⬇️  Pre-descargando {total} segmentos...")

    def download_one(url, idx):
        with state_lock:
            if url in segment_cache:
                return
            if url in segment_downloading:
                return
            ev = threading.Event()
            segment_downloading[url] = ev

        cache_path = os.path.join(CACHE_DIR, f"seg_{idx:05d}")
        try:
            skip = {'host', 'content-length', 'connection',
                    'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in headers.items() if k.lower() not in skip}
            req    = urllib.request.Request(url, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            raw  = resp.read()

            # Aplicar transformer si es necesario
            ct, data = detect_segment_type(raw, url)
            if ct is None:
                raise ValueError("Respuesta HTML — segmento inválido")

            with open(cache_path, 'wb') as f:
                f.write(data)

            with state_lock:
                segment_cache[url] = cache_path
                segment_downloading.pop(url, None)
            ev.set()
            print(f"    💾 Seg {idx+1}/{total} ({len(data):,} bytes)")

        except Exception as e:
            with state_lock:
                segment_downloading.pop(url, None)
            ev.set()
            print(f"    ⚠️  Seg {idx+1} error: {type(e).__name__}: {e}")

    sem = threading.Semaphore(3)

    def with_sem(url, idx):
        with sem:
            download_one(url, idx)

    threads = [threading.Thread(target=with_sem, args=(u, i), daemon=True)
               for i, u in enumerate(segment_urls)]
    for t in threads:
        t.start()

    def wait_all():
        for t in threads:
            t.join()
        print(f"✅ Pre-descarga completa: {total} segmentos")

    threading.Thread(target=wait_all, daemon=True).start()

# ─── Servidor threading ───────────────────────────────────────────────────────
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# ─── Proxy Local ──────────────────────────────────────────────────────────────
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
            with state_lock:
                body = manifest_rewritten
                murl = manifest_url
            if not murl or body is None:
                self.send_error(503, "Sin stream")
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

        frag = re.search(r'[Ff]rag-(\d+)|seg-(\d+)|chunk-(\d+)', target)
        label = f"Frag-{(frag.group(1) or frag.group(2) or frag.group(3))}" if frag else target[-30:]

        # Servir desde cache si está disponible
        with state_lock:
            cached = segment_cache.get(target)
            dl_evt = segment_downloading.get(target)

        if cached and os.path.exists(cached):
            print(f"💾 {label}")
            self._serve_cached(cached, method)
            return

        if dl_evt:
            print(f"⏳ {label} esperando...")
            dl_evt.wait(timeout=60)
            with state_lock:
                cached = segment_cache.get(target)
            if cached and os.path.exists(cached):
                self._serve_cached(cached, method)
                return

        # On-demand
        print(f"🔗 {label} on-demand")
        with state_lock:
            hdrs = dict(captured_headers)

        try:
            skip = {'host', 'content-length', 'connection',
                    'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in hdrs.items() if k.lower() not in skip}
            req    = urllib.request.Request(target, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            raw  = resp.read()

            ct, data = detect_segment_type(raw, target)
            if ct is None:
                self.send_error(502, "Segmento invalido (HTML)")
                return

            print(f"    ✅ {ct} | {len(data):,} bytes")

            # Cachear para futuras pausas
            cpath = os.path.join(CACHE_DIR, f"seg_od_{abs(hash(target)) % 99999:05d}")
            with open(cpath, 'wb') as f:
                f.write(data)
            with state_lock:
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
            print(f"    ❌ HTTP {e.code}")
            try:
                self.send_error(e.code, e.reason)
            except Exception:
                pass
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"    ⚠️  {type(e).__name__}: {e}")

    def _serve_cached(self, path, method):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            # Re-detectar tipo por si acaso
            ct, data = detect_segment_type(data, path)
            ct = ct or 'video/mp2t'
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(data)
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"    ⚠️  serve_cached: {e}")

    def _resolve(self, path):
        if path.startswith('/https://'):
            return path[1:]
        if path.startswith('/http://'):
            return path[1:]
        if path.startswith('/'):
            with state_lock:
                base = cdn_token_base or manifest_url
            if base:
                base_dir = base if base.endswith('/') else base.rsplit('/', 1)[0] + '/'
                return urljoin(base_dir, path.lstrip('/'))
        return None


def start_local_proxy():
    server = ThreadingHTTPServer(('0.0.0.0', LOCAL_PROXY_PORT), ProxyHandler)
    print(f"🎬 Proxy local (threading) en puerto {LOCAL_PROXY_PORT}")
    server.serve_forever()

# ─── Enviar a Kodi ────────────────────────────────────────────────────────────
def send_to_kodi(url):
    opener  = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "Player.Open",
        "params": {"item": {"file": url}}, "id": 1
    }).encode()
    req = urllib.request.Request(
        f"http://{KODI_IP}:{KODI_PORT}/jsonrpc", payload,
        {"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(req, timeout=5)
        data = json.loads(resp.read().decode())
        print(f"✅ KODI: {'OK' if 'result' in data else data}")
    except Exception as e:
        print(f"❌ Kodi: {e}")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ─── Addon mitmproxy ──────────────────────────────────────────────────────────
class UniversalInterceptor:

    def response(self, flow: http.HTTPFlow):
        global manifest_url, manifest_rewritten, cdn_token_base
        global captured_headers, local_proxy_ip, kodi_notified

        url  = flow.request.pretty_url
        code = flow.response.status_code

        if code != 200:
            return

        # Detectar manifiesto m3u8
        if not is_manifest_url(url):
            return

        content = flow.response.content
        if not content:
            return

        # Verificar que es realmente un m3u8
        try:
            text = content[:100].decode('utf-8', errors='ignore')
        except Exception:
            return
        if '#EXTM3U' not in text and '<MPD' not in text:
            return

        lip        = get_local_ip()
        rewritten  = rewrite_m3u8(content, url, lip, LOCAL_PROXY_PORT)
        token_base = extract_token_base(url)
        seg_urls   = extract_segment_urls(content, url)
        hdrs_copy  = dict(flow.request.headers)

        with state_lock:
            manifest_url       = url
            manifest_rewritten = rewritten
            cdn_token_base     = token_base
            captured_headers   = hdrs_copy
            local_proxy_ip     = lip
            already            = kodi_notified
            kodi_notified      = True

        # Detectar plataforma para el log
        platform = "Desconocida"
        for name, pattern in [
            ("Netu/cfglobalcdn", r"cfglobalcdn"),
            ("StreamWish", r"streamwish|wishonly|awish|dwish"),
            ("VidHide", r"vidhide"),
            ("FileMoon", r"filemoon"),
            ("VOE.sx", r"voe\.sx|launchrelaying|dieudurable"),
            ("Streamtape", r"streamtape"),
        ]:
            if re.search(pattern, url, re.IGNORECASE):
                platform = name
                break

        print(f"\n{'='*60}")
        print(f"🎯 STREAM DETECTADO [{platform}]")
        print(f"   Segmentos: {len(seg_urls)}")
        print(f"   URL: {url[:70]}...")
        print(f"{'='*60}")

        # Pre-descargar todos en background
        if seg_urls:
            threading.Thread(
                target=prefetch_segments,
                args=(seg_urls, hdrs_copy),
                daemon=True
            ).start()

        if not already:
            proxy_url = f"http://{lip}:{LOCAL_PROXY_PORT}/live"
            print(f"📡 Enviando a Kodi: {proxy_url}")
            threading.Thread(target=send_to_kodi, args=(proxy_url,), daemon=True).start()


addons = [UniversalInterceptor()]

threading.Thread(target=start_local_proxy, daemon=True).start()

print(f"{'='*60}")
print(f"🎬 Universal Stream Interceptor")
print(f"   mitmproxy:   puerto 8082")
print(f"   Proxy local: puerto {LOCAL_PROXY_PORT}")
print(f"   Kodi:        {KODI_IP}:{KODI_PORT}")
print(f"   Cache:       {CACHE_DIR}")
print(f"   Plataformas: Netu, StreamWish, VidHide, FileMoon, VOE.sx, Streamtape")
print(f"   Tips:")
print(f"     - Podés cerrar el browser una vez iniciado el stream")
print(f"     - Pausa y seek funcionan via cache local")
print(f"     - Para nueva pelicula: recargá la pagina en el browser")
print(f"{'='*60}")