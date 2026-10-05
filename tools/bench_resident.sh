#!/usr/bin/env bash
# Bench del Q2 (potato) con il server corrente. Uso: bench_resident.sh TAG [extra ds4-server args...]
# Variabili d'ambiente extra (es. DS4_CUDA_V41_QUEUE_LAYERS=1) vengono ereditate dal server.
set -u
TAG=$1; shift
P=/home/utente/ds4-engine/v4.1-flash/pruning; MODEL=/home/utente/ds4-engine/v4.1-flash/DeepSeek-V4.1-Flash-Q2.gguf
LOG=$P/${TAG}_server.log
pgrep -x 'ds4-server|ds4' >/dev/null && { echo "GPU busy"; exit 1; }
rm -f "$LOG"
( DS4_MODEL="$MODEL" HITS="" LOG="$LOG" nohup $P/run_profile_server.sh "$@" >/dev/null 2>&1 & )
for i in $(seq 1 120); do curl -s --max-time 3 http://127.0.0.1:8011/v1/models >/dev/null && break; sleep 5; done
curl -s --max-time 3 http://127.0.0.1:8011/v1/models >/dev/null || { echo "server failed:"; tail -5 "$LOG"; exit 1; }
python3 $P/run_corpus_client.py $P/bench_corpus.jsonl $P/bench_outputs_${TAG}.jsonl --port 8011 > $P/client_${TAG}.log 2>&1
pid=$(pgrep -x ds4-server); kill -TERM $pid; for i in $(seq 1 60); do kill -0 $pid 2>/dev/null || break; sleep 2; done
echo "=== $TAG: pass 2 (misurata)"; python3 $P/bench_from_log.py "$LOG" --skip 20 | sed -n 2,3p
echo "=== $TAG: tutte le 40"; python3 $P/bench_from_log.py "$LOG" | sed -n 2,3p
echo "=== log fast path:"; grep -i 'resident fast path\|unavailable\|slots,' "$LOG" | head -6 | cut -c1-160
echo "=== confronto con sabato (potato, path lento):"; python3 $P/compare_outputs.py $P/bench_outputs_q2_pruned.jsonl $P/bench_outputs_${TAG}.jsonl | head -6
