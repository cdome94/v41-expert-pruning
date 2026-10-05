#!/usr/bin/env bash
# Orchestratore weekend: Fase 1 sul Q4 -> (flag) cancellazione Q4 -> attesa Q2 -> Fase 3 sul Q2 -> REPORT.md
# Idempotente: ogni passo lascia un marker in state/; rilanciare riprende dal primo passo mancante.
# Sicurezza: se il processo muore con un modello patchato, il trap ripristina i bias originali.
set -uo pipefail
P=/home/utente/ds4-engine/v4.1-flash/pruning; ENG=/home/utente/ds4-engine; VF=/home/utente/ds4-engine/v4.1-flash
Q4=$VF/DeepSeek-V4.1-Flash-Q4.gguf; Q2=$VF/DeepSeek-V4.1-Flash-Q2.gguf
Q4ORIG=$VF/v41q4_router_bias_orig.npy; Q2ORIG=$VF/v41q2_router_bias_orig.npy
PORT=8011; LOGF=$P/pipeline.log
cd "$P"
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOGF"; }
done_(){ [ -f "state/$1" ]; }
mark(){ touch "state/$1"; log "== step $1 done"; }
restore_if_patched(){
    for m in q4 q2; do
        if [ -f "state/patched_$m" ]; then
            local model orig; if [ $m = q4 ]; then model=$Q4; orig=$Q4ORIG; else model=$Q2; orig=$Q2ORIG; fi
            log "TRAP: ripristino bias $m"; python3 router_bias_tool.py restore "$model" "$orig" >>"$LOGF" 2>&1 && rm -f "state/patched_$m"
        fi
    done
}
trap restore_if_patched EXIT
mem_avail_gib(){ awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }
wait_gpu_free(){ # nessun altro processo ds4 sulla GPU e memoria sufficiente.
    # Autorizzazione utente (2026-10-02): nel weekend posso TERMINARE processi se serve memoria; MAI cancellare file.
    local n=0
    while pgrep -x 'ds4-server|ds4|score_official|ds4-eval' >/dev/null; do
        n=$((n+1)); log "attendo processi ds4 esistenti: $(pgrep -ax 'ds4-server|ds4|score_official|ds4-eval' | head -2 | cut -c1-120)"
        if [ $n -ge 10 ]; then log "KILL (autorizzato) processi ds4 estranei dopo 10 min"; pkill -TERM -x 'ds4-server|ds4|score_official|ds4-eval'; sleep 20; pkill -KILL -x 'ds4-server|ds4|score_official|ds4-eval' 2>/dev/null; sleep 5; fi
        sleep 60
    done
    # memoria: servono ~100 GiB disponibili per modello residente + cache
    n=0
    while [ "$(mem_avail_gib)" -lt 100 ]; do
        n=$((n+1)); log "memoria disponibile $(mem_avail_gib) GiB < 100; top RSS: $(ps -eo pid,rss,comm --sort=-rss | awk 'NR>1 && NR<4 {printf "%s(%s,%dGiB) ", $3,$1,$2/1048576}')"
        if [ $n -ge 3 ]; then
            # termina il processo con RSS maggiore se > 20 GiB e non e' un processo di sistema/di questa pipeline
            local victim; victim=$(ps -eo pid,rss,comm --sort=-rss | awk 'NR>1 && $2>20971520 && $3!~/^(systemd|sshd|init|kthreadd|bash|curl|sleep|python3)$/ {print $1; exit}')
            if [ -n "$victim" ]; then log "KILL (autorizzato) pid $victim $(ps -o comm= -p $victim) per liberare memoria"; kill -TERM "$victim"; sleep 30; kill -KILL "$victim" 2>/dev/null; sleep 10; n=0
            else log "nessun candidato > 20 GiB da terminare: continuo ad attendere"; fi
        fi
        sleep 60
    done
}
stop_server(){
    local pid; pid=$(pgrep -f "ds4-server .*--port $PORT" | head -1); [ -z "$pid" ] && return 0
    log "stop ds4-server pid $pid"; kill -TERM "$pid"
    for i in $(seq 1 120); do kill -0 "$pid" 2>/dev/null || { log "server fermato"; return 0; }; sleep 5; done
    log "server non si ferma, SIGKILL"; kill -KILL "$pid"; sleep 5
}
start_server(){ # $1 model $2 hits csv $3 log
    wait_gpu_free
    log "start ds4-server $1 -> hits $2"
    ( DS4_MODEL="$1" HITS="$2" LOG="$3" EVERY=256 nohup ./run_profile_server.sh >/dev/null 2>&1 & )
    for i in $(seq 1 360); do curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" >/dev/null && { log "server pronto"; return 0; }; sleep 5; done
    log "ERRORE: server non pronto dopo 30 min"; tail -5 "$3" >>"$LOGF"; return 1
}
slots_from_log(){ grep -o 'CUDA SSD expert cache: [0-9]* slots' "$1" | tail -1 | grep -o '[0-9]*' ; }
run_phase(){ # $1 tag(q4|q2) $2 model $3 orig.npy $4 profile hits csv $5 profile server log  $6 skip_profile(0/1)
    local T=$1 M=$2 ORIG=$3 HITS=$4 SLOG=$5 SKIP=$6
    # profilo
    if [ "$SKIP" = 0 ] && ! done_ "${T}_profile"; then
        start_server "$M" "$HITS" "$SLOG" || return 1
        python3 run_corpus_client.py profile_corpus_ordered.jsonl "profile_outputs_${T}_unpruned.jsonl" --port $PORT --resume >> "client_${T}.log" 2>&1
        stop_server; mark "${T}_profile"
    fi
    local SLOTS; SLOTS=$(slots_from_log "$SLOG"); [ -z "$SLOTS" ] && { log "ERRORE: slot cache non trovati in $SLOG"; return 1; }
    log "$T: budget cache = $SLOTS slot"
    python3 analyze_hits.py "$HITS" --budget "$SLOTS" --alloc-out "alloc_${T}_${SLOTS}.json" > "analysis_${T}.txt" 2>&1
    python3 analyze_hits.py "$HITS" --budget $(( SLOTS * 13 / 10 )) --alloc-out "alloc_${T}_x13.json" >/dev/null 2>&1
    # qualità baseline
    if ! done_ "${T}_quality_base"; then wait_gpu_free; ./quality_run.sh "$M" "${T}_unpruned" >>"$LOGF" 2>&1; mark "${T}_quality_base"; fi
    # patch + bench + qualità
    if ! done_ "${T}_pruned_done"; then
        [ -f "$ORIG" ] || python3 router_bias_tool.py dump "$M" "$ORIG" >>"$LOGF" 2>&1
        python3 router_bias_tool.py apply "$M" "$HITS" --alloc "alloc_${T}_${SLOTS}.json" --orig "$ORIG" >>"$LOGF" 2>&1 || { log "ERRORE apply bias"; return 1; }
        touch "state/patched_$T"; python3 router_bias_tool.py show "$M" | head -3 >>"$LOGF"
        if ! done_ "${T}_bench"; then
            # bench di velocita' SENZA profiler (il profiler sincronizza la GPU 40 volte per token)
            start_server "$M" "" "$P/pruned_${T}_server_clean.log" || return 1
            python3 run_corpus_client.py bench_corpus.jsonl "bench_outputs_${T}_pruned.jsonl" --port $PORT >> "client_bench_${T}.log" 2>&1
            stop_server; python3 bench_from_log.py "pruned_${T}_server_clean.log" --skip 20 > "bench_${T}_pruned.txt" 2>&1
            # passata CON profiler sulle prime 40 richieste del profilo: confronto risposte prima/dopo + verifica zero chiamate a expert esclusi
            head -40 profile_corpus_ordered.jsonl > "bench_profile40.jsonl"
            [ -f "pruned_${T}_hits.csv" ] && mv -f "pruned_${T}_hits.csv" "pruned_${T}_hits.prev.csv"; start_server "$M" "$P/pruned_${T}_hits.csv" "$P/pruned_${T}_server.log" || return 1
            python3 run_corpus_client.py bench_profile40.jsonl "profile40_outputs_${T}_pruned.jsonl" --port $PORT >> "client_bench_${T}.log" 2>&1
            stop_server; mark "${T}_bench"
        fi
        if ! done_ "${T}_quality_pruned"; then wait_gpu_free; ./quality_run.sh "$M" "${T}_pruned" >>"$LOGF" 2>&1; mark "${T}_quality_pruned"; fi
        python3 router_bias_tool.py restore "$M" "$ORIG" >>"$LOGF" 2>&1 && rm -f "state/patched_$T"
        mark "${T}_pruned_done"
    fi
    # secondo punto della curva qualità: budget x1.3 (solo qualità, non residente)
    if [ "$T" = q2 ] && ! done_ "${T}_quality_x13"; then
        python3 router_bias_tool.py apply "$M" "$HITS" --alloc "alloc_${T}_x13.json" --orig "$ORIG" >>"$LOGF" 2>&1 && touch "state/patched_$T"
        wait_gpu_free; ./quality_run.sh "$M" "${T}_pruned_x13" >>"$LOGF" 2>&1
        python3 router_bias_tool.py restore "$M" "$ORIG" >>"$LOGF" 2>&1 && rm -f "state/patched_$T"
        mark "${T}_quality_x13"
    fi
    python3 make_report.py > REPORT.md 2>>"$LOGF"; log "REPORT.md aggiornato ($T)"
}

