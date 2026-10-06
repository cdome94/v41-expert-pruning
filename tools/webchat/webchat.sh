#!/usr/bin/env bash
# Web chat con login per il modello V4.1 sul Spark.
#   ./webchat.sh start|stop|status|restart     ./webchat.sh passwd UTENTE   (cambia/crea password)
# Porta 8080 (PORT=...), log ~/ds4-webchat.log. Richiede il server del modello attivo (~/serve-v41.sh).
set -u
APP=/home/utente/ds4-engine/v4.1-flash/pruning/webchat/app.py; PORT="${PORT:-8080}"; LOG=/home/utente/ds4-webchat.log
case "${1:-status}" in
  start) pgrep -f "app.py serve" >/dev/null && { echo "già attiva"; exit 0; }
         ( exec setsid nohup python3 "$APP" serve --port "$PORT" --bind 0.0.0.0 ) >>"$LOG" 2>&1 </dev/null & disown
         sleep 1; curl -s --max-time 3 "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "webchat attiva: http://$(hostname -I | awk '{print $1}'):$PORT" || { echo "non parte, vedi $LOG"; tail -3 "$LOG"; } ;;
  stop) pkill -f "app.py serve" && echo "fermata" || echo "non attiva" ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  status) pgrep -f "app.py serve" >/dev/null && echo "attiva su porta $PORT" || echo "non attiva"; tail -3 "$LOG" 2>/dev/null ;;
  passwd) shift; python3 "$APP" passwd "$@" ;;
  *) echo "uso: $0 start|stop|status|restart|passwd UTENTE [--generate]"; exit 1 ;;
esac
