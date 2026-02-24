"""
VidHide — EN CONSTRUCCIÓN
Completar después de analizar el tráfico con mitmproxy.
"""
from platforms.base import BasePlatform

class VidHidePlatform(BasePlatform):
    name = "VidHide"
    cdn_patterns = [
        # TODO: agregar dominios CDN reales después del análisis
        r"vidhide\.com",
        r"vidhidepro\.com",
    ]
