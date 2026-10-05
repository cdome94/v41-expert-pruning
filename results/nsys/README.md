# nsys capture of the pruned Q2 decode at steady state

`nsys profile --delay 330 --duration 40 --trace cuda,osrt` on `ds4-server --cuda --ssd-streaming --ssd-streaming-cache-experts 8700` serving the router-bias-pruned Q2 (8546 live experts) with the resident fast path and `DS4_CUDA_V41_QUEUE_LAYERS=1`, 12.4 t/s decode, ~400 tokens in the window.

Per token (divide totals by ~399): non-routed Q8 matmuls 31 ms (memory-bound, 9.4 GiB/token), IQ2_XXS expert gate/up decode kernel 20 ms (3.6x slower than bandwidth), attention Q8 projections 9 ms, Q2_K expert down 8 ms (2.9x slower than bandwidth), F16 hyper-connection gemv 5 ms, small kernels ~5 ms, GPU idle ~12 ms (106 synchronous device-to-device `cudaMemcpy` and 3 `cudaDeviceSynchronize` per token). The streaming cache no longer appears in the profile.
