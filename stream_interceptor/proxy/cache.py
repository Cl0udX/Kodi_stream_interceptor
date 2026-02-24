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


def prefetch_segments(urls: list, headers: dict, transform_fn=None, max_workers: int = 3):
    """
    Pre-descarga segmentos en paralelo.
    
    Args:
        urls: Lista de URLs de segmentos
        headers: Headers HTTP a usar
        transform_fn: Función opcional para transformar URLs
        max_workers: Número de descargas paralelas
    """
    if not urls:
        return
    
    print(f"⬇️  Pre-descargando {len(urls)} segmentos...")
    
    # Filtrar headers conflictivos
    req_headers = {k: v for k, v in headers.items() 
                  if k.lower() not in ['host', 'content-length', 'connection', 'accept-encoding']}
    
    def download_one(url: str) -> bool:
        try:
            target = transform_fn(url) if transform_fn else url
            
            # Crear evento para esta descarga
            ev = threading.Event()
            with _events_lock:
                _download_events[url] = ev
            
            req = urllib.request.Request(target, headers=req_headers)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=30)
            data = resp.read()
            
            # Guardar en cache
            cpath = os.path.join(CACHE_DIR, f"{abs(hash(url)) % 999999:06d}.ts")
            with open(cpath, 'wb') as f:
                f.write(data)
            segment_cache[url] = cpath
            
            # Señalizar que terminó
            ev.set()
            return True
        except Exception:
            return False
        finally:
            with _events_lock:
                _download_events.pop(url, None)
    
    downloaded = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_one, url): url for url in urls}
        for future in as_completed(futures):
            if future.result():
                downloaded += 1
    
    print(f"   ✅ {downloaded}/{len(urls)} segmentos pre-descargados")