from platforms.base import BasePlatform
from platforms.netu import NetuPlatform
from platforms.goodstream import GoodStreamPlatform
# Agregar aquí a medida que se implementan:
# from platforms.streamwish import StreamWishPlatform
# from platforms.vidhide import VidHidePlatform
# from platforms.voesx import VoeSxPlatform

# Lista de plataformas activas — el interceptor las prueba en orden
PLATFORMS = [
    NetuPlatform(),
    GoodStreamPlatform(),
    # StreamWishPlatform(),
    # VidHidePlatform(),
    # VoeSxPlatform(),
]