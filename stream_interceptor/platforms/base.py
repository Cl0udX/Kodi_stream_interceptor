import re

class BasePlatform:
    """
    Clase base para cada plataforma.
    Cada plataforma define:
      - name: nombre para logs
      - cdn_patterns: lista de regex que matchean las URLs del CDN
      - segment_patterns: regex que identifican segmentos (no manifiestos)
      - token_base(url): extrae la base con token para resolver relativos
      - transform_segment(data, url): transforma los bytes del segmento si hace falta
    """
    name = "Base"
    cdn_patterns      = []
    segment_patterns  = [
        r"/Frag-\d+", r"/seg-\d+", r"/chunk-\d+",
        r"\.ts($|\?)", r"\.m4s($|\?)",
    ]

    def matches_cdn(self, url: str) -> bool:
        return any(re.search(p, url) for p in self.cdn_patterns)

    def is_segment(self, url: str) -> bool:
        return any(re.search(p, url) for p in self.segment_patterns)

    def is_manifest(self, url: str) -> bool:
        if not self.matches_cdn(url):
            return False
        if self.is_segment(url):
            return False
        return '.m3u8' in url or not re.search(r'\.(ts|mp4|m4s|png|jpg)($|\?)', url)

    def token_base(self, url: str) -> str:
        """Extrae la base de la URL con token para reconstruir segmentos relativos."""
        # Fallback genérico: directorio padre
        return url.rsplit('/', 1)[0] + '/'

    def transform_segment(self, data: bytes, url: str):
        """
        Transforma los bytes del segmento si la plataforma los ofusca.
        Devuelve (content_type, data_limpia).
        None como content_type indica error real.
        """
        return self._detect_type(data)

    def _detect_type(self, data: bytes):
        if not data:
            return 'video/mp2t', data
        if data[0] == 0x47:
            return 'video/mp2t', data
        if len(data) > 8 and data[4:8] in (b'ftyp', b'moof', b'mdat', b'moov'):
            return 'video/mp4', data
        if data[:9].lower().startswith(b'<!doctype') or data[:6].lower() == b'<html>':
            return None, data
        return 'video/mp2t', data
