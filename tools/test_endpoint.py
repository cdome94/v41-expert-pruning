#!/usr/bin/env python3
"""Collaudo endpoint per client tipo OpenCode: prompt lungo (prefill) e tool call.
Uso: test_endpoint.py [URL]  (default http://127.0.0.1:8011)"""
import json, sys, time, urllib.request
url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011").rstrip("/")
def post(body, timeout=1800):
    t = time.time()
    js = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/v1/chat/completions",
         data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer dsv4-local"}),
         timeout=timeout).read())
    return js, time.time() - t
# 1) prompt lungo: ~4k token di codice C del repo + domanda
src = open("/home/utente/ds4-engine/ds4_ssd.c").read()[:14000]
body = {"model": "deepseek-v4.1-flash", "max_tokens": 64, "temperature": 0, "think": False,
        "messages": [{"role": "system", "content": "Sei un assistente di programmazione. Rispondi in italiano."},
                     {"role": "user", "content": "Ecco un file C:\n\n```c\n" + src + "\n```\n\nIn una frase: cosa fa la funzione ds4_ssd_auto_cache_plan?"}]}
js, dt = post(body); u = js["usage"]
print(f"[prefill lungo] prompt {u['prompt_tokens']} tok, out {u['completion_tokens']} tok, {dt:.1f}s totali -> ~{u['prompt_tokens']/max(dt-u['completion_tokens']/12.5,0.1):.0f} tok/s di prefill stimato")
print("  risposta:", js["choices"][0]["message"]["content"][:200].replace("\n", " "))
# 1b) stesso prompt di nuovo: la KV cache su disco/prefisso deve renderlo quasi istantaneo
js, dt2 = post(body); u2 = js["usage"]
print(f"[prefill ripetuto] {dt2:.1f}s (cached_tokens={u2.get('prompt_tokens_details',{}).get('cached_tokens')})")
# 2) tool call
tools = [{"type": "function", "function": {"name": "read_file", "description": "Legge un file dal repository",
          "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "percorso relativo"}}, "required": ["path"]}}}]
body = {"model": "deepseek-v4.1-flash", "max_tokens": 200, "temperature": 0, "think": False, "tools": tools, "tool_choice": "auto",
        "messages": [{"role": "system", "content": "Sei un agente di programmazione. Usa gli strumenti quando servono."},
                     {"role": "user", "content": "Leggi il file src/main.c e dimmi cosa contiene."}]}
js, dt = post(body); msg = js["choices"][0]["message"]
tc = msg.get("tool_calls")
print(f"[tool call] finish={js['choices'][0].get('finish_reason')} in {dt:.1f}s ->", json.dumps(tc, ensure_ascii=False)[:300] if tc else "NESSUNA tool call; contenuto: " + (msg.get("content") or "")[:200])
# 3) streaming SSE
req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps({"model": "deepseek-v4.1-flash", "stream": True, "max_tokens": 24, "temperature": 0, "think": False,
      "messages": [{"role": "user", "content": "Conta da 1 a 10 separando con virgole."}]}).encode(), headers={"Content-Type": "application/json"})
chunks = 0; text = ""
with urllib.request.urlopen(req, timeout=600) as r:
    for line in r:
        line = line.decode().strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            chunks += 1; d = json.loads(line[6:])["choices"][0]["delta"]; text += d.get("content") or ""
print(f"[streaming] {chunks} chunk SSE -> {text[:80]!r}")
