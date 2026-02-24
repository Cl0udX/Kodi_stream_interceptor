"""
VOE.sx — EN CONSTRUCCIÓN
Completar después de analizar el tráfico con mitmproxy.
"""
from platforms.base import BasePlatform

class VoeSxPlatform(BasePlatform):
    name = "VOE.sx"
    cdn_patterns = [
        # TODO: agregar dominios CDN reales después del análisis
        r"voe\.sx",
        r"launchrelaying\.com",
        r"dieudurable\.com",
    ]
