import re
from urllib.parse import urljoin

def rewrite_m3u8(content_bytes: bytes, base_url: str, proxy_ip: str, proxy_port: int) -> str:
    """
    Reescribe todas las URLs del m3u8 para que pasen por el proxy local.
    Convierte segmentos relativos en URLs absolutas apuntando al proxy.
    """
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
                    uri  = m.group(1)
                    full = uri if uri.startswith('http') else urljoin(base_dir, uri)
                    return f'URI="http://{proxy_ip}:{proxy_port}/{full}"'
                s = re.sub(r'URI="([^"]+)"', replace_uri, s)
            out.append(s)
            continue
        full = s if s.startswith('http') else urljoin(base_dir, s)
        out.append(f"http://{proxy_ip}:{proxy_port}/{full}")

    return '\n'.join(out)

def extract_segment_urls(content_bytes: bytes, base_url: str) -> list:
    """Devuelve lista de URLs absolutas de todos los segmentos del m3u8."""
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
