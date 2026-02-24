#!/bin/bash
# start.sh - Inicia el interceptor con configuración automática de proxy

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAIN_PY="$SCRIPT_DIR/main.py"
CACHE_DIR="$SCRIPT_DIR/cache"

# Función para limpiar cache
clean_cache() {
    echo "🧹 Limpiando cache..."
    if [ -d "$CACHE_DIR" ]; then
        rm -rf "$CACHE_DIR"/*
        echo "✅ Cache limpiado"
    fi
}

# Función para configurar el proxy del sistema
enable_proxy() {
    echo "🔧 Configurando proxy del sistema..."
    
    # Configurar proxy HTTP y HTTPS
    networksetup -setwebproxy Wi-Fi 127.0.0.1 8082
    networksetup -setsecurewebproxy Wi-Fi 127.0.0.1 8082
    networksetup -setwebproxystate Wi-Fi on
    networksetup -setsecurewebproxystate Wi-Fi on
    
    echo "✅ Proxy configurado (127.0.0.1:8082)"
}

# Función para desconfigurar el proxy del sistema
disable_proxy() {
    echo "🔧 Desconfigurando proxy del sistema..."
    
    # Desactivar proxy HTTP y HTTPS
    networksetup -setwebproxystate Wi-Fi off
    networksetup -setsecurewebproxystate Wi-Fi off
    
    echo "✅ Proxy desactivado"
}

# Función para limpiar al salir
cleanup() {
    echo ""
    echo "🧹 Limpiando..."
    disable_proxy
    pkill -f "mitmdump.*main.py" 2>/dev/null
    lsof -ti:8888 | xargs kill -9 2>/dev/null
    lsof -ti:8082 | xargs kill -9 2>/dev/null
    echo "👋 ¡Hasta luego!"
    exit 0
}

# Capturar Ctrl+C
trap cleanup SIGINT SIGTERM

# Verificar si ya está corriendo
if lsof -i:8082 >/dev/null 2>&1; then
    echo "⚠️  El puerto 8082 ya está en uso. Matando proceso anterior..."
    lsof -ti:8082 | xargs kill -9 2>/dev/null
    sleep 1
fi

if lsof -i:8888 >/dev/null 2>&1; then
    echo "⚠️  El puerto 8888 ya está en uso. Matando proceso anterior..."
    lsof -ti:8888 | xargs kill -9 2>/dev/null
    sleep 1
fi

# Limpiar cache al inicio
clean_cache

# Configurar proxy
enable_proxy

echo ""
echo "🚀 Iniciando Stream Interceptor..."
echo "   Presiona Ctrl+C para detener"
echo ""

# Ejecutar mitmdump
mitmdump -s "$MAIN_PY" --listen-port 8082 --quiet

# Si mitmdump termina, limpiar
cleanup