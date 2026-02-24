#!/bin/bash

# ─── KodiPlay - Envía cualquier video a Kodi ─────────────────────────────────
# Dependencias: yt-dlp, streamlink, python3
# Uso: play [opciones] "URL"

# ─── Configuración por defecto ───────────────────────────────────────────────
DEFAULT_KODI_IP="127.0.0.1"
DEFAULT_KODI_PORT="8080"

# ─── Ayuda ───────────────────────────────────────────────────────────────────
usage() {
  echo ""
  echo "Uso: play [opciones] \"URL\""
  echo ""
  echo "Opciones:"
  echo "  -q [baja|media|alta|original]   Calidad base (default: media)"
  echo "  -h IP                           IP del host Kodi (default: $DEFAULT_KODI_IP)"
  echo "  -p PUERTO                       Puerto Kodi (default: $DEFAULT_KODI_PORT)"
  echo "  -s                              Siempre pedir selección de formato"
  echo ""
  echo "Ejemplos:"
  echo "  play \"https://youtube.com/...\""
  echo "  play -s \"https://youtube.com/...\"   # fuerza selección"
  echo "  play -q alta \"https://youtube.com/...\""
  echo ""
  exit 1
}

# ─── Valores por defecto ──────────────────────────────────────────────────────
KODI_IP="$DEFAULT_KODI_IP"
KODI_PORT="$DEFAULT_KODI_PORT"
QUALITY="media"
FORCE_SELECT=false

# ─── Parsear argumentos ───────────────────────────────────────────────────────
while getopts "q:h:p:s" opt; do
  case $opt in
    q) QUALITY="$OPTARG" ;;
    h) KODI_IP="$OPTARG" ;;
    p) KODI_PORT="$OPTARG" ;;
    s) FORCE_SELECT=true ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))

LINK="$1"
if [ -z "$LINK" ]; then usage; fi

# ─── Formato base según calidad ───────────────────────────────────────────────
case $QUALITY in
  baja)     HEIGHT=480  ; STREAMLINK_Q="480p,360p,worst" ;;
  media)    HEIGHT=720  ; STREAMLINK_Q="720p,480p,best"  ;;
  alta)     HEIGHT=1080 ; STREAMLINK_Q="1080p,720p,best" ;;
  original) HEIGHT=9999 ; STREAMLINK_Q="best"            ;;
  *)
    echo "❌ Calidad inválida: $QUALITY. Usa: baja, media, alta, original"
    exit 1
    ;;
esac

