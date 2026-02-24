"""
main.py - Addon para mitmproxy

Uso:
    mitmdump -s ~/Documents/Kodi/stream_interceptor/main.py --listen-port 8082 --quiet

Agregar nuevas plataformas:
    1. Crear platforms/nombre.py heredando BasePlatform
    2. Importar y agregar a PLATFORMS en platforms/__init__.py
"""
import re
import socket
import threading

from mitmproxy import http

from config import LOCAL_PROXY_PORT
from kodi import send_to_kodi
from platforms import PLATFORMS
from proxy.rewriter import rewrite_m3u8, extract_segment_urls
from proxy.cache import prefetch_segments, CACHE_DIR
from segmentos.server import start as start_proxy, update_state

# ─── Estado global ────────────────────────────────────────────────────────────
_kodi_notified = False
_state_lock    = threading.Lock()

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
        global _kodi_notified

        url  = flow.request.pretty_url
        code = flow.response.status_code

        if code != 200:
            return

        # Buscar qué plataforma matchea esta URL
        platform = None
        for p in PLATFORMS:
            if p.is_manifest(url):
                platform = p
                break

        if platform is None:
            return

        content = flow.response.content
        if not content:
            return

        # Verificar que el contenido es realmente un manifiesto
        try:
            preview = content[:100].decode('utf-8', errors='ignore')
        except Exception:
            return

        if '#EXTM3U' not in preview and '<MPD' not in preview:
            return

        lip        = get_local_ip()
        rewritten  = rewrite_m3u8(content, url, lip, LOCAL_PROXY_PORT)
        token_base = platform.token_base(url)
        seg_urls   = extract_segment_urls(content, url)
        hdrs_copy  = dict(flow.request.headers)

        # Actualizar estado del servidor proxy
        update_state(
            manifest_url       = url,
            manifest_rewritten = rewritten,
            cdn_token_base     = token_base,
            captured_headers   = hdrs_copy,
            platform           = platform,
        )

        print(f"\n{'='*60}")
        print(f"🎯 STREAM DETECTADO [{platform.name}]")
        print(f"   Segmentos: {len(seg_urls)}")
        print(f"   URL: {url[:70]}...")
        print(f"   Cache: {CACHE_DIR}")
        print(f"{'='*60}")

        # Pre-descargar todos los segmentos en background
        if seg_urls:
            threading.Thread(
                target=prefetch_segments,
                args=(seg_urls, hdrs_copy, platform.transform_segment),
                daemon=True
            ).start()

        # Avisar a Kodi (solo la primera vez por stream)
        with _state_lock:
            already        = _kodi_notified
            _kodi_notified = True

        if not already:
            proxy_url = f"http://{lip}:{LOCAL_PROXY_PORT}/live"
            print(f"📡 Enviando a Kodi: {proxy_url}")
            threading.Thread(
                target=send_to_kodi,
                args=(proxy_url,),
                daemon=True
            ).start()


addons = [UniversalInterceptor()]

# Iniciar proxy local en background
threading.Thread(
    target=start_proxy,
    args=(LOCAL_PROXY_PORT,),
    daemon=True
).start()

print(f"{'='*60}")
print(f"🎬 Universal Stream Interceptor")
print(f"   mitmproxy:    puerto 8082")
print(f"   Proxy local:  puerto {LOCAL_PROXY_PORT}")
print(f"   Cache:        {CACHE_DIR}")
print(f"   Plataformas activas:")
for p in PLATFORMS:
    print(f"     ✅ {p.name}")
print(f"   Tips:")
print(f"     - Podés cerrar el browser una vez iniciado el stream")
print(f"     - Pausa y seek funcionan via cache local")
print(f"     - Para nueva pelicula recarga la pagina en el browser")
print(f"{'='*60}")