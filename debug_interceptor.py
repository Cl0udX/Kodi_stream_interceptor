"""
debug_interceptor.py - Ver TODOS los requests que pasan por mitmproxy
Uso:
    mitmdump -s ~/Documents/Kodi/debug_interceptor.py --listen-port 8082
"""
from mitmproxy import http

class DebugAll:
    def request(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url
        method = flow.request.method
        
        # Mostrar TODOS los requests (filtramos assets irrelevantes)
        skip = ['.png', '.jpg', '.gif', '.ico', '.css', '.woff', 
                'google-analytics', 'doubleclick', 'facebook']
        
        if any(s in url for s in skip):
            return
        
        print(f"→ {method} {url}")

    def response(self, flow: http.HTTPFlow):
        url  = flow.request.pretty_url
        code = flow.response.status_code
        ct   = flow.response.headers.get('content-type', '')
        
        skip = ['.png', '.jpg', '.gif', '.ico', '.css', '.woff',
                'google-analytics', 'doubleclick', 'facebook']
        
        if any(s in url for s in skip):
            return
        
        # Resaltar m3u8 y video
        if any(x in url for x in ['.m3u8', '.ts', 'get_md5', 'silverlight', 
                                    'stream', 'hls', 'video', 'media']):
            print(f"  ★ {code} [{ct}] {url}")
        else:
            print(f"  ← {code} {url[:100]}")

addons = [DebugAll()]
print("🔍 Debug interceptor listo — mostrando todos los requests")
print("   Reproducí el video en el browser ahora...")