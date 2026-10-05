#!/usr/bin/env bash
# Server OpenAI-compatible di DeepSeek V4.1 Flash Q2 potato (fast path residente) per client esterni
# (OpenCode, Codex, curl) dal LAN. Nessuna autenticazione: tenere il server dentro la rete privata
# o usare un tunnel SSH (ssh -L 8011:127.0.0.1:8011 utente@<spark>) invece di esporre la porta.
#
#   ./serve-v41.sh            avvia (ascolta su 0.0.0.0:8011, ctx 32768, KV su disco)
#   ./serve-v41.sh --status   mostra stato, piano memoria, velocità delle ultime richieste
#   ./serve-v41.sh --warmup   riscalda la cache con 20 richieste brevi (~4 min a freddo)
#   ./serve-v41.sh --stop     ferma il server
# Variabili: PORT (8011), CTX (32768), CACHE (8700 slot), HOST (0.0.0.0)
set -u
ENG=/home/utente/ds4-engine
MODEL=/home/utente/ds4-engine/v4.1-flash/DeepSeek-V4.1-Flash-Q2.gguf
PORT="${PORT:-8011}"; CTX="${CTX:-32768}"; CACHE="${CACHE:-8700}"; HOST="${HOST:-0.0.0.0}"
KVDIR=/home/utente/.ds4/server-kv
LOG=/home/utente/ds4-server-v41-pruned.log
URL="http://127.0.0.1:$PORT"
up(){ curl -s --max-time 3 "$URL/v1/models" >/dev/null; }
case "${1:-}" in
  --stop) pid=$(pgrep -x ds4-server); [ -n "$pid" ] && { echo "fermo ds4-server (pid $pid)"; kill -TERM $pid; } || echo "nessun server attivo"; exit 0 ;;
  --status)
    if up; then echo "server attivo su $(hostname -I | awk '{print $1}'):$PORT"; else echo "server NON attivo"; fi
    grep -o 'CUDA SSD expert cache: [0-9]* slots, [0-9.]* GiB' "$LOG" 2>/dev/null | tail -1
    grep 'planned' "$LOG" 2>/dev/null | tail -1 | cut -c1-200
    grep 'fast path active' "$LOG" 2>/dev/null | tail -1
    python3 /home/utente/ds4-engine/v4.1-flash/pruning/bench_from_log.py "$LOG" 2>/dev/null | sed -n 2,3p
    exit 0 ;;
  --warmup)
    up || { echo "server non attivo"; exit 1; }
    python3 - "$URL" <<'PY'
import json, sys, time, urllib.request
url = sys.argv[1]
reqs = [json.loads(l) for l in open('/home/utente/ds4-engine/v4.1-flash/pruning/bench_corpus.jsonl')][:20]
for i, r in enumerate(reqs, 1):
    body = {"model": "deepseek-v4.1-flash", "messages": r["messages"], "max_tokens": 96, "temperature": 0, "think": False}
    t = time.time()
    js = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/v1/chat/completions",
         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=900).read())
    n = js.get("usage", {}).get("completion_tokens", 0)
    print(f"  {i:2d}/20  {n/(time.time()-t):5.1f} t/s", flush=True)
PY
    exit 0 ;;
  "") ;;
  *) echo "opzione sconosciuta: $1"; exit 1 ;;
esac
if up; then echo "server già attivo su $URL"; exit 0; fi
if pgrep -x 'ds4-server|ds4|score_official' >/dev/null; then
  echo "c'è già un processo ds4 sulla GPU:"; pgrep -ax 'ds4-server|ds4|score_official' | cut -c1-120; exit 1
fi
mkdir -p "$KVDIR"
echo "avvio ds4-server su $HOST:$PORT (Q2 potato, cache $CACHE slot, ctx $CTX, KV su disco in $KVDIR)..."
# server completamente staccato (nuova sessione, nessun fd ereditato): sopravvive alla chiusura della shell
( cd "$ENG" && exec env DS4_CUDA_V41_QUEUE_LAYERS=1 setsid nohup ./ds4-server --cuda -m "$MODEL" --ssd-streaming \
    --ssd-streaming-cache-experts "$CACHE" --ctx "$CTX" --host "$HOST" --port "$PORT" \
    --kv-disk-dir "$KVDIR" --kv-disk-space-mb 16384 --cors ) >>"$LOG" 2>&1 </dev/null &
disown
for i in $(seq 1 120); do up && break; sleep 3; done
up || { echo "il server non è partito, vedi $LOG:"; tail -5 "$LOG"; exit 1; }
echo "server pronto: http://$(hostname -I | awk '{print $1}'):$PORT/v1  (modello: deepseek-v4.1-flash)"
echo "consigliato ora: ./serve-v41.sh --warmup"
