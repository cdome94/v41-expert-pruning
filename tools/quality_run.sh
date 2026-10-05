#!/usr/bin/env bash
# Qualità di un GGUF: perplexity teacher-forced sui testi held-out + NLL sulle continuazioni ufficiali V4.1.
# Uso: quality_run.sh MODEL TAG   -> quality/TAG_ppl_<nome>.txt, quality/TAG_scores.tsv, quality/TAG_scores.log
set -uo pipefail
MODEL=$1; TAG=$2
P=/home/utente/ds4-engine/v4.1-flash/pruning; ENG=/home/utente/ds4-engine
CTX="${QCTX:-4096}"; NTOK="${QNTOK:-1200}"
for f in "$P"/heldout/*.txt; do
    n=$(basename "$f" .txt); out="$P/quality/${TAG}_ppl_${n}.txt"
    if grep -q '^tokens=' "$out" 2>/dev/null; then echo "skip $out"; continue; fi
    echo "[$(date '+%F %T')] perplexity $TAG $n"
    ( cd "$ENG" && ./ds4 --cuda -m "$MODEL" --ssd-streaming --ctx "$CTX" --perplexity-file "$f" -n "$NTOK" ) > "$out.tmp" 2> "$P/quality/${TAG}_ppl_${n}.log"
    grep '^tokens=' "$out.tmp" > "$out" && rm -f "$out.tmp" || echo "PPL FAILED $n (see log)"
done
out="$P/quality/${TAG}_scores.tsv"
if [ ! -s "$out" ]; then
    echo "[$(date '+%F %T')] score_official $TAG"
    ( cd "$ENG" && ./gguf-tools/quality-testing/score_official "$MODEL" \
        gguf-tools/quality-testing/deepseek-v4.1-flash-20260910/manifest.tsv "$out" "$CTX" \
        --ssd-streaming --max-cases 5 ) > "$P/quality/${TAG}_scores.log" 2>&1 || echo "SCORE FAILED (see log)"
fi
echo "[$(date '+%F %T')] quality $TAG done"
