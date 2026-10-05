#!/usr/bin/env bash
# ds4-server (patched ~/ds4-engine build) on V4.1 Flash Q4, SSD streaming, with the
# routed-expert hit profiler enabled. Output CSV: $HITS (rewritten atomically
# every $EVERY router rows and at shutdown).
set -euo pipefail
BIN_DIR=/home/utente/ds4-engine
MODEL="${DS4_MODEL:-/home/utente/ds4-engine/v4.1-flash/DeepSeek-V4.1-Flash-Q4.gguf}"
HITS="${HITS-/home/utente/ds4-engine/v4.1-flash/pruning/profile_hits.csv}"   # HITS="" disattiva il profiler
EVERY="${EVERY:-256}"
CTX="${DS4_CTX:-4096}"
PORT="${DS4_PORT:-8011}"
LOG="${LOG:-/home/utente/ds4-engine/v4.1-flash/pruning/profile_server.log}"
cd "$BIN_DIR"
if [ -n "${HITS}" ]; then export DS4_EXPERT_HITS_OUT="$HITS" DS4_EXPERT_HITS_EVERY="$EVERY"; fi
exec ./ds4-server --cuda -m "$MODEL" --ssd-streaming --ctx "$CTX" \
    --host 127.0.0.1 --port "$PORT" "$@" >>"$LOG" 2>&1
