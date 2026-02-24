"""
cache.py - Cache y pre-descarga de segmentos
"""
import os
import ssl
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# Directorio de cache
CACHE_DIR = os.path.expanduser("~/Documents/Kodi/stream_interceptor/cache")

# SSL context sin verificación
ctx_no_verify = ssl._create_unverified_context()

# Cache en memoria: URL -> path del archivo
segment_cache = {}

# Eventos de descarga en curso: URL -> Event
_download_events = {}
_events_lock = threading.Lock()

# Asegurar que el directorio existe
os.makedirs(CACHE_DIR, exist_ok=True)


def get_cached(url: str) -> str:
    """Devuelve el path del cache si existe, None si no."""
    return segment_cache.get(url)


def get_downloading_event(url: str) -> threading.Event:
    """Devuelve el evento de descarga si hay una en curso, None si no."""
    with _events_lock:
        return _download_events.get(url)


def prefetch_segments(urls: list, headers: dict, transform_fn=None, max_workers: int = 10):
    """
    Pre-descarga segmentos en paralelo de forma agresiva.
    
    Args:
        urls: Lista de URLs de segmentos
        headers: Headers HTTP a usar
        transform_fn: Función opcional para transformar segmentos (data, url) -> (ct, data)
        max_workers: Número de descargas paralelas (default: 10)
    """
    if not urls:
        return
    
    print(f"⬇️  Pre-descargando {len(urls)} segmentos con {max_workers} conexiones paralelas...")
    
    # Filtrar headers conflictivos
    req_headers = {k: v for k, v in headers.items() 
                  if k.lower() not in ['host', 'content-length', 'connection', 'accept-encoding']}
    
    downloaded = 0
    failed = 0
    
    def download_one(url: str) -> bool:
        nonlocal downloaded, failed
        try:
            # Debug: mostrar primera URL
            if downloaded == 0 and failed == 0:
                print(f"   🔍 Primera URL: {url[:80]}...")
            
            # Crear evento para esta descarga
            ev = threading.Event()
            with _events_lock:
                _download_events[url] = ev
            
            req = urllib.request.Request(url, headers=req_headers)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            data = resp.read()
            
            # Transformar si es necesario (algunas plataformas ofuscan)
            if transform_fn:
                ct, data = transform_fn(data, url)
                if ct is None:
                    failed += 1
                    return False
            
            # Guardar en cache
            cpath = os.path.join(CACHE_DIR, f"{abs(hash(url)) % 999999:06d}.ts")
            with open(cpath, 'wb') as f:
                f.write(data)
            segment_cache[url] = cpath
            
            # Señalizar que terminó
            ev.set()
            downloaded += 1
            
            # Mostrar progreso cada 10 segmentos
            if downloaded % 10 == 0:
                print(f"   📥 {downloaded}/{len(urls)} segmentos...")
            
            return True
        except Exception as e:
            failed += 1
            # Mostrar primer error para debug
            if failed == 1:
                print(f"   ❌ Error en primer segmento: {e}")
                print(f"      URL: {url[:80]}...")
            return False
        finally:
            with _events_lock:
                _download_events.pop(url, None)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_one, url): url for url in urls}
        for future in as_completed(futures):
            pass  # El contador se actualiza en download_one
    
    print(f"   ✅ Pre-descarga completada: {downloaded}/{len(urls)} segmentos ({failed} fallos)")
