#!/usr/bin/env python3
"""
KodiPlay Android - GUI Web para Android/Termux

Uso:
    python kodi_android.py
    
Luego abre en tu navegador: http://localhost:8080
"""

import json
import os
import socket
import subprocess
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

# ─── Configuración ────────────────────────────────────────────────────────────
KODI_PORT = 8080
WEB_PORT = 5000
PROXY_PORT = 8888
MITM_PORT = 8082

# ─── Estado Global ────────────────────────────────────────────────────────────
state = {
    "kodi_ip": None,
    "kodi_port": KODI_PORT,
    "interceptor_running": False,
    "stream_ready": False,
    "last_url": None,
    "log": [],
}

# ─── Utilidades ───────────────────────────────────────────────────────────────
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def kodi_request(method, params=None):
    if not state["kodi_ip"]:
        return {"error": "No Kodi configurado"}
    
    payload = json.dumps({
        "jsonrpc": "2.0", "method": method,
        "params": params or {}, "id": 1
    }).encode()
    
    try:
        req = urllib.request.Request(
            f"http://{state['kodi_ip']}:{state['kodi_port']}/jsonrpc",
            payload, {"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=3)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def log(msg):
    state["log"].append(msg)
    if len(state["log"]) > 100:
        state["log"] = state["log"][-100:]
    print(msg)

# ─── Notificaciones Android (Termux) ──────────────────────────────────────────
def notify(title, text):
    """Envía notificación en Android via Termux"""
    try:
        subprocess.run([
            "termux-notification",
            "--title", title,
            "--content", text,
            "--priority", "high"
        ], check=False)
    except:
        pass  # No es Termux

def toast(text):
    """Muestra toast en Android"""
    try:
        subprocess.run(["termux-toast", text], check=False)
    except:
        pass

# ─── Interceptor ──────────────────────────────────────────────────────────────
interceptor_proc = None

def start_interceptor():
    global interceptor_proc
    
    if state["interceptor_running"]:
        return {"error": "Ya está corriendo"}
    
    # Actualizar config
    config_path = os.path.join(os.path.dirname(__file__), "..", "stream_interceptor", "config.py")
    config_content = f'''KODI_IP = "{state['kodi_ip']}"
KODI_PORT = {state['kodi_port']}
LOCAL_PROXY_PORT = {PROXY_PORT}
MITMPROXY_PORT = {MITM_PORT}
PREFETCH_CONCURRENCY = 10
'''
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    # Limpiar puertos
    subprocess.run(["pkill", "-f", "mitmdump"], check=False)
    
    # Iniciar mitmdump
    main_path = os.path.join(os.path.dirname(__file__), "..", "stream_interceptor", "main.py")
    interceptor_proc = subprocess.Popen(
        ["mitmdump", "-s", main_path, "--listen-port", str(MITM_PORT), "--quiet"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    
    state["interceptor_running"] = True
    state["stream_ready"] = True
    
    notify("Interceptor", "Iniciado - Abre tu navegador")
    log("✅ Interceptor iniciado")
    
    return {"status": "ok"}

def stop_interceptor():
    global interceptor_proc
    
    subprocess.run(["pkill", "-f", "mitmdump"], check=False)
    interceptor_proc = None
    state["interceptor_running"] = False
    state["stream_ready"] = False
    
    log("⏹ Interceptor detenido")
    return {"status": "ok"}

def send_to_kodi():
    if not state["kodi_ip"]:
        return {"error": "Configura Kodi primero"}
    
    local_ip = get_local_ip()
    proxy_url = f"http://{local_ip}:{PROXY_PORT}/live"
    
    # Detener reproducción anterior
    kodi_request("Player.Stop", {"playerid": 1})
    
    # Enviar nuevo stream
    result = kodi_request("Player.Open", {"item": {"file": proxy_url}})
    
    if "result" in result:
        notify("Kodi", "Reproduciendo stream")
        log("✅ Enviado a Kodi")
        return {"status": "ok"}
    else:
        log(f"❌ Error: {result}")
        return {"error": str(result)}

# ─── GUI Web ──────────────────────────────────────────────────────────────────
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KodiPlay Android</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0e0e16;
            color: #e8e8f0;
            min-height: 100vh;
            padding: 16px;
        }
        .container { max-width: 500px; margin: 0 auto; }
        h1 { font-size: 24px; margin-bottom: 8px; color: #bc7d00; }
        .subtitle { color: #55556a; margin-bottom: 24px; font-size: 12px; }
        
        .card {
            background: #16161f;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .card-title { font-size: 11px; color: #55556a; margin-bottom: 8px; text-transform: uppercase; }
        
        input, select {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: #1e1e2e;
            color: #e8e8f0;
            font-size: 14px;
            margin-bottom: 8px;
        }
        input:focus { outline: 2px solid #bc7d00; }
        
        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            margin-bottom: 8px;
        }
        .btn-primary { background: #bc7d00; color: #000; }
        .btn-success { background: #4eff91; color: #000; }
        .btn-danger { background: #ff4757; color: #fff; }
        .btn-secondary { background: #1e1e2e; color: #e8e8f0; }
        
        .status {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px;
            background: #1e1e2e;
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #55556a;
        }
        .status-dot.active { background: #4eff91; }
        .status-dot.error { background: #ff4757; }
        
        .log {
            background: #16161f;
            border-radius: 8px;
            padding: 12px;
            font-family: monospace;
            font-size: 11px;
            max-height: 200px;
            overflow-y: auto;
        }
        .log-entry { margin-bottom: 4px; }
        .log-ok { color: #4eff91; }
        .log-err { color: #ff4757; }
        .log-info { color: #e8e8f0; }
        
        .controls {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }
        .controls button { padding: 16px 8px; font-size: 20px; }
        
        .instructions {
            font-size: 12px;
            color: #55556a;
            line-height: 1.6;
        }
        .instructions ol { padding-left: 16px; }
        .instructions li { margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 KodiPlay</h1>
        <p class="subtitle">Android Edition</p>
        
        <div class="card">
            <div class="card-title">Kodi</div>
            <input type="text" id="kodi-ip" placeholder="IP de Kodi (ej: 192.168.1.100)">
            <button class="btn-secondary" onclick="connectKodi()">Conectar</button>
            <div class="status" id="kodi-status">
                <div class="status-dot" id="kodi-dot"></div>
                <span id="kodi-text">No conectado</span>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">Interceptor</div>
            <button class="btn-success" id="btn-start" onclick="startInterceptor()">▶ INICIAR</button>
            <button class="btn-danger" id="btn-stop" onclick="stopInterceptor()" style="display:none;">⏹ DETENER</button>
            <button class="btn-primary" id="btn-send" onclick="sendToKodi()" disabled>📤 ENVIAR A KODI</button>
            <div class="status">
                <div class="status-dot" id="interceptor-dot"></div>
                <span id="interceptor-text">Detenido</span>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">Controles</div>
            <div class="controls">
                <button class="btn-secondary" onclick="control('prev')">⏮</button>
                <button class="btn-secondary" onclick="control('seekback')">⏪</button>
                <button class="btn-secondary" onclick="control('pause')">⏸</button>
                <button class="btn-secondary" onclick="control('seekfwd')">⏩</button>
                <button class="btn-secondary" onclick="control('next')">⏭</button>
                <button class="btn-secondary" onclick="control('stop')">⏹</button>
                <button class="btn-secondary" onclick="control('voldown')">🔉</button>
                <button class="btn-secondary" onclick="control('volup')">🔊</button>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">Instrucciones</div>
            <div class="instructions">
                <ol>
                    <li>Conecta tu Kodi (IP:puerto)</li>
                    <li>Presiona INICIAR</li>
                    <li>Abre tu navegador y carga la película</li>
                    <li>Presiona ENVIAR A KODI</li>
                </ol>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">Log</div>
            <div class="log" id="log"></div>
        </div>
    </div>
    
    <script>
        function api(action, data = {}) {
            return fetch('/api/' + action, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(r => r.json());
        }
        
        function connectKodi() {
            const ip = document.getElementById('kodi-ip').value;
            api('connect', {ip}).then(r => {
                updateStatus('kodi', r.status === 'ok');
                if (r.status === 'ok') {
                    document.getElementById('kodi-text').textContent = 'Conectado: ' + ip;
                }
            });
        }
        
        function startInterceptor() {
            api('interceptor/start').then(r => {
                if (r.status === 'ok') {
                    document.getElementById('btn-start').style.display = 'none';
                    document.getElementById('btn-stop').style.display = 'block';
                    document.getElementById('btn-send').disabled = false;
                    updateStatus('interceptor', true);
                    document.getElementById('interceptor-text').textContent = 'Activo';
                }
            });
        }
        
        function stopInterceptor() {
            api('interceptor/stop').then(r => {
                document.getElementById('btn-start').style.display = 'block';
                document.getElementById('btn-stop').style.display = 'none';
                document.getElementById('btn-send').disabled = true;
                updateStatus('interceptor', false);
                document.getElementById('interceptor-text').textContent = 'Detenido';
            });
        }
        
        function sendToKodi() {
            api('send').then(r => {
                if (r.status === 'ok') {
                    document.getElementById('interceptor-text').textContent = 'Reproduciendo';
                }
            });
        }
        
        function control(action) {
            api('control/' + action);
        }
        
        function updateStatus(type, active) {
            const dot = document.getElementById(type + '-dot');
            dot.className = 'status-dot' + (active ? ' active' : '');
        }
        
        function refreshLog() {
            fetch('/api/log').then(r => r.json()).then(data => {
                const log = document.getElementById('log');
                log.innerHTML = data.log.map(l => 
                    '<div class="log-entry">' + l + '</div>'
                ).join('');
                log.scrollTop = log.scrollHeight;
            });
        }
        
        setInterval(refreshLog, 2000);
        refreshLog();
    </script>
</body>
</html>
'''

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif self.path == '/api/log':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"log": state["log"]}).encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
        data = json.loads(body) if body else {}
        
        path = self.path.replace('/api/', '')
        result = self.handle_api(path, data)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    
    def handle_api(self, action, data):
        if action == 'connect':
            ip = data.get('ip', '')
            if ':' in ip:
                parts = ip.split(':')
                state['kodi_ip'] = parts[0]
                state['kodi_port'] = int(parts[1])
            else:
                state['kodi_ip'] = ip
            
            # Verificar conexión
            r = kodi_request("JSONRPC.Ping")
            if "result" in r and r["result"] == "pong":
                log(f"✅ Conectado a Kodi: {state['kodi_ip']}")
                return {"status": "ok"}
            else:
                log(f"❌ No se pudo conectar a {state['kodi_ip']}")
                return {"status": "error", "error": "No conectado"}
        
        elif action == 'interceptor/start':
            return start_interceptor()
        
        elif action == 'interceptor/stop':
            return stop_interceptor()
        
        elif action == 'send':
            return send_to_kodi()
        
        elif action == 'control/prev':
            kodi_request("Player.GoTo", {"playerid": 1, "to": "previous"})
            return {"status": "ok"}
        
        elif action == 'control/next':
            kodi_request("Player.GoTo", {"playerid": 1, "to": "next"})
            return {"status": "ok"}
        
        elif action == 'control/pause':
            kodi_request("Player.PlayPause", {"playerid": 1})
            return {"status": "ok"}
        
        elif action == 'control/stop':
            kodi_request("Player.Stop", {"playerid": 1})
            return {"status": "ok"}
        
        elif action == 'control/seekfwd':
            kodi_request("Player.Seek", {"playerid": 1, "value": {"seconds": 30}})
            return {"status": "ok"}
        
        elif action == 'control/seekback':
            kodi_request("Player.Seek", {"playerid": 1, "value": {"seconds": -30}})
            return {"status": "ok"}
        
        elif action == 'control/volup':
            kodi_request("Application.SetVolume", {"volume": "increment"})
            return {"status": "ok"}
        
        elif action == 'control/voldown':
            kodi_request("Application.SetVolume", {"volume": "decrement"})
            return {"status": "ok"}
        
        return {"error": "Unknown action"}

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def main():
    local_ip = get_local_ip()
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           🎬 KodiPlay Android                            ║
╠══════════════════════════════════════════════════════════╣
║  GUI Web:     http://{local_ip}:{WEB_PORT}                 ║
║  Proxy:       {local_ip}:{PROXY_PORT}                       ║
║  MITM:        puerto {MITM_PORT}                           ║
╠══════════════════════════════════════════════════════════╣
║  Abre el link en tu navegador para controlar Kodi        ║
╚══════════════════════════════════════════════════════════╝
""")
    
    notify("KodiPlay", f"Abre http://{local_ip}:{WEB_PORT} en tu navegador")
    
    server = ThreadedHTTPServer(('0.0.0.0', WEB_PORT), APIHandler)
    server.serve_forever()

if __name__ == "__main__":
    main()