log "===== pipeline start ====="
# 0. attendi fine del profilo Q4 in corso (client lanciato a mano) e ferma il server
if ! done_ q4_profile; then
    while pgrep -f '^python3 run_corpus_client.py profile_corpus_ordered' >/dev/null; do sleep 60; done
    log "profilo Q4: client terminato ($(grep -c '^\[' client.log) richieste)"; stop_server; mark q4_profile
fi
# 1. Fase 1 sul Q4
run_phase q4 "$Q4" "$Q4ORIG" "$P/profile_hits.csv" "$P/profile_server.log" 1 || { log "Fase 1 fallita"; }
# 1b. bench pulito (senza profiler) del Q4 potato, se il bench e' stato fatto col profiler attivo
if [ -f "$Q4" ] && done_ q4_pruned_done && ! done_ q4_bench_clean; then
    python3 router_bias_tool.py apply "$Q4" "$P/profile_hits.csv" --alloc alloc_q4_3889.json --orig "$Q4ORIG" >>"$LOGF" 2>&1 && touch state/patched_q4
    start_server "$Q4" "" "$P/pruned_q4_server_clean.log" && {
        python3 run_corpus_client.py bench_corpus.jsonl bench_outputs_q4_pruned_clean.jsonl --port $PORT >> client_bench_q4.log 2>&1
        stop_server; python3 bench_from_log.py pruned_q4_server_clean.log --skip 20 > bench_q4_pruned.txt 2>&1; }
    python3 router_bias_tool.py restore "$Q4" "$Q4ORIG" >>"$LOGF" 2>&1 && rm -f state/patched_q4
    mark q4_bench_clean; python3 make_report.py > REPORT.md 2>>"$LOGF"
