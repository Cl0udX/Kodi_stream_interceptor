#!/bin/bash
# Instalador de KodiPlay para Android/Termux con Ubuntu (proot)

echo "╔══════════════════════════════════════════════════════════╗"
echo "║         🎬 KodiPlay Android - Instalador                ║"
echo "║            (Ubuntu via proot-distro)                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Verificar que estamos en Termux
if [ ! -d "/data/data/com.termux" ]; then
    echo "⚠️  Este script debe ejecutarse en Termux (Android)"
    echo "   Descarga Termux desde: https://f-droid.org/packages/com.termux/"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════
# FASE 1: Instalar proot-distro y Ubuntu
# ═══════════════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  FASE 1: Instalando proot-distro y Ubuntu"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Actualizar paquetes de Termux
echo "📦 Actualizando paquetes de Termux..."
pkg update -y && pkg upgrade -y

# Instalar proot-distro
echo "📦 Instalando proot-distro..."
pkg install -y proot-distro git wget curl termux-api

# Instalar Ubuntu
echo "📦 Instalando Ubuntu (esto puede tardar unos minutos)..."
proot-distro install ubuntu

echo "✅ Ubuntu instalado"

# ═══════════════════════════════════════════════════════════════════════
# FASE 2: Configurar Ubuntu con dependencias
# ═══════════════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  FASE 2: Configurando Ubuntu"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Crear script de configuración de Ubuntu
cat > ~/ubuntu_setup.sh << 'UBUNTU_EOF'
#!/bin/bash
set -e

echo "📦 Actualizando Ubuntu..."
apt update && apt upgrade -y

echo "📦 Instalando dependencias del sistema..."
apt install -y python3 python3-pip python3-venv git wget curl build-essential libffi-dev libssl-dev

echo "📦 Instalando dependencias de Python..."
pip3 install --upgrade pip
pip3 install mitmproxy yt-dlp streamlink

echo "✅ Ubuntu configurado correctamente"
UBUNTU_EOF
chmod +x ~/ubuntu_setup.sh

# Ejecutar configuración dentro de Ubuntu
echo "📦 Ejecutando configuración dentro de Ubuntu..."
proot-distro login ubuntu -- ~/ubuntu_setup.sh

# ═══════════════════════════════════════════════════════════════════════
# FASE 3: Instalar KodiPlay
# ═══════════════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  FASE 3: Instalando KodiPlay"
echo "═══════════════════════════════════════════════════════════"
echo ""

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

# Crear script de inicio para Ubuntu
cat > ~/kodiplay/start_ubuntu.sh << 'EOF'
#!/bin/bash
# Ejecutar KodiPlay dentro de Ubuntu (proot)
cd ~/kodiplay
proot-distro login ubuntu -- python3 /root/kodiplay/kodi_android.py
EOF
chmod +x ~/kodiplay/start_ubuntu.sh

# Crear acceso directo en ~/bin
mkdir -p ~/bin
cat > ~/bin/kodiplay << 'EOF'
#!/bin/bash
# KodiPlay - Ejecutar en Ubuntu (proot)
cd ~/kodiplay
proot-distro login ubuntu -- python3 /root/kodiplay/kodi_android.py
EOF
chmod +x ~/bin/kodiplay

# Crear script para generar certificado dentro de Ubuntu
cat > ~/kodiplay/gen_cert.sh << 'EOF'
#!/bin/bash
proot-distro login ubuntu -- bash -c "mitmdump --help 2>/dev/null; cp ~/.mitmproxy/mitmproxy-ca-cert.pem /root/kodiplay/"
EOF
chmod +x ~/kodiplay/gen_cert.sh

# Generar certificado HTTPS
echo ""
echo "🔐 Generando certificado HTTPS..."
proot-distro login ubuntu -- bash -c "mitmdump --help 2>/dev/null || true"

# Instrucciones finales
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  📱 INSTALACIÓN COMPLETADA                              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Para ejecutar:                                         ║"
echo "║    kodiplay                                             ║"
echo "║                                                          ║"
echo "║  O manualmente:                                         ║"
echo "║    cd ~/kodiplay && ./start_ubuntu.sh                   ║"
echo "║                                                          ║"
echo "║  Luego abre en tu navegador:                            ║"
echo "║    http://TU_IP:5000                                    ║"
echo "║                                                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  ⚠️  CERTIFICADO HTTPS (Opcional pero recomendado)      ║"
echo "║                                                          ║"
echo "║  El certificado está en:                                ║"
echo "║    ~/.mitmproxy/mitmproxy-ca-cert.pem (en Ubuntu)       ║"
echo "║                                                          ║"
echo "║  Para instalarlo en Android:                            ║"
echo "║  1. Copia el certificado a Descargas                    ║"
echo "║  2. Settings > Security > Install certificate           ║"
echo "║  3. Selecciona el archivo .pem                          ║"
echo "║                                                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  📝 NOTAS IMPORTANTES                                   ║"
echo "║                                                          ║"
echo "║  - KodiPlay corre dentro de Ubuntu (proot)              ║"
echo "║  - mitmproxy funciona correctamente en Ubuntu           ║"
echo "║  - El proxy del sistema debe configurarse manualmente   ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Preguntar si quiere iniciar ahora
read -p "¿Iniciar KodiPlay ahora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    cd ~/kodiplay && ./start_ubuntu.sh
fi
