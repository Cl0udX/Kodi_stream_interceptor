#!/bin/bash
echo "🎬 Stream Interceptor iniciado..."
echo "   Proxy: 127.0.0.1:8082"
echo "   Kodi: 192.168.128.10:8080"
echo "   Abre tu navegador y carga la película"
echo ""
mitmdump -s "/Users/santo/Documents/Kodi/stream_interceptor/main.py" --listen-port 8082 --quiet
