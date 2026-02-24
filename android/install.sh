#!/bin/bash
# Instalador de KodiPlay para Android/Termux

echo "╔══════════════════════════════════════════════════════════╗"
echo "║         🎬 KodiPlay Android - Instalador                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Verificar que estamos en Termux
if [ ! -d "/data/data/com.termux" ]; then
    echo "⚠️  Este script debe ejecutarse en Termux (Android)"
    echo "   Descarga Termux desde: https://f-droid.org/packages/com.termux/"
    exit 1
fi

# Actualizar paquetes
echo "📦 Actualizando paquetes..."
pkg update -y && pkg upgrade -y

# Instalar dependencias del sistema
echo "📦 Instalando dependencias del sistema..."
pkg install -y python python-pip git wget curl

# Instalar dependencias de Python
echo "📦 Instalando dependencias de Python..."
pip install --upgrade pip
pip install mitmproxy yt-dlp streamlink

# Crear directorio de la app
echo "📁 Creando directorio de la aplicación..."
mkdir -p ~/kodiplay
mkdir -p ~/kodiplay/cache

# Copiar archivos del interceptor
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/../stream_interceptor" ]; then
    cp -r "$SCRIPT_DIR/../stream_interceptor" ~/kodiplay/
    echo "   ✅ Interceptor copiado"
fi

# Copiar GUI Android
if [ -f "$SCRIPT_DIR/kodi_android.py" ]; then
    cp "$SCRIPT_DIR/kodi_android.py" ~/kodiplay/
    echo "   ✅ GUI Android copiada"
fi

# Crear script de inicio
cat > ~/kodiplay/start.sh << 'EOF'
#!/bin/bash
cd ~/kodiplay
python kodi_android.py
EOF
chmod +x ~/kodiplay/start.sh

# Crear acceso directo en ~/bin
mkdir -p ~/bin
cat > ~/bin/kodiplay << 'EOF'
#!/bin/bash
cd ~/kodiplay && python kodi_android.py
EOF
chmod +x ~/bin/kodiplay

# Configurar proxy para mitmproxy
echo ""
echo "🔐 Configurando certificado HTTPS..."
echo "   (Necesario para interceptar tráfico HTTPS)"
echo ""

# Generar certificado si no existe
if [ ! -f ~/.mitmproxy/mitmproxy-ca-cert.pem ]; then
    mitmdump --help > /dev/null 2>&1  # Genera certificados
fi

# Instrucciones para instalar certificado
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  📱 INSTALACIÓN COMPLETADA                              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Para ejecutar:                                         ║"
echo "║    kodiplay                                             ║"
echo "║                                                          ║"
echo "║  O manualmente:                                         ║"
echo "║    cd ~/kodiplay && python kodi_android.py              ║"
echo "║                                                          ║"
echo "║  Luego abre en tu navegador:                            ║"
echo "║    http://TU_IP:5000                                    ║"
echo "║                                                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  ⚠️  CERTIFICADO HTTPS (Opcional pero recomendado)      ║"
echo "║                                                          ║"
echo "║  Para interceptar HTTPS necesitas instalar el cert:     ║"
echo "║  1. Transfiere ~/.mitmproxy/mitmproxy-ca-cert.pem       ║"
echo "║  2. En Android: Settings > Security > Install cert     ║"
echo "║  3. Selecciona el archivo .pem                          ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Preguntar si quiere iniciar ahora
read -p "¿Iniciar KodiPlay ahora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    cd ~/kodiplay && python kodi_android.py
fi