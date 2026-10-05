## CUDA: V4.1 routed-expert hit profiler and a resident fast path for SSD streaming

Two additions to the single-GPU CUDA V4.1 path, both inert unless enabled or unless their precondition holds.

### 1. Routed-expert hit profiler for the `ds41_*` CUDA graph

`DS4_EXPERT_HITS_OUT=<csv>` (optional `DS4_EXPERT_HITS_EVERY=<rows>`, default 2048) records how often each `(layer, expert)` pair is selected, plus the summed router weight, for decode (`ds41_moe_partial`) and prefill/batched (`ds41_route_batch`). The CSV is rewritten atomically every N router rows and at exit, so a killed `ds4-server` still leaves a usable profile. The existing `--expert-profile` is Metal-only; this gives CUDA users the same data (it is what the SSD-streaming hotlists are built from).

Cost when disabled: one `getenv` at first use. When enabled it adds one device sync per layer per token, so it is a profiling tool, not a serving mode.

### 2. Resident fast path for the streaming expert cache

Today every layer of a streaming decode does a host round trip before the routed MoE: D2H copy of the selected ids, `cudaStreamSynchronize` on the decode stream, hash lookups, H2D copy of the slot remap. When the live expert set of a layer is entirely cached (which is the normal state for a model pruned through the router bias, i.e. experts whose `exp_probs_b.bias` is below -1000 can never be selected), this round trip resolves to the same slots every time and is pure overhead.

The patch keeps a per-layer `expert -> slot` table on the device, rebuilt lazily whenever slot ownership changes (`g_stream_slot_map_version` is bumped at every point that mutates `g_stream_expert_by_gate`), and resolves the selected ids with a tiny kernel on the decode stream. Nothing in the slot map changes, so no sync is needed. The slow path is untouched and remains the fallback: layers that are not fully resident, batched prefill (`n_tokens > 1`), multi-GPU, and any model whose live set is the full 384 experts and does not fit the cache never enter the fast path. `ds4.c` passes the layer's router-bias offset to the backend (`ds4_gpu_stream_expert_cache_set_layer_bias`) so the backend can compute the live set; the fast path also stages up to 64 never-yet-selected live experts so a layer can become resident (needs spare slots: size the cache above the live total).

`DS4_CUDA_DISABLE_RESIDENT_FAST_PATH=1` disables it. `DS4_CUDA_V41_QUEUE_LAYERS=1` is a separate opt-in that skips the per-layer `ds4_gpu_end_commands()` drain in the single-GPU V4.1 decode once no per-layer host dependency remains.

### Testing

Machine: NVIDIA DGX Spark (GB10, aarch64, 119 GiB), CUDA sm_121, Micron 2500 NVMe. Model: `antirez/deepseek-v4.1-flash-gguf` Q2 (340.6 GiB, sha256 `1ce6a8f8...`), `--ssd-streaming --ctx 4096`, 8546-8700 cache slots, router bias pruned to 8546 live experts with [router_bias_tool.py](https://github.com/cdome94/v41-expert-pruning).

| configuration | decode | prefill |
|---|---|---|
| streaming, unpruned model (55% of experts cached) | 7.3 t/s | 9.0 t/s |
| streaming, pruned, slow path (this PR disabled) | 10.3 t/s | 18.8 t/s |
| streaming, pruned, resident fast path | 10.0 t/s | 18.9 t/s |
| + `DS4_CUDA_V41_QUEUE_LAYERS=1` | 12.7 t/s | 19.2 t/s |

Correctness: 40 chat completions at temperature 0 (two passes of 20 prompts, 128 tokens each) are byte-identical between the slow path and the fast path. The profiler on the pruned runs recorded 0 selections of excluded experts over 2.54M expert calls, and `pruned_q2_hits` matched the expected live set exactly.

Unpruned models never enter the fast path (the live set is never fully cached), so the default streaming behaviour and the non-streaming paths are unchanged; `make test` / `./ds4_test --server` pass (see below).

```
make ds4_test CUDA_ARCH=sm_121 && ./ds4_test --server
server: OK
ds4 tests: ok
```
(run on both the development tree and this branch rebased on current `main`). The 40-prompt byte-identity check and the speed numbers above come from `ds4-server --cuda --ssd-streaming --ssd-streaming-cache-experts 8700 --ctx 4096`, 20 warm-up requests followed by 20 measured ones (128 generated tokens each, temperature 0), medians of the per-request `decoding ... avg=` log lines.

The fast path alone did not change the decode speed (10.3 -> 10.0 t/s, within noise): once the host round trip is gone, the per-layer `ds4_gpu_end_commands()` drain becomes the limiter, hence the second, opt-in switch. I kept it opt-in because I could only validate it on the single-GPU streaming configuration.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
