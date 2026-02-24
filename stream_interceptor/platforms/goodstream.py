"""
GoodStream (goodstream.one / enc*.goodstream.one)

Estructura:
  master.m3u8  → lista de calidades (360p/480p/720p/1080p)
    └── index-v1-a1.m3u8  → lista de segmentos .ts
          └── seg-N-v1-a1.ts?t=TOKEN&s=...&e=43200

Características:
  - Token en query string (?t=...&s=...&e=43200)
  - Sin ofuscación, segmentos .ts directos
  - e=43200 → expira en 12 horas (muy generoso)
  - Múltiples calidades → interceptamos el master y dejamos que Kodi elija
"""
import re
from platforms.base import BasePlatform

# Calidad preferida por defecto si no hay selección manual
# Opciones: "360p", "480p", "720p", "1080p", "best", "worst"
DEFAULT_QUALITY = "1080p"

QUALITY_MAP = {
    "360p":  640,
    "480p":  852,
    "720p":  1280,
    "1080p": 1920,
}

class GoodStreamPlatform(BasePlatform):
    name = "GoodStream"
    cdn_patterns = [
        r"goodstream\.one",
        r"enc\d+\.goodstream\.one",
    ]
    segment_patterns = [
        r"/seg-\d+-v\d+-a\d+\.ts",
        r"/iframes-v\d+-a\d+\.m3u8",
    ]

    def is_manifest(self, url: str) -> bool:
        if not self.matches_cdn(url):
            return False
        if self.is_segment(url):
            return False
        # Capturar tanto master.m3u8 como index-v1-a1.m3u8
        return 'master.m3u8' in url or 'index-' in url

    def token_base(self, url: str) -> str:
        # El token está en query string, el path base es el directorio
        # https://enc10.goodstream.one/hls2/06/00075/l7znl4kmd08w_x/
        return url.rsplit('/', 1)[0] + '/'

    def select_quality(self, master_content: bytes, preferred: str = DEFAULT_QUALITY) -> str:
        """
        Dado el contenido del master.m3u8, devuelve la URL de la calidad preferida.
        Si no existe la calidad exacta, devuelve la más cercana.
        """
        text   = master_content.decode('utf-8', errors='ignore')
        streams = []

        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('#EXT-X-STREAM-INF'):
                # Extraer resolución
                res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                if res_match and i + 1 < len(lines):
                    width  = int(res_match.group(1))
                    height = int(res_match.group(2))
                    url    = lines[i + 1].strip()
                    if url and not url.startswith('#'):
                        streams.append((width, height, url))

        if not streams:
            return None

        # Ordenar por ancho
        streams.sort(key=lambda x: x[0])

        if preferred == "best":
            return streams[-1][2]
        if preferred == "worst":
            return streams[0][2]

        target_width = QUALITY_MAP.get(preferred, 1920)
        # Buscar calidad exacta o la más cercana por encima
        for w, h, url in streams:
            if w >= target_width:
                return url
        # Si no hay ninguna por encima, devolver la más alta disponible
        return streams[-1][2]

    def transform_segment(self, data: bytes, url: str):
        # GoodStream sirve .ts limpios, sin ofuscación
        return self._detect_type(data)

    def filter_master(self, content: bytes) -> bytes:
        """
        Filtra el master.m3u8 para eliminar variantes de solo audio.
        Kodi a veces elige la variante de audio si está disponible.
        Solo mantiene las variantes con video (index-v*-a*.m3u8).
        """
        text = content.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        filtered = []
        i = 0
        removed = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Si es un tag de stream-info, verificar si la URL es de solo audio
            if line.startswith('#EXT-X-STREAM-INF'):
                # Verificar la siguiente línea (URL del stream)
                if i + 1 < len(lines):
                    next_url = lines[i + 1].strip()
                    # Solo audio: index-a1.m3u8 o index-a2.m3u8 (sin -v)
                    # Video+audio: index-v1-a1.m3u8
                    is_audio_only = 'index-a' in next_url and '-v' not in next_url
                    
                    if is_audio_only:
                        # Saltar esta línea y la siguiente (URL de solo audio)
                        print(f"      🗑️  Eliminando: {next_url[-50:]}")
                        removed += 1
                        i += 2
                        continue
                
                # Si no es solo audio, agregar el tag y la URL
                filtered.append(line)
                i += 1
            else:
                # Agregar cualquier otra línea
                filtered.append(line)
                i += 1
        
        if removed > 0:
            print(f"      ✂️  {removed} variantes de audio eliminadas")
        
        return '\n'.join(filtered).encode('utf-8')
