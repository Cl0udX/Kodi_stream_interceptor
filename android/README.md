# KodiPlay para Android - Guía Completa de Instalación

## 📋 Requisitos Previos

- **Android 7.0+** (recomendado Android 10+)
- **2GB RAM mínimo** (4GB recomendado)
- **4GB espacio libre** en almacenamiento
- **Conexión WiFi** (misma red que Kodi)

---

## 📱 PASO 1: Instalar Termux y Termux:API

### ⚠️ IMPORTANTE: NO uses Google Play Store

Las versiones en Play Store están **desactualizadas y no funcionan**. Debes descargar desde F-Droid.

### Descargar desde F-Droid:

1. **Termux:**
   - Ir a: https://f-droid.org/packages/com.termux/
   - Descargar el APK
   - Instalar (permitir instalación de orígenes desconocidos)

2. **Termux:API** (opcional, para notificaciones):
   - Ir a: https://f-droid.org/packages/com.termux.api/
   - Descargar e instalar

### Verificar instalación:

Abre Termux y ejecuta:
```bash
echo "Termux funciona!"
```

Si ves "Termux funciona!", todo está correcto.

---

## 📦 PASO 2: Preparar Termux

### 2.1 Actualizar paquetes de Termux

```bash
pkg update
```

Si pregunta `[Y/n]`, presiona `Y` y Enter.

```bash
pkg upgrade -y
```

### 2.2 Instalar herramientas básicas

```bash
pkg install -y git wget curl proot-distro
```

Espera a que termine (puede tardar 1-2 minutos).

### 2.3 Verificar instalación

```bash
which git
which proot-distro
```

Debes ver rutas como `/data/data/com.termux/files/usr/bin/git`

---

## 🐧 PASO 3: Instalar Ubuntu (proot-distro)

### 3.1 Instalar Ubuntu

```bash
proot-distro install ubuntu
```

**Esto tarda 3-5 minutos.** Verás progreso como:
```
Installing Ubuntu...
Downloading rootfs...
Extracting...
```

### 3.2 Verificar instalación

```bash
proot-distro list
```

Debes ver `ubuntu` en la lista con estado `installed`.

---

## 🔧 PASO 4: Configurar Ubuntu

### 4.1 Entrar a Ubuntu

```bash
proot-distro login ubuntu
```

El prompt cambiará a algo como:
```
root@localhost:~#
```

### 4.2 Actualizar Ubuntu (dentro de Ubuntu)

```bash
apt update
```

Si hay errores, intenta:
```bash
apt update --fix-missing
```

```bash
apt upgrade -y
```

### 4.3 Instalar dependencias del sistema

```bash
apt install -y python3 python3-pip python3-venv
```

```bash
apt install -y build-essential libffi-dev libssl-dev libxml2-dev libxslt1-dev
```

```bash
apt install -y git wget curl
```

### 4.4 Actualizar pip

```bash
pip3 install --upgrade pip setuptools wheel
```

### 4.5 Instalar mitmproxy

```bash
pip3 install mitmproxy
```

**Esto puede tardar 5-10 minutos** porque compila módulos. Paciencia.

Si falla, intenta:
```bash
pip3 install mitmproxy --no-cache-dir
```

### 4.6 Instalar yt-dlp y streamlink

```bash
pip3 install yt-dlp streamlink
```

### 4.7 Verificar instalaciones

```bash
python3 --version
mitmdump --version
yt-dlp --version
```

### 4.8 Salir de Ubuntu

```bash
exit
```

Volverás al prompt de Termux.

---

## 📥 PASO 5: Descargar KodiPlay

### 5.1 Clonar el repositorio

```bash
cd ~
git clone https://github.com/Cl0udX/Kodi_stream_interceptor.git
```

### 5.2 Copiar archivos a Ubuntu

```bash
# Crear directorio en Ubuntu
mkdir -p ~/kodiplay

# Copiar interceptor
cp -r ~/Kodi_stream_interceptor/stream_interceptor ~/kodiplay/

# Copiar GUI Android
cp ~/Kodi_stream_interceptor/android/kodi_android.py ~/kodiplay/
```

### 5.3 Copiar a Ubuntu (proot)

```bash
# Entrar a Ubuntu y crear enlace
proot-distro login ubuntu -- mkdir -p /root/kodiplay

# Copiar archivos
proot-distro login ubuntu -- cp -r /data/data/com.termux/files/home/kodiplay/* /root/kodiplay/
```

---

## 🚀 PASO 6: Crear Script de Inicio

### 6.1 Crear script en Termux

```bash
cat > ~/bin/kodiplay << 'EOF'
#!/bin/bash
echo "🎬 Iniciando KodiPlay..."
proot-distro login ubuntu -- python3 /root/kodiplay/kodi_android.py
EOF

chmod +x ~/bin/kodiplay
```

### 6.2 Agregar bin al PATH

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## ✅ PASO 7: Probar la Instalación

### 7.1 Ejecutar KodiPlay

```bash
kodiplay
```

