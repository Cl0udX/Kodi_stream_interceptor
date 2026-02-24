#!/usr/bin/env python3
"""
KodiPlay - GUI para controlar Kodi desde Mac
Dependencias: yt-dlp, streamlink (brew install yt-dlp streamlink)
Uso: python3 kodiplay.py
"""

import tkinter as tk
from tkinter import ttk
import threading
import subprocess
import json
import urllib.request
import socket
import os

# ─── Configuración ────────────────────────────────────────────────────────────
KODI_PORT    = 8080
SCAN_TIMEOUT = 0.5

QUALITY_OPTIONS = ["media", "baja", "alta", "original"]

# ─── Colores ──────────────────────────────────────────────────────────────────
BG        = "#0e0e16"
SURFACE   = "#16161f"
SURFACE2  = "#1e1e2e"
BORDER    = "#2a2a3e"
ACCENT    = "#e8ff47"
ACCENT2   = "#ff4757"
TEXT      = "#e8e8f0"
MUTED     = "#55556a"
GREEN     = "#4eff91"
FONT_MAIN = "SF Pro Display"
FONT_MONO = "SF Mono"

# ─── Kodi API ─────────────────────────────────────────────────────────────────
def kodi_request(ip, port, method, params=None):
    payload = json.dumps({
        "jsonrpc": "2.0", "method": method,
        "params": params or {}, "id": 1
    }).encode()
    req = urllib.request.Request(
        f"http://{ip}:{port}/jsonrpc", payload,
        {"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=3)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def is_kodi(ip, port=KODI_PORT):
    try:
        r = kodi_request(ip, port, "JSONRPC.Ping")
        return "result" in r and r["result"] == "pong"
    except:
        return False

def scan_network():
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        network = ".".join(local_ip.split(".")[:3])

        def check(i):
            ip = f"{network}.{i}"
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SCAN_TIMEOUT)
            if sock.connect_ex((ip, KODI_PORT)) == 0:
                sock.close()
                if is_kodi(ip, KODI_PORT):
                    found.append({"ip": ip, "port": KODI_PORT, "name": f"Kodi @ {ip}"})
            else:
                sock.close()

        threads = [threading.Thread(target=check, args=(i,), daemon=True) for i in range(1, 255)]
        for t in threads: t.start()
        for t in threads: t.join()
    except Exception as e:
        print(f"Scan error: {e}")
    return found

# ─── Extracción de formatos ───────────────────────────────────────────────────
FORMAT_MAP = {
    "baja":     "best[ext=mp4][height<=480]/best[height<=480]",
    "media":    "best[ext=mp4][height<=720]/best[height<=720]",
    "alta":     "best[ext=mp4][height<=1080]/best[height<=1080]",
    "original": "best[ext=mp4]/best",
}
STREAMLINK_MAP = {
    "baja": "480p,360p,worst", "media": "720p,480p,best",
    "alta": "1080p,720p,best", "original": "best",
}

def get_formats(link):
    """Retorna (título, lista de formatos con metadatos) via yt-dlp -J."""
    try:
        result = subprocess.run(
            ["yt-dlp", "-J", link],
            capture_output=True, text=True, timeout=30
        )
        data    = json.loads(result.stdout)
        formats = data.get("formats", [])
        title   = data.get("title", "Sin título")

        useful = []
        for f in formats:
            vcodec = f.get("vcodec", "none")
            if not vcodec or vcodec == "none":
                continue
            fid    = f.get("format_id", "?")
            ext    = f.get("ext", "?")
            height = f.get("height")
            acodec = f.get("acodec", "none")
            lang   = f.get("language") or ""
            note   = f.get("format_note", "")
            tbr    = f.get("tbr") or f.get("abr") or 0
            fps    = f.get("fps")

            has_audio = acodec and acodec != "none"
            res       = f"{height}p" if height else "?"
            fps_str   = f" {fps}fps" if fps else ""
            audio_str = "🔊" if has_audio else "🔇"
            lang_str  = f" [{lang.upper()}]" if lang else ""
            note_str  = f" {note}" if note else ""
            tbr_str   = f" ~{int(tbr)}kbps" if tbr else ""

            label = f"{audio_str}  {res}{fps_str}  {ext.upper()}{lang_str}{note_str}{tbr_str}"
            useful.append({
                "id": fid, "label": label,
                "height": height or 0,
                "has_audio": has_audio,
            })

        return title, useful
    except Exception as e:
        return None, []

def get_streamlink_qualities(link):
    try:
        result = subprocess.run(
            ["streamlink", link],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            if "Available streams:" in line:
                qualities = line.split("Available streams:")[-1].strip()
                return [q.strip().replace("(best)", "★").replace("(worst)", "↓").strip()
                        for q in qualities.split(",")]
    except:
        pass
    return []

def extract_url_direct(link, quality, format_id=None):
    if link.endswith(".m3u8") or ".m3u8?" in link or link.endswith(".m3u"):
        return link
    if "twitch.tv" in link:
        q      = STREAMLINK_MAP.get(quality, "best")
        result = subprocess.run(
            ["streamlink", "--stream-url", "--twitch-disable-ads",
             "--twitch-low-latency", link, q],
            capture_output=True, text=True, timeout=30
        )
        url = result.stdout.strip().split("\n")[0]
        return url if url else None
    fmt    = format_id if format_id else FORMAT_MAP.get(quality, FORMAT_MAP["media"])
    result = subprocess.run(
        ["yt-dlp", "-g", "-f", fmt, link],
        capture_output=True, text=True, timeout=30
    )
    url = result.stdout.strip().split("\n")[0]
    return url if url else None


# ─── Ventana de selección de formato ─────────────────────────────────────────
class FormatSelector(tk.Toplevel):
    def __init__(self, parent, title, formats, is_twitch=False, twitch_qualities=None):
        super().__init__(parent)
        self.title("Seleccionar formato")
        self.geometry("600x440")
        self.configure(bg=BG)
        self.resizable(False, True)
        self.grab_set()

        self.selected        = None
        self.formats         = formats
        self.is_twitch       = is_twitch
        self.twitch_qualities = twitch_qualities or []

        self._build(title)

    def _build(self, title):
        tk.Label(self, text="SELECCIONAR FORMATO",
                 font=(FONT_MONO, 11, "bold"), fg=ACCENT, bg=BG
                 ).pack(padx=20, pady=(16, 4), anchor="w")

        short_title = title[:72] + ("..." if len(title) > 72 else "")
        tk.Label(self, text=short_title, font=(FONT_MONO, 9), fg=MUTED, bg=BG
                 ).pack(padx=20, anchor="w")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20, pady=10)

        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=20)

        sb = tk.Scrollbar(list_frame, bg=SURFACE2, troughcolor=BG, relief="flat", bd=0)
        sb.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame, font=(FONT_MONO, 10), bg=SURFACE, fg=TEXT,
            selectbackground=SURFACE2, selectforeground=ACCENT,
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            yscrollcommand=sb.set
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)

        items = self.twitch_qualities if self.is_twitch else self.formats
        for item in items:
            label = item if self.is_twitch else item["label"]
            self.listbox.insert("end", f"  {label}")

        if items:
            self.listbox.selection_set(0)

        self.listbox.bind("<Double-Button-1>", lambda e: self.confirm())
        self.bind("<Return>", lambda e: self.confirm())
        self.bind("<Escape>", lambda e: self.cancel())

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=14)

        tk.Button(btn_frame, text="✓ Seleccionar",
                  font=(FONT_MONO, 10, "bold"), bg=ACCENT, fg="#000",
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=self.confirm).pack(side="left")

        tk.Button(btn_frame, text="Auto (recomendado)",
                  font=(FONT_MONO, 10), bg=SURFACE2, fg=TEXT,
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=self.auto_select).pack(side="left", padx=(8, 0))

        tk.Button(btn_frame, text="Cancelar",
                  font=(FONT_MONO, 10), bg=SURFACE2, fg=MUTED,
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=self.cancel).pack(side="right")

    def confirm(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if self.is_twitch:
            q = self.twitch_qualities[idx].replace("★", "").replace("↓", "").strip()
            self.selected = ("twitch", q)
        else:
            self.selected = ("format", self.formats[idx]["id"])
        self.destroy()

    def auto_select(self):
        self.selected = ("auto", None)
        self.destroy()

    def cancel(self):
        self.selected = None
        self.destroy()


# ─── GUI Principal ────────────────────────────────────────────────────────────
class KodiPlay(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KodiPlay")
        self.geometry("720x620")
        self.minsize(600, 540)
        self.configure(bg=BG)
        self.resizable(True, True)

        self.devices         = []
        self.selected_device = None

        self._build_ui()
        self.after(300, self.start_scan)

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(header, text="KODI", font=(FONT_MAIN, 28, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(header, text="PLAY", font=(FONT_MAIN, 28, "bold"),
                 fg=TEXT, bg=BG).pack(side="left", padx=(2, 0))

        self.status_dot = tk.Label(header, text="●", font=("", 10), fg=MUTED, bg=BG)
        self.status_dot.pack(side="right", pady=4)
        self.status_lbl = tk.Label(header, text="Buscando dispositivos...",
                                    font=(FONT_MONO, 10), fg=MUTED, bg=BG)
        self.status_lbl.pack(side="right", padx=6)

        # Dispositivos
        dev_frame = tk.Frame(self, bg=BG)
        dev_frame.pack(fill="x", padx=24, pady=(16, 0))

        tk.Label(dev_frame, text="DISPOSITIVO", font=(FONT_MONO, 9),
                 fg=MUTED, bg=BG).pack(anchor="w")

        sel_row = tk.Frame(dev_frame, bg=BG)
        sel_row.pack(fill="x", pady=(4, 0))

        self.device_var  = tk.StringVar(value="Buscando...")
        self.device_menu = ttk.Combobox(sel_row, textvariable=self.device_var,
                                         state="disabled", font=(FONT_MONO, 11))
        self.device_menu.pack(side="left", fill="x", expand=True)
        self.device_menu.bind("<<ComboboxSelected>>", self.on_device_select)

        tk.Button(sel_row, text="⟳ Escanear", font=(FONT_MONO, 10),
                  bg=SURFACE2, fg=TEXT, relief="flat", padx=12, pady=6,
                  cursor="hand2", activebackground=BORDER,
                  command=self.start_scan).pack(side="left", padx=(8, 0))

        man_row = tk.Frame(dev_frame, bg=BG)
        man_row.pack(fill="x", pady=(6, 0))

        self.ip_entry = tk.Entry(man_row, font=(FONT_MONO, 10),
                                  bg=SURFACE, fg=MUTED, insertbackground=TEXT,
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=ACCENT)
        self.ip_entry.insert(0, "IP manual (ej: 192.168.1.100:8080)")
        self.ip_entry.bind("<FocusIn>", self._clear_ip_placeholder)
        self.ip_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        tk.Button(man_row, text="Conectar", font=(FONT_MONO, 10),
                  bg=SURFACE2, fg=ACCENT, relief="flat", padx=10, pady=6,
                  cursor="hand2", command=self.connect_manual).pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=16)

        # URL
        url_frame = tk.Frame(self, bg=BG)
        url_frame.pack(fill="x", padx=24)

        tk.Label(url_frame, text="LINK", font=(FONT_MONO, 9),
                 fg=MUTED, bg=BG).pack(anchor="w")

        url_row = tk.Frame(url_frame, bg=BG)
        url_row.pack(fill="x", pady=(4, 0))

        self.url_var   = tk.StringVar()
        self.url_entry = tk.Entry(url_row, textvariable=self.url_var,
                                   font=(FONT_MONO, 11), bg=SURFACE, fg=TEXT,
                                   insertbackground=ACCENT, relief="flat",
                                   highlightthickness=1, highlightbackground=BORDER,
                                   highlightcolor=ACCENT)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.play_now())

        self.quality_var = tk.StringVar(value="media")
        ttk.Combobox(url_row, textvariable=self.quality_var,
                     values=QUALITY_OPTIONS, state="readonly",
                     font=(FONT_MONO, 10), width=9).pack(side="left")

        # Checkbox selección de formato
        fmt_row = tk.Frame(url_frame, bg=BG)
        fmt_row.pack(fill="x", pady=(6, 0))

        self.ask_format_var = tk.BooleanVar(value=True)
        tk.Checkbutton(fmt_row, text="Pedir selección de formato si hay múltiples opciones",
                       variable=self.ask_format_var,
                       font=(FONT_MONO, 9), fg=MUTED, bg=BG,
                       selectcolor=SURFACE2, activebackground=BG,
                       activeforeground=TEXT).pack(side="left")

        # Botones
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=10)

        self.play_btn = self._mk_btn(btn_frame, "▶  REPRODUCIR", ACCENT, "#000",
                                      self.play_now, big=True)
        self.play_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._mk_btn(btn_frame, "+ COLA", SURFACE2, TEXT,
                     self.add_queue).pack(side="left")

        # Controles playback
        ctrl = tk.Frame(self, bg=SURFACE)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))

        for sym, cmd in [("⏮", self.prev_track), ("⏪", self.seek_back),
                         ("⏸", self.pause), ("⏩", self.seek_fwd),
                         ("⏭", self.next_track), ("⏹", self.stop)]:
            tk.Button(ctrl, text=sym, font=("", 16), bg=SURFACE, fg=TEXT,
                      relief="flat", padx=14, pady=8, cursor="hand2",
                      activebackground=SURFACE2, activeforeground=ACCENT,
                      command=cmd).pack(side="left")

        tk.Label(ctrl, text="VOL", font=(FONT_MONO, 8), fg=MUTED,
                 bg=SURFACE).pack(side="right", padx=(0, 4))
        self.vol_slider = ttk.Scale(ctrl, from_=0, to=100,
                                     orient="horizontal", length=90,
                                     command=self.set_volume)
        self.vol_slider.set(80)
        self.vol_slider.pack(side="right", padx=8)

        # Log
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(10, 0))

        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(8, 20))

        tk.Label(log_frame, text="LOG", font=(FONT_MONO, 9),
                 fg=MUTED, bg=BG).pack(anchor="w")

        self.log = tk.Text(log_frame, bg=SURFACE, fg=MUTED, font=(FONT_MONO, 9),
                           relief="flat", state="disabled", wrap="word",
                           highlightthickness=0, bd=0)
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        for tag, color in [("ok", GREEN), ("err", ACCENT2), ("info", TEXT), ("accent", ACCENT)]:
            self.log.tag_config(tag, foreground=color)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                        foreground=TEXT, selectbackground=SURFACE2,
                        bordercolor=BORDER, arrowcolor=MUTED)

    def _mk_btn(self, parent, text, bg, fg, cmd, big=False):
        return tk.Button(parent, text=text,
                         font=(FONT_MONO, 12 if big else 10, "bold"),
                         bg=bg, fg=fg, relief="flat", padx=16, pady=10,
                         cursor="hand2", activebackground=BORDER,
                         activeforeground=fg, command=cmd)

    def _clear_ip_placeholder(self, e):
        if self.ip_entry.get().startswith("IP"):
            self.ip_entry.delete(0, "end")
            self.ip_entry.config(fg=TEXT)

    # ── Log / Status ─────────────────────────────────────────────────────────
    def log_msg(self, msg, tag="info"):
        if not hasattr(self, 'log') or self.log is None:
            return
        self.log.configure(state="normal")
        self.log.insert("end", f"› {msg}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, msg, color=MUTED):
        self.status_lbl.config(text=msg)
        self.status_dot.config(fg=color)

    # ── Escaneo ──────────────────────────────────────────────────────────────
    def start_scan(self):
        self.devices = []
        self.device_menu.config(state="disabled")
        self.device_var.set("Escaneando red...")
        self.set_status("Escaneando...", ACCENT)
        self.log_msg("Buscando dispositivos Kodi en la red...", "accent")
        threading.Thread(
            target=lambda: self.after(0, self._scan_done, scan_network()),
            daemon=True
        ).start()

    def _scan_done(self, found):
        self.devices = found
        if found:
            names = [d["name"] for d in found]
            self.device_menu["values"] = names
            self.device_menu.config(state="readonly")
            self.device_var.set(names[0])
            self.selected_device = found[0]
            self.set_status(f"{len(found)} dispositivo(s)", GREEN)
            self.log_msg(f"Encontrado: {found[0]['ip']}:{found[0]['port']}", "ok")
        else:
            self.device_var.set("No se encontraron dispositivos")
            self.set_status("Sin dispositivos", ACCENT2)
            self.log_msg("Sin dispositivos. Usa IP manual.", "err")

    def on_device_select(self, event):
        name = self.device_var.get()
        for d in self.devices:
            if d["name"] == name:
                self.selected_device = d
                self.log_msg(f"Seleccionado: {d['ip']}:{d['port']}", "ok")
                break

    def connect_manual(self):
        raw = self.ip_entry.get().strip()
        if not raw or raw.startswith("IP"):
            return
        parts = raw.split(":")
        ip    = parts[0]
        port  = int(parts[1]) if len(parts) > 1 else KODI_PORT
        self.log_msg(f"Conectando a {ip}:{port}...", "accent")
        threading.Thread(target=self._connect_thread, args=(ip, port), daemon=True).start()

    def _connect_thread(self, ip, port):
        ok = is_kodi(ip, port)
        self.after(0, self._connect_done, ip, port, ok)

    def _connect_done(self, ip, port, ok):
        if ok:
            device = {"ip": ip, "port": port, "name": f"Kodi @ {ip}"}
            self.devices.append(device)
            self.selected_device = device
            names = [d["name"] for d in self.devices]
            self.device_menu["values"] = names
            self.device_menu.config(state="readonly")
            self.device_var.set(device["name"])
            self.set_status("Conectado", GREEN)
            self.log_msg(f"Conectado a {ip}:{port}", "ok")
        else:
            self.log_msg(f"No se pudo conectar a {ip}:{port}", "err")

    # ── Playback ─────────────────────────────────────────────────────────────
    def _get_device(self):
        if not self.selected_device:
            self.log_msg("No hay dispositivo seleccionado", "err")
            return None
        return self.selected_device

    def play_now(self):
        self._start_playback("Player.Open")

    def add_queue(self):
        self._start_playback("queue")

    def _start_playback(self, method):
        link   = self.url_var.get().strip()
        device = self._get_device()
        if not link:
            self.log_msg("Pega un link primero", "err")
            return
        if not device:
            return

        quality    = self.quality_var.get()
        ask_format = self.ask_format_var.get()
        is_direct  = link.endswith(".m3u8") or ".m3u8?" in link or link.endswith(".m3u")
        is_twitch  = "twitch.tv" in link

        self.play_btn.config(state="disabled", text="⏳ Analizando...")
        self.log_msg(f"Analizando: {link[:60]}...", "accent")

        threading.Thread(
            target=self._analyze_thread,
            args=(link, quality, device, method, ask_format, is_direct, is_twitch),
            daemon=True
        ).start()

    def _analyze_thread(self, link, quality, device, method, ask_format, is_direct, is_twitch):
        try:
            # Stream directo — sin análisis
            if is_direct:
                self.after(0, self._send_url, link, device, method)
                return

            # Twitch
            if is_twitch:
                if ask_format:
                    qualities = get_streamlink_qualities(link)
                    if qualities:
                        self.after(0, self._show_twitch_selector,
                                   link, qualities, quality, device, method)
                        return
                url = extract_url_direct(link, quality)
                self.after(0, self._send_url, url, device, method)
                return

            # yt-dlp con selección de formato
            if ask_format:
                title, formats = get_formats(link)
                if formats and len(formats) > 1:
                    self.after(0, self._show_format_selector,
                               link, title or link, formats, quality, device, method)
                    return

            url = extract_url_direct(link, quality)
            self.after(0, self._send_url, url, device, method)

        except Exception as e:
            self.after(0, self.log_msg, f"Error: {e}", "err")
            self.after(0, lambda: self.play_btn.config(state="normal", text="▶  REPRODUCIR"))

    def _show_format_selector(self, link, title, formats, quality, device, method):
        self.play_btn.config(state="normal", text="▶  REPRODUCIR")
        dlg = FormatSelector(self, title, formats)
        self.wait_window(dlg)

        if dlg.selected is None:
            self.log_msg("Cancelado", "err")
            return

        kind, value = dlg.selected
        self.play_btn.config(state="disabled", text="⏳ Procesando...")
        self.log_msg(f"{'Formato automático' if kind == 'auto' else 'Formato: ' + value}", "accent")

        fmt_id = None if kind == "auto" else value
        threading.Thread(
            target=lambda: self.after(0, self._send_url,
                                      extract_url_direct(link, quality, format_id=fmt_id),
                                      device, method),
            daemon=True
        ).start()

    def _show_twitch_selector(self, link, qualities, quality, device, method):
        self.play_btn.config(state="normal", text="▶  REPRODUCIR")
        dlg = FormatSelector(self, f"Twitch: {link}", [],
                             is_twitch=True, twitch_qualities=qualities)
        self.wait_window(dlg)

        if dlg.selected is None:
            self.log_msg("Cancelado", "err")
            return

        kind, value   = dlg.selected
        chosen_q      = value if kind == "twitch" else STREAMLINK_MAP.get(quality, "best")
        self.play_btn.config(state="disabled", text="⏳ Procesando...")
        self.log_msg(f"Calidad Twitch: {chosen_q}", "accent")

        def run():
            result = subprocess.run(
                ["streamlink", "--stream-url", "--twitch-disable-ads",
                 "--twitch-low-latency", link, chosen_q],
                capture_output=True, text=True, timeout=30
            )
            url = result.stdout.strip().split("\n")[0]
            self.after(0, self._send_url, url if url else None, device, method)

        threading.Thread(target=run, daemon=True).start()

    def _send_url(self, url, device, method):
        try:
            if not url:
                self.log_msg("No se pudo extraer la URL", "err")
                return
            if method == "queue":
                result = kodi_request(device["ip"], device["port"],
                                      "Playlist.Add",
                                      {"playlistid": 1, "item": {"file": url}})
                self.log_msg("✅ Añadido a la cola!" if "result" in result
                             else f"Error: {result}", "ok" if "result" in result else "err")
            else:
                result = kodi_request(device["ip"], device["port"],
                                      "Player.Open", {"item": {"file": url}})
                self.log_msg("✅ Reproduciendo!" if "result" in result
                             else f"Error: {result}", "ok" if "result" in result else "err")
        finally:
            self.play_btn.config(state="normal", text="▶  REPRODUCIR")

    # ── Controles ────────────────────────────────────────────────────────────
    def pause(self):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"], "Player.PlayPause", {"playerid": 1})
            self.log_msg("⏸ Pausa / Reanudar", "info")

    def stop(self):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"], "Player.Stop", {"playerid": 1})
            self.log_msg("⏹ Detenido", "info")

    def seek_fwd(self):  self._seek(30)
    def seek_back(self): self._seek(-30)

    def _seek(self, s):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"],
                         "Player.Seek", {"playerid": 1, "value": {"seconds": s}})
            self.log_msg(f"{'⏩' if s > 0 else '⏪'} {abs(s)}s", "info")

    def next_track(self):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"], "Player.GoTo", {"playerid": 1, "to": "next"})
            self.log_msg("⏭ Siguiente", "info")

    def prev_track(self):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"], "Player.GoTo", {"playerid": 1, "to": "previous"})
            self.log_msg("⏮ Anterior", "info")

    def set_volume(self, val):
        d = self._get_device()
        if d:
            kodi_request(d["ip"], d["port"],
                         "Application.SetVolume", {"volume": int(float(val))})


if __name__ == "__main__":
    app = KodiPlay()
    app.mainloop()