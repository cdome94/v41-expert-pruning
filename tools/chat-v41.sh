#!/usr/bin/env bash
# Chat interattiva con DeepSeek V4.1 Flash Q2 (potato al 55%, 8546 expert vivi) sul DGX Spark.
#
#   ./chat-v41.sh              avvia (o riusa) il server, riscalda la cache, apre la chat
#   ./chat-v41.sh --no-warmup  salta il riscaldamento (le prime risposte saranno lente)
#   ./chat-v41.sh --think      ragionamento attivo di default (in chat: /think on|off)
#   ./chat-v41.sh --stop       ferma il server
#
# Il server resta attivo dopo l'uscita dalla chat (la cache calda vale ~80 GiB di letture),
# fermalo con --stop quando hai finito. Log: ~/ds4-server-v41-pruned.log
set -u
ENG=/home/utente/ds4-engine
MODEL=/home/utente/ds4-engine/v4.1-flash/DeepSeek-V4.1-Flash-Q2.gguf
CLIENT=/home/utente/lexar_backup/ds4/ds4-chat.py
PORT="${PORT:-8011}"; CTX="${CTX:-32768}"; CACHE="${CACHE:-8700}"
LOG=/home/utente/ds4-server-v41-pruned.log
URL="http://127.0.0.1:$PORT"
WARMUP=1; THINK=""
for a in "$@"; do
  case "$a" in
    --no-warmup) WARMUP=0 ;;
    --think) THINK="--think" ;;
    --stop) pid=$(pgrep -x ds4-server); [ -n "$pid" ] && { echo "fermo ds4-server (pid $pid)"; kill -TERM $pid; } || echo "nessun server attivo"; exit 0 ;;
    *) echo "opzione sconosciuta: $a"; exit 1 ;;
  esac
done

up(){ curl -s --max-time 3 "$URL/v1/models" >/dev/null; }

if up; then
  echo "server già attivo su $URL"
else
  if pgrep -x 'ds4-server|ds4|score_official' >/dev/null; then
    echo "c'è già un processo ds4 sulla GPU:"; pgrep -ax 'ds4-server|ds4|score_official' | cut -c1-120; exit 1
  fi
  /home/utente/ds4-engine/v4.1-flash/pruning/serve-v41.sh || exit 1
fi

if [ "$WARMUP" = 1 ]; then
  echo "riscaldamento cache (20 richieste brevi, ~4 minuti; poi il modello è tutto residente)..."
  python3 - "$URL" <<'PY'
import json, sys, time, urllib.request
url = sys.argv[1]
reqs = [json.loads(l) for l in open('/home/utente/ds4-engine/v4.1-flash/pruning/bench_corpus.jsonl')][:20]
t0 = time.time()
for i, r in enumerate(reqs, 1):
    body = {"model": "deepseek-v4.1-flash", "messages": r["messages"], "max_tokens": 96, "temperature": 0, "think": False}
    t = time.time()
    try:
        js = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/v1/chat/completions",
             data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=600).read())
        n = js.get("usage", {}).get("completion_tokens", 0)
        print(f"  {i:2d}/20  {n/(time.time()-t):5.1f} t/s", flush=True)
    except Exception as e:
        print(f"  {i:2d}/20  errore: {e}", flush=True)
print(f"riscaldamento finito in {time.time()-t0:.0f}s")
PY
fi

echo
echo "Chat pronta. Comandi: /think on|off, /reset, /quit. Modello potato sul dominio italiano/cyber/codice."
exec python3 "$CLIENT" --url "$URL" --model deepseek-v4.1-flash $THINK \
    --system "Sei un assistente tecnico. Rispondi in italiano in modo preciso e conciso."
