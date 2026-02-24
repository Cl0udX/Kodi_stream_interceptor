# KodiPlay para Android

## 🎯 Resumen

KodiPlay Android permite interceptar streams de video desde tu dispositivo Android y enviarlos a Kodi. Funciona completamente en Termux sin necesidad de compilar una APK.

## 📐 Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     ANDROID                                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Termux    │    │  Kodi App   │    │  Navegador  │     │
│  │  (Backend)  │◄──►│  (Player)   │    │  (Película) │     │
│  └──────┬──────┘    └─────────────┘    └──────┬──────┘     │
│         │                                      │            │
│         │  ┌───────────────────────────────────┘            │
│         │  │                                                │
│         ▼  ▼                                                │
│  ┌─────────────────┐                                        │
│  │  Interceptor    │  ◄── mitmproxy (proxy HTTPS)          │
│  │  (Python)       │                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │  GUI Web/Float  │  ◄── http://localhost:5000             │
│  │  (Interfaz)     │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

## 📱 Instalación

### Paso 1: Instalar Termux y Termux:API

**IMPORTANTE:** Descarga desde F-Droid, NO desde Play Store (versiones desactualizadas)

1. **Termux:** https://f-droid.org/packages/com.termux/
2. **Termux:API:** https://f-droid.org/packages/com.termux.api/

### Paso 2: Instalar dependencias

Abre Termux y ejecuta:

```bash
# Actualizar paquetes
pkg update && pkg upgrade -y

# Instalar Python y herramientas
pkg install python python-pip git wget curl termux-api -y

# Instalar dependencias de Python
pip install mitmproxy yt-dlp streamlink
```

### Paso 3: Clonar el proyecto

```bash
git clone https://github.com/Cl0udX/Kodi_stream_interceptor.git
cd Kodi_stream_interceptor
```

### Paso 4: Ejecutar instalación automática

```bash
cd android
chmod +x install.sh
./install.sh
```

### Paso 5: Configurar certificado HTTPS (Opcional pero recomendado)

Para interceptar tráfico HTTPS necesitas instalar el certificado de mitmproxy:

```bash
# Generar certificado
mitmdump --help

# El certificado está en:
~/.mitmproxy/mitmproxy-ca-cert.pem
```

Luego en Android:
1. Configuración → Seguridad → Instalar certificado
2. Selecciona `mitmproxy-ca-cert.pem`
3. Nombra el certificado (ej: "KodiPlay")

## 🚀 Uso

### Iniciar KodiPlay

```bash
kodiplay
# O manualmente:
cd ~/kodiplay && python kodi_android.py
```

### Abrir la interfaz web

En tu navegador (Chrome, Firefox, etc.) abre:
```
http://TU_IP_ANDROID:5000
```

La IP se muestra en Termux al iniciar la app.

### Flujo de uso

1. **Conectar Kodi:** Ingresa la IP de tu Kodi (ej: `192.168.1.100:8080`)
2. **Iniciar Interceptor:** Presiona "INICIAR"
3. **Cargar película:** Abre tu navegador y ve a la página de la película
4. **Enviar a Kodi:** Cuando el video cargue, presiona "ENVIAR A KODI"
5. **Detener:** Presiona "DETENER" cuando termines

## 🎨 Widget Flotante

KodiPlay incluye un widget flotante que aparece como notificación persistente:

```bash
# Iniciar widget flotante
python float_widget.py 192.168.1.100
```

El widget muestra:
- Estado del interceptor
- Botón para enviar a Kodi
- Botón para detener

## 📋 Archivos del Proyecto

| Archivo | Descripción |
|---------|-------------|
| `kodi_android.py` | GUI web principal |
| `float_widget.py` | Widget flotante |
| `install.sh` | Script de instalación |
| `README.md` | Esta documentación |

## ⚙️ Configuración

### Puertos utilizados

| Puerto | Servicio |
|--------|----------|
| 5000 | GUI Web |
| 8082 | mitmproxy |
| 8888 | Proxy local |

### Variables de configuración

Edita `~/kodiplay/stream_interceptor/config.py`:

```python
KODI_IP = "192.168.1.100"  # IP de tu Kodi
KODI_PORT = 8080           # Puerto de Kodi
LOCAL_PROXY_PORT = 8888    # Puerto del proxy local
MITMPROXY_PORT = 8082      # Puerto de mitmproxy
```

## 🔧 Solución de Problemas

### "No se puede conectar a Kodi"

1. Verifica que Kodi esté ejecutándose
2. Verifica la IP y puerto
3. Asegúrate de que "Allow remote control" esté activado en Kodi

### "El interceptor no captura nada"

1. Verifica que el certificado HTTPS esté instalado
2. Verifica que el proxy del sistema esté configurado
3. Algunos sitios usan certificados pinning (no se pueden interceptar)

### "Error al instalar mitmproxy"

```bash
# Intenta con una versión específica
pip install mitmproxy==10.1.6
```

### Termux se cierra solo

1. Desactiva "Battery optimization" para Termux
2. Settings → Battery → Unrestricted para Termux

## 🆚 Comparación: APK vs Termux

| Característica | APK Nativa | Termux |
|----------------|------------|--------|
| Facilidad de uso | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Instalación | Simple | Manual |
| Actualizaciones | Play Store | Git pull |
| Acceso sistema | Limitado | Completo |
| GUI flotante | Nativa | Notificación |
| Rendimiento | Óptimo | Bueno |

## 📝 Notas Importantes

1. **No uses la Play Store:** Las versiones de Termux en Play Store están desactualizadas
2. **Batería:** Desactiva la optimización de batería para Termux
3. **HTTPS:** Sin el certificado, solo podrás interceptar HTTP
4. **Kodi:** Asegúrate de activar "Allow remote control via HTTP" en Kodi

## 🤝 Alternativas para APK Nativa

Si necesitas una APK nativa con GUI flotante real, considera:

1. **Flutter + Python backend**
   - Flutter para GUI nativa
   - Python ejecutándose en background
   - Comunicación via HTTP/WebSocket

2. **Kivy + Buildozer**
   - Requiere reescribir la GUI
   - mitmproxy puede tener problemas
   - Mucho trabajo de adaptación

3. **React Native + Termux**
   - React Native para GUI
   - Termux como servicio background
   - Comunicación via Intent

La opción Termux es la más práctica y funcional actualmente.