fi
# 2. cancellazione Q4 (solo con flag esplicito) per far posto al Q2
if [ -f "$Q4" ] && ! done_ q4_deleted; then
    [ -f state/patched_q4 ] && { log "Q4 ancora patchato: non cancello"; exit 1; }
    while [ ! -f "$P/ALLOW_DELETE_Q4" ]; do log "attendo il flag ALLOW_DELETE_Q4 per cancellare il Q4 (download Q2 in pausa quando lo spazio finisce)"; sleep 600; done
    done_ q4_pruned_done || { log "Fase 1 non completata: non cancello il Q4"; exit 1; }
    log "cancello $Q4"; rm -f "$Q4"; sync; mark q4_deleted; log "spazio libero: $(df -h "$VF" | awk 'NR==2{print $4}')"
fi
# 3. attendi il Q2 completo e verificato
while :; do
    if [ -s "$Q2" ] && grep -q "DeepSeek-V4.1-Flash-Q2.gguf: OK" "$VF/download-v4.1-q2.log" 2>/dev/null; then log "Q2 completo e SHA OK"; break; fi
    if grep -q "FAILED\|ERRORE" "$VF/download-v4.1-q2.log" 2>/dev/null; then log "ERRORE download Q2: $(grep 'FAILED\|ERRORE' "$VF/download-v4.1-q2.log" | tail -1)"; exit 1; fi
    pgrep -f download-v4.1-flash-q2.sh >/dev/null || { log "download Q2 non attivo: lo rilancio (cap 60 Mbit)"; ( cd "$VF" && RATE=7500000 nohup ./download-v4.1-flash-q2.sh >> download-v4.1-q2.nohup 2>&1 & ); }
    sleep 300
done
# 4. Fase 3 sul Q2: profilo, baseline, pruning al budget della cache, bench, qualità, punto x1.3
run_phase q2 "$Q2" "$Q2ORIG" "$P/profile_q2_hits.csv" "$P/profile_q2_server.log" 0 || { log "Fase 3 fallita"; exit 1; }
log "===== pipeline end ====="
