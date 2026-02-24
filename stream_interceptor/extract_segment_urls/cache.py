import os
import ssl
import threading
import tempfile
import urllib.request

from config import PREFETCH_CONCURRENCY

CACHE_DIR = tempfile.mkdtemp(prefix="stream_cache_")
ctx_no_verify = ssl._create_unverified_context()

# { url: cache_path }
segment_cache       = {}
# { url: threading.Event }
segment_downloading = {}
_lock = threading.Lock()

def get_cached(url: str):
    with _lock:
        return segment_cache.get(url)

def get_downloading_event(url: str):
    with _lock:
        return segment_downloading.get(url)

def prefetch_segments(segment_urls: list, headers: dict, transform_fn):
    """
    Descarga todos los segmentos en background.
    transform_fn(data, url) → (content_type, data_limpia)
    """
    total = len(segment_urls)
    print(f"⬇️  Pre-descargando {total} segmentos en background...")

    def download_one(url, idx):
        with _lock:
            if url in segment_cache:
                return
            if url in segment_downloading:
                return
            ev = threading.Event()
            segment_downloading[url] = ev

        cache_path = os.path.join(CACHE_DIR, f"seg_{idx:05d}")
        try:
            skip  = {'host', 'content-length', 'connection',
                     'accept-encoding', 'transfer-encoding'}
            clean = {k: v for k, v in headers.items() if k.lower() not in skip}
            req    = urllib.request.Request(url, headers=clean)
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ctx_no_verify)
            )
            resp = opener.open(req, timeout=60)
            raw  = resp.read()

            ct, data = transform_fn(raw, url)
            if ct is None:
                raise ValueError("Segmento inválido (HTML)")

            with open(cache_path, 'wb') as f:
                f.write(data)

            with _lock:
                segment_cache[url] = cache_path
                segment_downloading.pop(url, None)
            ev.set()
            print(f"    💾 Seg {idx+1}/{total} ({len(data):,} bytes)")

        except Exception as e:
            with _lock:
                segment_downloading.pop(url, None)
            ev.set()
            print(f"    ⚠️  Seg {idx+1} error: {e}")

    sem = threading.Semaphore(PREFETCH_CONCURRENCY)

    def with_sem(url, idx):
        with sem:
            download_one(url, idx)

    threads = [
        threading.Thread(target=with_sem, args=(u, i), daemon=True)
        for i, u in enumerate(segment_urls)
    ]
    for t in threads:
        t.start()

    def wait_all():
        for t in threads:
            t.join()
        print(f"✅ Pre-descarga completa: {total} segmentos")

    threading.Thread(target=wait_all, daemon=True).start()
