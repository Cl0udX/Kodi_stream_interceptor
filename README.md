mitmweb --mode regular --listen-port 8082 --web-port 8083


mitmdump -s ~/Documents/Kodi/stream_interceptor/main.py --listen-port 8082 --quiet

pkill -f mitmdump
lsof -ti:8888 | xargs kill -9 2>/dev/null
lsof -ti:8082 | xargs kill -9 2>/dev/null