Debes ver algo como:
```
╔══════════════════════════════════════════════════════════╗
║           🎬 KodiPlay Android                            ║
╠══════════════════════════════════════════════════════════╣
║  GUI Web:     http://192.168.1.XXX:5000                  ║
╚══════════════════════════════════════════════════════════╝
```

### 7.2 Abrir en navegador

En tu navegador Android, abre la URL que aparece (ej: `http://192.168.1.100:5000`)

---

## 🔐 PASO 8: Configurar Certificado HTTPS (Opcional)

### 8.1 Generar certificado

```bash
proot-distro login ubuntu -- mitmdump --help
```

### 8.2 Copiar certificado a almacenamiento

```bash
# Dentro de Ubuntu
proot-distro login ubuntu

# Copiar certificado
cp ~/.mitmproxy/mitmproxy-ca-cert.pem /root/kodiplay/

# Salir
exit
```

### 8.3 Instalar en Android

1. Transfiere `mitmproxy-ca-cert.pem` a Descargas
2. Ve a **Configuración → Seguridad → Instalar certificado**
3. Selecciona **Certificado CA**
4. Elige el archivo `.pem`
5. Nómbralo "KodiPlay"

---

## 📶 PASO 9: Configurar Proxy WiFi

### 9.1 Configurar proxy manual

1. Ve a **Configuración → WiFi**
2. Mantén presionada tu red WiFi
3. Toca **Modificar red** o **Configuración de red**
4. Ve a **Opciones avanzadas**
5. En **Proxy**, selecciona **Manual**
6. Configura:
   - **Nombre de host:** `127.0.0.1`
   - **Puerto:** `8082`
7. Guarda

### 9.2 Quitar proxy cuando termines

Repite los pasos y selecciona **Ninguno** en Proxy.

---

## 🎮 USO

### Iniciar KodiPlay

```bash
kodiplay
```

### Flujo de uso

1. Abre `http://TU_IP:5000` en tu navegador
2. Ingresa la IP de tu Kodi (ej: `192.168.1.100:8080`)
3. Configura el proxy WiFi a `127.0.0.1:8082`
4. Presiona **INICIAR** en la web
5. Abre otra pestaña y carga la película
6. Presiona **ENVIAR A KODI**
7. Cuando termines, presiona **DETENER**
8. Quita el proxy del WiFi

---

## 🔧 Solución de Problemas

### "command not found: proot-distro"

```bash
pkg install proot-distro
```

### "Ubuntu not found"

```bash
proot-distro install ubuntu
```

### "pip: command not found" (en Ubuntu)

```bash
apt install python3-pip
```

### "mitmproxy fails to install"

Intenta instalar dependencias primero:
```bash
apt install -y python3-dev libffi-dev libssl-dev build-essential
pip3 install --upgrade pip
pip3 install mitmproxy --no-cache-dir
```

### "No space left on device"

Libera espacio:
```bash
pkg clean
apt clean  # dentro de Ubuntu
```

### "Connection refused" en navegador

1. Verifica que KodiPlay esté corriendo
2. Verifica que la IP sea correcta
3. Desactiva VPN si tienes una

### El interceptor no captura nada

1. Verifica que el proxy WiFi esté configurado
2. Verifica que el certificado HTTPS esté instalado
3. Algunos sitios usan certificate pinning (no se pueden interceptar)

---

## 📝 Resumen de Comandos

```bash
# En Termux
pkg update && pkg upgrade -y
pkg install -y git wget curl proot-distro
proot-distro install ubuntu

# En Ubuntu (proot-distro login ubuntu)
apt update && apt upgrade -y
apt install -y python3 python3-pip build-essential libffi-dev libssl-dev
pip3 install --upgrade pip
pip3 install mitmproxy yt-dlp streamlink
exit

# En Termux
git clone https://github.com/Cl0udX/Kodi_stream_interceptor.git
mkdir -p ~/kodiplay
cp -r ~/Kodi_stream_interceptor/stream_interceptor ~/kodiplay/
cp ~/Kodi_stream_interceptor/android/kodi_android.py ~/kodiplay/

# Crear script de inicio
mkdir -p ~/bin
cat > ~/bin/kodiplay << 'EOF'
#!/bin/bash
proot-distro login ubuntu -- python3 /root/kodiplay/kodi_android.py
EOF
chmod +x ~/bin/kodiplay

# Copiar a Ubuntu
proot-distro login ubuntu -- mkdir -p /root/kodiplay
proot-distro login ubuntu -- cp -r /data/data/com.termux/files/home/kodiplay/* /root/kodiplay/

# Ejecutar
kodiplay
```

---

## 🆘 Ayuda Adicional

Si tienes problemas:

1. **Reinicia Termux** completamente
2. **Verifica espacio:** `df -h`
3. **Verifica memoria:** `free -h`
4. **Reinstala Ubuntu:**
   ```bash
   proot-distro remove ubuntu
   proot-distro install ubuntu
   ```

---

## 📋 Archivos del Proyecto

| Archivo | Descripción |
|---------|-------------|
| `kodi_android.py` | GUI web principal |
| `float_widget.py` | Widget flotante (opcional) |
| `install.sh` | Script de instalación automática |
| `README.md` | Esta documentación |