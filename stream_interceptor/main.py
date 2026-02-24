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
import sys
import select

from mitmproxy import http

from config import LOCAL_PROXY_PORT
from kodi import send_to_kodi
from platforms import PLATFORMS
from platforms.goodstream import GoodStreamPlatform
from proxy.rewriter import rewrite_m3u8, extract_segment_urls
from proxy.cache import prefetch_segments, CACHE_DIR
from segmentos.server import start as start_proxy, update_state

# ─── Estado global ────────────────────────────────────────────────────────────
_kodi_notified = False
_state_lock    = threading.Lock()

# Cache de sub-manifiestos para plataformas con master
_sub_manifests = {}  # url -> (rewritten, seg_urls, headers)
_master_info = None  # (master_url, master_rewritten, platform, headers)
_ready_to_send = threading.Event()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def wait_for_key():
    """Espera a que el usuario presione Enter para enviar a Kodi"""
    global _kodi_notified
    
    print(f"\n⏳ Esperando a que carguen todos los streams...")
    print(f"   Presiona ENTER cuando estés listo para enviar a Kodi")
    
    # Esperar input del usuario
    try:
        input()
    except:
        pass
    
    with _state_lock:
        if _kodi_notified:
            return
        _kodi_notified = True
    
    # Enviar a Kodi
    lip = get_local_ip()
    proxy_url = f"http://{lip}:{LOCAL_PROXY_PORT}/live"
    print(f"\n📡 Enviando a Kodi: {proxy_url}")
    threading.Thread(
        target=send_to_kodi,
        args=(proxy_url,),
        daemon=True
    ).start()

# ─── Addon mitmproxy ──────────────────────────────────────────────────────────
class UniversalInterceptor:

    def response(self, flow: http.HTTPFlow):
        global _kodi_notified, _master_info

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

        lip = get_local_ip()
        hdrs_copy = dict(flow.request.headers)

        # ── Detectar si es master.m3u8 ────────────────────────────────────────
        is_master = 'master.m3u8' in url or (
            '#EXT-X-STREAM-INF' in preview or
            b'#EXT-X-STREAM-INF' in content[:500]
        )

        if is_master:
            print(f"\n{'='*60}")
            print(f"📋 MASTER M3U8 DETECTADO [{platform.name}]")
            
            # Filtrar variantes de solo audio si la plataforma lo soporta
            if hasattr(platform, 'filter_master'):
                content = platform.filter_master(content)
                print(f"   🔧 Filtradas variantes de solo audio")
            
            # Reescribir el master para que todas las URLs pasen por el proxy
            rewritten = rewrite_m3u8(content, url, lip, LOCAL_PROXY_PORT)
            
            # Guardar el master
            _master_info = (url, rewritten, platform, hdrs_copy)
            
            # Contar variantes
            text = content.decode('utf-8', errors='ignore')
            variants = text.count('#EXT-X-STREAM-INF')
            print(f"   📊 {variants} variantes disponibles")
            print(f"   🔗 URLs reescritas para proxy local")
            
            # Actualizar estado del servidor proxy con el master
            update_state(
                manifest_url       = url,
                manifest_rewritten = rewritten,
                cdn_token_base     = platform.token_base(url),
                captured_headers   = hdrs_copy,
                platform           = platform,
                local_ip           = lip,
                proxy_port         = LOCAL_PROXY_PORT,
            )
            
            # Iniciar thread para esperar input del usuario
            with _state_lock:
                if not _kodi_notified:
                    threading.Thread(target=wait_for_key, daemon=True).start()
            
            print(f"{'='*60}")
            return

        # ── Manifiesto normal (lista de segmentos) ────────────────────────────
        rewritten  = rewrite_m3u8(content, url, lip, LOCAL_PROXY_PORT)
        token_base = platform.token_base(url)
        seg_urls   = extract_segment_urls(content, url)

        # Guardar sub-manifiesto en cache
        _sub_manifests[url] = (rewritten, seg_urls, hdrs_copy)

        update_state(
            manifest_url       = url,
            manifest_rewritten = rewritten,
            cdn_token_base     = token_base,
            captured_headers   = hdrs_copy,
            platform           = platform,
        )

        # Detectar si es video o audio por el tamaño de segmentos
        is_audio_only = 'index-a' in url and '-v' not in url
        stream_type = "🎧 AUDIO" if is_audio_only else "🎬 VIDEO"
        
        print(f"\n{'='*60}")
        print(f"🎯 SUB-MANIFIESTO [{platform.name}] {stream_type}")
        print(f"   Segmentos: {len(seg_urls)}")
        print(f"   URL: {url[:70]}...")
        print(f"{'='*60}")
        
        # Si no hay master (como Netu), iniciar espera de ENTER aquí
        with _state_lock:
            if not _kodi_notified and _master_info is None:
                threading.Thread(target=wait_for_key, daemon=True).start()

        # Pre-descargar en background
        MAX_PREFETCH = 50
        if seg_urls and len(seg_urls) <= MAX_PREFETCH:
            threading.Thread(
                target=prefetch_segments,
                args=(seg_urls, hdrs_copy, platform.transform_segment),
                daemon=True
            ).start()
        elif seg_urls:
            print(f"   ⚡ {len(seg_urls)} segmentos — pre-descargando primeros {MAX_PREFETCH}")
            threading.Thread(
                target=prefetch_segments,
                args=(seg_urls[:MAX_PREFETCH], hdrs_copy, platform.transform_segment),
                daemon=True
            ).start()


addons = [UniversalInterceptor()]

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
print(f"")
print(f"   ⚠️  IMPORTANTE:")
print(f"   - Espera a que carguen todos los streams")
print(f"   - Presiona ENTER para enviar a Kodi")
print(f"{'='*60}")