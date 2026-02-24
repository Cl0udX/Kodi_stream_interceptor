#!/usr/bin/env python3
"""
Widget Flotante para Android - KodiPlay

Este módulo crea un botón flotante sobre otras aplicaciones
usando Termux:API y notificaciones interactivas.

Requiere:
    pkg install termux-api
    pip install flask
    
Uso:
    from float_widget import FloatWidget
    widget = FloatWidget(on_send, on_stop)
    widget.show()
"""

import json
import subprocess
import threading
import time
import urllib.request

class FloatWidget:
    """
    Widget flotante para Android usando notificaciones persistentes
    y diálogos de Termux.
    """
    
    def __init__(self, on_send=None, on_stop=None, on_pause=None, kodi_ip=None, kodi_port=8080):
        self.on_send = on_send
        self.on_stop = on_stop
        self.on_pause = on_pause
        self.kodi_ip = kodi_ip
        self.kodi_port = kodi_port
        self.running = False
        self.interceptor_active = False
        
    def kodi_request(self, method, params=None):
        """Envía petición a Kodi"""
        if not self.kodi_ip:
            return {"error": "No Kodi configurado"}
        
        payload = json.dumps({
            "jsonrpc": "2.0", "method": method,
            "params": params or {}, "id": 1
        }).encode()
        
        try:
            req = urllib.request.Request(
                f"http://{self.kodi_ip}:{self.kodi_port}/jsonrpc",
                payload, {"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=3)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}
    
    def notify(self, title, text, actions=None):
        """Envía notificación con botones opcionales"""
        cmd = [
            "termux-notification",
            "--title", title,
            "--content", text,
            "--priority", "high",
            "--ongoing",  # Persistente
            "--id", "kodiplay-widget"
        ]
        
        if actions:
            for action in actions:
                cmd.extend(["--button1", action[0], "--button1-action", action[1]])
        
        try:
            subprocess.run(cmd, check=False)
        except:
            pass
    
    def toast(self, text):
        """Muestra toast"""
        try:
            subprocess.run(["termux-toast", text], check=False)
        except:
            pass
    
    def dialog(self, title, text):
        """Muestra diálogo con botones"""
        try:
            result = subprocess.run([
                "termux-dialog",
                "--title", title,
                "--text", text,
                "--button1", "Enviar",
                "--button2", "Detener",
                "--button3", "Cerrar"
            ], capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return ""
    
    def show_interceptor_active(self):
        """Muestra widget con interceptor activo"""
        self.notify(
            "🎬 KodiPlay",
            "Interceptor activo - Toca para enviar a Kodi",
            actions=[
                ("📤 Enviar", "termux-notification --title 'Kodi' --content 'Enviando...'"),
                ("⏹ Detener", "pkill -f mitmdump")
            ]
        )
    
    def show_interceptor_inactive(self):
        """Muestra widget con interceptor inactivo"""
        self.notify(
            "🎬 KodiPlay",
            "Toca para iniciar interceptor",
            actions=[
                ("▶ Iniciar", "echo 'start'"),
                ("⚙ Config", "termux-dialog --title 'Kodi IP' --input")
            ]
        )
    
    def show_floating_button(self):
        """
        Simula botón flotante usando notificación persistente.
        En Android real se necesitaría una app nativa con permiso SYSTEM_ALERT_WINDOW.
        """
        self.notify(
            "🎬 KodiPlay",
            f"Kodi: {self.kodi_ip or 'No configurado'} | Interceptor: {'Activo' if self.interceptor_active else 'Inactivo'}",
            actions=[
                ("📤", "curl -s http://localhost:5000/api/send"),
                ("⏹", "curl -s http://localhost:5000/api/interceptor/stop"),
                ("▶", "curl -s http://localhost:5000/api/interceptor/start")
            ]
        )
    
    def run_interactive(self):
        """
        Modo interactivo - muestra menú y espera acciones
        """
        self.running = True
        
        while self.running:
            # Mostrar menú
            result = self.dialog(
                "🎬 KodiPlay",
                f"Kodi: {self.kodi_ip or 'No configurado'}\nInterceptor: {'Activo' if self.interceptor_active else 'Inactivo'}"
            )
            
            if "Enviar" in result or "button1" in result:
                if self.on_send:
                    self.on_send()
                else:
                    self.kodi_request("Player.Open", {"item": {"file": f"http://localhost:8888/live"}})
                self.toast("Enviando a Kodi...")
                
            elif "Detener" in result or "button2" in result:
                if self.on_stop:
                    self.on_stop()
                self.interceptor_active = False
                self.toast("Interceptor detenido")
                
            elif "Cerrar" in result or "button3" in result:
                self.running = False
            
            time.sleep(0.5)
    
    def start_background(self):
        """Inicia el widget en background"""
        self.show_floating_button()
        
        def monitor():
            while self.running:
                time.sleep(5)
                self.show_floating_button()
        
        threading.Thread(target=monitor, daemon=True).start()


class QuickSettingsTile:
    """
    Simula un Quick Settings Tile para Android.
    Requiere Termux:API y configuración adicional.
    """
    
    def __init__(self, kodi_ip, kodi_port=8080):
        self.kodi_ip = kodi_ip
        self.kodi_port = kodi_port
    
    def send_to_kodi(self):
        """Envía stream a Kodi"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"
        
        proxy_url = f"http://{local_ip}:8888/live"
        
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "Player.Open",
            "params": {"item": {"file": proxy_url}},
            "id": 1
        }).encode()
        
        try:
            req = urllib.request.Request(
                f"http://{self.kodi_ip}:{self.kodi_port}/jsonrpc",
                payload, {"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=3)
            return True
        except:
            return False


# ─── CLI para pruebas ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    print("""
╔══════════════════════════════════════════════════════════╗
║         🎬 KodiPlay Widget Flotante                      ║
╠══════════════════════════════════════════════════════════╣
║  Este módulo proporciona un widget flotante para         ║
║  controlar Kodi desde cualquier pantalla de Android.     ║
║                                                          ║
║  Requiere:                                               ║
║    - Termux (com.termux)                                 ║
║    - Termux:API (com.termux.api)                         ║
║                                                          ║
║  Uso:                                                    ║
║    from float_widget import FloatWidget                  ║
║    widget = FloatWidget(kodi_ip="192.168.1.100")         ║
║    widget.show_floating_button()                         ║
╚══════════════════════════════════════════════════════════╝
""")
    
    if len(sys.argv) > 1:
        kodi_ip = sys.argv[1]
        widget = FloatWidget(kodi_ip=kodi_ip)
        widget.show_floating_button()
        print(f"Widget activo. Kodi: {kodi_ip}")
        print("Presiona Ctrl+C para salir")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nWidget detenido")
    else:
        print("Uso: python float_widget.py <kodi_ip>")