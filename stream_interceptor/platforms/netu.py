import re
from platforms.base import BasePlatform

class NetuPlatform(BasePlatform):
    name = "Netu/cfglobalcdn"
    cdn_patterns = [
        r"cfglobalcdn\.com",
        r"cdnglobalcheck\.com",
    ]
    segment_patterns = [
        r"/Frag-\d+",
        r"/seg-\d+",
        r"\.ts($|\?)",
    ]

    def token_base(self, url: str) -> str:
        # URL: https://cdn/silverlight/secip/ID/ID/TOKEN/IP/TIMESTAMP/hls-vod-.../
        # Extraemos hasta el TIMESTAMP para poder reconstruir cualquier segmento
        match = re.search(
            r'(https?://[^/]+/(?:silverlight/)?secip/\d+/\d+/[^/]+/[^/]+/\d{9,11}/)',
            url
        )
        if match:
            return match.group(1)
        # Fallback: timestamp numérico genérico
        parts = url.split('/')
        for i, part in enumerate(parts):
            if re.match(r'^\d{9,11}$', part):
                return '/'.join(parts[:i+1]) + '/'
        return url.rsplit('/', 1)[0] + '/'

    def transform_segment(self, data: bytes, url: str):
        # Netu sirve los segmentos limpios, solo detectar tipo
        return self._detect_type(data)
