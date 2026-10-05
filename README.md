# Router-bias expert pruning for DeepSeek V4.1 Flash on a single DGX Spark

Workload-conditioned expert pruning for DeepSeek V4.1 Flash GGUFs served with
[antirez/ds4](https://github.com/antirez/ds4), done **without rewriting a single
expert tensor**: the pruning mask is written into the router bias
(`blk.N.exp_probs_b.bias`, 384 floats per layer, 61 KB in a 340 GiB file), so the
GGUF stays structurally identical, every kernel constraint is untouched, and the
operation is reversible by restoring the saved biases.

Combined with ds4's SSD-streaming expert cache, this turns a model that does not
fit in 119 GiB of unified memory into one whose whole live expert set is
resident after warm-up: zero NVMe misses, decode 7.3 -> 12.7 t/s, prefill
9 -> 19 t/s on one GB10, with a quality loss that is small on the profiled
domain and large outside it. All numbers below were measured, not estimated.

> This is a **specialisation** technique. The pruned model is not an equivalent
> model: on the profiled workload (Italian prose, cyber-security, code, agent
> traffic) it loses 1-5% perplexity; on unrelated English prose it loses 70%.

## How it works

DeepSeek V4/V4.1 route with `noaux_tc`: experts are *selected* by
`score(logit) + bias[e]` but the output is *weighted* by `score` only. ds4's
CUDA kernel (`router_select_warp_topk_kernel<384>`) reads the bias straight from
the mapped file. Writing `-1e4` into `bias[e]` therefore excludes expert `e`
forever and the six selected weights renormalise by themselves. The engine does
not know anything happened.

1. **Profile** which (layer, expert) pairs the router selects on your real
   traffic (`DS4_EXPERT_HITS_OUT`, a small engine patch; see below).
2. **Allocate** a live-expert budget per layer under a global slot budget equal
   to the streaming cache size (`analyze_hits.py --budget N`): layers differ a
   lot (effective number of experts 150-250 out of 384), so the per-layer keep
   count ranges 74-122 at 25% and 176-274 at 55%.
3. **Apply** the bias mask (`router_bias_tool.py apply`), keeping the original
   biases in a `.npy` for `restore`.
4. Serve with `--ssd-streaming` and a cache sized at live experts + ~150 slots.
   After warm-up every selected expert is a cache hit.

## Measured results (DGX Spark GB10, 119 GiB, Micron 2500 NVMe)

Profile: 157 chat requests, 47.5k router rows, 11.4M expert calls (Italian
cyber/code/general, English cyber, a sample of ds4's imatrix corpus incl. code
review and agent prompts). Coverage of the top-N experts per layer (share of
expert calls served):

| live experts / layer | 25% | 50% | 58% | 67% | 83% |
|---|---|---|---|---|---|
| calls covered (mean) | 69% | 89% | 93% | 96% | 99% |
| worst layer (layer 0) | 57% | 81% | 86% | 91% | 98% |

Effective number of experts per layer: mean 188 (min 153, max 249). Only 2.8%
of experts were never selected; 48% have a share below 0.1%. The file's
load-balancing bias is uncorrelated with usage (r = -0.01).

Speed and quality (perplexity on held-out texts, teacher-forced, 1200 tokens;
NLL on 5 official DeepSeek API continuations):

| model | live experts | decode | prefill | ppl it_cyber | ppl code | ppl en_story | official NLL / top-1 |
|---|---|---|---|---|---|---|---|
| Q4_K streaming (25% cache) | 384 | 3.3 t/s | 2.4 t/s | 2.59 | 1.48 | 4.01 | 0.205 / 99% |
| Q4_K pruned 25% (resident) | 3889 | 9.5 t/s | 9.9 t/s | 3.84 (+48%) | 1.92 (+30%) | 12.85 (x3.2) | 1.553 / 71% |
| Q2 streaming (55% cache) | 384 | 7.3 t/s | 9.0 t/s | 3.12 | 1.51 | 4.27 | 0.443 / 88% |
| Q2 pruned 55% (resident, host streaming path) | 8546 | 10.3 t/s | 18.8 t/s | 3.17 (+1.4%) | 1.54 (+1.7%) | 7.31 (+71%) | 1.189 / 78% |
| Q2 pruned 55% + engine patch (resident fast path, queued layers) | 8546 | 12.7 t/s | 19.2 t/s | same | same | same | same |
| Q2 pruned 72% (not resident) | 11109 | - | - | 3.14 (+0.6%) | 1.51 (-0.1%) | 5.23 (+22%) | 1.103 / 82% |

Mechanism check: during the pruned benchmarks the profiler recorded
**0 calls to excluded experts** (4.36M and 2.54M calls). Outputs at temperature 0
are byte-identical between the host-side streaming path and the resident fast
path described below.

Full report with the exact commands: [results/REPORT_2026-10-03.md](results/REPORT_2026-10-03.md).

## Engine patch (ds4, CUDA)

`engine-patch/*.diff` against antirez/ds4 `main` (also submitted upstream):

- `DS4_EXPERT_HITS_OUT=<csv>`: routed-expert hit profiler for the V4.1 CUDA graph
  (ds4's built-in profiler is Metal-only). Counts and router-weight mass per
  (layer, expert), dumped atomically every `DS4_EXPERT_HITS_EVERY` rows.
- Resident fast path for SSD streaming: when every expert the router can still
  select in a layer is cached, selected ids are resolved to cache slots on the
  device and the per-layer host round trip (D2H read, stream drain, hash
  lookups, H2D remap) is skipped. Off by default unless the live set is fully
  resident; `DS4_CUDA_DISABLE_RESIDENT_FAST_PATH=1` disables it.
- `DS4_CUDA_V41_QUEUE_LAYERS=1`: opt-in, skips the per-layer command drain in
  the single-GPU V4.1 decode when the fast path is active.

Measured effect on the pruned Q2 (8546 live experts, 8700 cache slots): the
fast path alone leaves decode at 10.0 t/s (the per-layer drain becomes the
limiter), fast path + queued layers gives 12.7 t/s; prefill 19.2 t/s; all 40
temperature-0 completions byte-identical to the host path. The memory-bandwidth
ceiling of this configuration is around 20 t/s, so roughly 30 ms per token of
non-expert work remain to be explained.

## Tools

All scripts live in `tools/`; they were written for one machine and contain
absolute paths (`/home/utente/ds4-engine/...`) that you will want to adapt.

| script | purpose |
|---|---|
| `router_bias_tool.py` | `dump` / `apply --alloc` / `restore` / `show` the router biases in a GGUF |
| `analyze_hits.py` | coverage curve, per-layer concentration, greedy per-layer allocation for a slot budget (`--alloc-out`) |
| `build_profile_corpus.py` | builds the chat request corpus used for profiling |
| `run_profile_server.sh`, `run_corpus_client.py` | ds4-server with the profiler on; sequential client that also saves outputs |
| `bench_from_log.py` | prefill/decode t/s per request from the server log |
| `quality_run.sh` | perplexity on held-out texts + ds4's official-continuation scorer |
| `weekend_pipeline.sh` | the unattended orchestration that produced the Q2 results |

Minimal recipe:

```bash
# 1. profile (server side)
DS4_EXPERT_HITS_OUT=profile_hits.csv ./ds4-server --cuda -m MODEL.gguf --ssd-streaming --ctx 4096
# 2. allocation for the cache budget printed by the server ("CUDA SSD expert cache: N slots")
python3 analyze_hits.py profile_hits.csv --budget N --expert-mib 9.49 --alloc-out alloc.json
# 3. prune (reversible)
python3 router_bias_tool.py apply MODEL.gguf profile_hits.csv --alloc alloc.json --orig bias_orig.npy
# 4. serve with ~150 spare slots so the few never-selected live experts can be staged
./ds4-server --cuda -m MODEL.gguf --ssd-streaming --ssd-streaming-cache-experts $((N+150))
# undo
python3 router_bias_tool.py restore MODEL.gguf bias_orig.npy
```

## Data

- `data/profiles/`: the raw hit profiles (layer, expert, hits, rows[, weight]).
- `data/alloc/`: the per-layer keep counts used for the measurements.
- `data/profile_corpus.jsonl`, `data/bench_corpus.jsonl`: request corpora
  (includes prompts sampled from ds4's MIT-licensed imatrix dataset).
- `data/heldout/it_cyber.txt`: the one held-out text we can redistribute.

## Prior art

Usage-guided expert pruning is established: Lu et al. 2024 (*Not All Experts
are Equal*), Cerebras REAP (2025), MoE-Pruner, SEER-MoE and many community
scripts for Mixtral and Qwen3-MoE. Those rewrite the expert tensors. What this
repo adds is the bias-as-mask mechanism (specific to `noaux_tc` routers:
DeepSeek V3/V4/V4.1, Kimi K2), its combination with a streaming expert cache to
reach residency on a fixed memory budget, and measured numbers for V4.1 Flash
on a single DGX Spark.

## License

MIT. DeepSeek model weights and antirez/ds4 keep their own licenses.
