import json
import urllib.request
from config import KODI_IP, KODI_PORT

def send_to_kodi(url: str):
    opener  = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method":  "Player.Open",
        "params":  {"item": {"file": url}},
        "id":      1
    }).encode()
    req = urllib.request.Request(
        f"http://{KODI_IP}:{KODI_PORT}/jsonrpc",
        payload,
        {"Content-Type": "application/json"}
    )
    try:
        resp = opener.open(req, timeout=5)
        data = json.loads(resp.read().decode())
        if "result" in data:
            print(f"✅ KODI: reproduccion iniciada")
        else:
            print(f"❌ KODI error: {data}")
    except Exception as e:
        print(f"❌ No se pudo conectar a Kodi ({KODI_IP}:{KODI_PORT}): {e}")