# ─── Enviar a Kodi ────────────────────────────────────────────────────────────
send_to_kodi() {
  local URL="$1"
  RESPONSE=$(python3 -c "
import json, urllib.request
payload = json.dumps({'jsonrpc':'2.0','method':'Player.Open','params':{'item':{'file':'$URL'}},'id':1})
req = urllib.request.Request('http://$KODI_IP:$KODI_PORT/jsonrpc', payload.encode(), {'Content-Type':'application/json'})
try:
    print(urllib.request.urlopen(req, timeout=5).read().decode())
except Exception as e:
    print('ERROR:' + str(e))
")
  if echo "$RESPONSE" | grep -q '"result"'; then
    return 0
  else
    echo "❌ Error conectando a Kodi en $KODI_IP:$KODI_PORT"
    echo "   $RESPONSE"
    return 1
  fi
}

# ─── Selección interactiva de formatos ───────────────────────────────────────
select_format() {
  local LINK="$1"
  echo "🔍 Analizando formatos disponibles..." >&2

  # Obtener JSON de formatos
  FORMATS_JSON=$(yt-dlp -J "$LINK" 2>/dev/null)
  if [ -z "$FORMATS_JSON" ]; then
    echo "❌ No se pudieron obtener los formatos" >&2
    return 1
  fi

  # Extraer y mostrar formatos con python
  python3 - <<PYEOF
import json, sys

data = json.loads('''$(echo "$FORMATS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d))" 2>/dev/null)''')

formats = data.get("formats", [])
if not formats:
    print("NO_FORMATS")
    sys.exit(1)

# Filtrar solo formatos con video o que sean completos
useful = []
for f in formats:
    fid     = f.get("format_id", "?")
    ext     = f.get("ext", "?")
    height  = f.get("height")
    width   = f.get("width")
    vcodec  = f.get("vcodec", "none")
    acodec  = f.get("acodec", "none")
    lang    = f.get("language") or f.get("language_preference") or ""
    note    = f.get("format_note", "")
    tbr     = f.get("tbr") or f.get("abr") or 0
    fps     = f.get("fps")

    has_video = vcodec and vcodec != "none"
    has_audio = acodec and acodec != "none"

    if not has_video:
        continue

    res = f"{height}p" if height else (f"{width}x?" if width else "?")
    fps_str = f" {fps}fps" if fps else ""
    audio_str = "🔊" if has_audio else "🔇"
    lang_str = f" [{lang}]" if lang else ""
    note_str = f" ({note})" if note else ""
    tbr_str = f" ~{int(tbr)}kbps" if tbr else ""

    label = f"{audio_str} {res}{fps_str} {ext}{lang_str}{note_str}{tbr_str}  [id:{fid}]"
    useful.append((fid, label, has_audio))

if not useful:
    print("NO_FORMATS")
    sys.exit(1)

print(f"COUNT:{len(useful)}")
for i, (fid, label, _) in enumerate(useful):
    print(f"  {i+1}) {label}")
PYEOF

  COUNT=$(yt-dlp -J "$LINK" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
fmts=[f for f in d.get('formats',[]) if f.get('vcodec','none') != 'none']
print(len(fmts))
" 2>/dev/null)

  if [ -z "$COUNT" ] || [ "$COUNT" -le 1 ]; then
    # Solo hay un formato, usarlo directamente
    echo "AUTO"
    return 0
  fi

  echo "" >&2
  printf "Selecciona un formato (1-$COUNT) o Enter para automático: " >&2
  read CHOICE </dev/tty

  if [ -z "$CHOICE" ]; then
    echo "AUTO"
  else
    # Devolver el format_id seleccionado
    yt-dlp -J "$LINK" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
fmts=[f for f in d.get('formats',[]) if f.get('vcodec','none') != 'none']
idx=$CHOICE - 1
if 0 <= idx < len(fmts):
    print(fmts[idx]['format_id'])
else:
    print('AUTO')
"
  fi
}

# ─── Extraer URL final ────────────────────────────────────────────────────────
extract_url() {
  local LINK="$1"

  # Stream directo m3u8/m3u
  if [[ "$LINK" == *.m3u8* ]] || [[ "$LINK" == *.m3u* ]]; then
    echo "📡 Stream directo detectado..." >&2
    echo "$LINK"
    return
  fi

  # Twitch → streamlink sin ads
  if [[ "$LINK" == *twitch.tv* ]]; then
    echo "🎮 Twitch detectado, usando streamlink (sin ads)..." >&2

    # Obtener calidades disponibles
    AVAILABLE=$(streamlink "$LINK" 2>/dev/null | grep "Available streams:" | sed 's/Available streams: //')
    if [ -n "$AVAILABLE" ] && $FORCE_SELECT; then
      echo "" >&2
      echo "📡 Calidades disponibles: $AVAILABLE" >&2
      printf "Selecciona calidad (o Enter para '$STREAMLINK_Q'): " >&2
      read CHOSEN_Q </dev/tty
      [ -z "$CHOSEN_Q" ] && CHOSEN_Q="$STREAMLINK_Q"
    else
      CHOSEN_Q="$STREAMLINK_Q"
    fi

    streamlink --stream-url \
      --twitch-disable-ads \
      --twitch-low-latency \
      "$LINK" "$CHOSEN_Q" 2>/dev/null | head -1
    return
  fi

  # yt-dlp: pedir selección si hay múltiples formatos o si se fuerza
  if $FORCE_SELECT; then
    FORMAT_ID=$(select_format "$LINK")
  else
    FORMAT_ID="AUTO"
  fi

  if [ "$FORMAT_ID" = "AUTO" ] || [ -z "$FORMAT_ID" ]; then
    echo "🔍 Extrayendo mejor formato [calidad: $QUALITY]..." >&2
    FORMAT="best[ext=mp4][height<=$HEIGHT]/best[height<=$HEIGHT]"
    yt-dlp -g -f "$FORMAT" "$LINK" 2>/dev/null | head -1
  else
    echo "🔍 Extrayendo formato seleccionado [$FORMAT_ID]..." >&2
    yt-dlp -g -f "$FORMAT_ID" "$LINK" 2>/dev/null | head -1
  fi
}

# ─── Main ─────────────────────────────────────────────────────────────────────
URL=$(extract_url "$LINK")

if [ -z "$URL" ]; then
  echo "❌ No se pudo extraer el video. El sitio puede no estar soportado."
  exit 1
fi

echo "▶️  Enviando a $KODI_IP:$KODI_PORT..."
send_to_kodi "$URL" && echo "✅ Reproduciendo en TV!"

# mitmweb --mode regular --listen-port 8082 --web-port 8083