#!/usr/bin/env python3
"""Corpus di profilazione per traffico agentico con tools (stile OpenCode): richieste con
definizioni di strumenti in formato OpenAI, in italiano e inglese, incluse conversazioni
con tool_calls già eseguite e messaggi role=tool, così il profilo copre sia l'emissione
della sintassi DSML sia la lettura dei risultati."""
import json, random
random.seed(7)
TOOLS = [
 {"type":"function","function":{"name":"read","description":"Reads a file from the local filesystem.","parameters":{"type":"object","properties":{"filePath":{"type":"string","description":"The absolute path to the file to read"},"offset":{"type":"number","description":"The line number to start reading from"},"limit":{"type":"number","description":"The number of lines to read"}},"required":["filePath"]}}},
 {"type":"function","function":{"name":"write","description":"Writes a file to the local filesystem, overwriting it if it exists.","parameters":{"type":"object","properties":{"filePath":{"type":"string"},"content":{"type":"string"}},"required":["filePath","content"]}}},
 {"type":"function","function":{"name":"edit","description":"Performs exact string replacements in a file.","parameters":{"type":"object","properties":{"filePath":{"type":"string"},"oldString":{"type":"string"},"newString":{"type":"string"},"replaceAll":{"type":"boolean"}},"required":["filePath","oldString","newString"]}}},
 {"type":"function","function":{"name":"bash","description":"Executes a bash command and returns its output.","parameters":{"type":"object","properties":{"command":{"type":"string"},"description":{"type":"string"},"timeout":{"type":"number"}},"required":["command","description"]}}},
 {"type":"function","function":{"name":"glob","description":"Fast file pattern matching tool.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}},
 {"type":"function","function":{"name":"grep","description":"Searches file contents using regular expressions.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"include":{"type":"string"}},"required":["pattern"]}}},
 {"type":"function","function":{"name":"list","description":"Lists files and directories in a given path.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":[]}}},
 {"type":"function","function":{"name":"todowrite","description":"Create and manage a structured task list.","parameters":{"type":"object","properties":{"todos":{"type":"array","items":{"type":"object","properties":{"content":{"type":"string"},"status":{"type":"string"},"priority":{"type":"string"},"id":{"type":"string"}}}}},"required":["todos"]}}},
]
SYS_IT = "Sei OpenCode, un agente di programmazione interattivo che lavora in un repository locale. Usa gli strumenti per leggere, cercare e modificare file ed eseguire comandi. Spiega brevemente cosa fai. Rispondi in italiano."
SYS_EN = "You are OpenCode, an interactive coding agent working in a local repository. Use the tools to read, search and edit files and run commands. Keep explanations short."
IT = [
 "Elenca i file di questa cartella e dimmi che tipo di progetto è.",
 "Trova tutte le occorrenze di 'TODO' nei file .py e riassumile.",
 "Leggi README.md e proponi tre miglioramenti.",
 "Aggiungi la gestione dell'eccezione FileNotFoundError nella funzione load_config in src/config.py.",
 "Esegui i test con pytest e dimmi quali falliscono.",
 "Crea un file .gitignore adatto a un progetto Python con virtualenv e cache di pytest.",
 "Cerca dove viene definita la classe Scanner e spiega come viene usata.",
 "Correggi il bug per cui lo script scan.py va in crash quando l'host non risponde al ping.",
 "Scrivi uno script bash scripts/backup.sh che faccia il backup della cartella data/ con rsync.",
 "Quante righe di codice ci sono nel progetto, per linguaggio?",
 "Il parser dei log in parser/syslog.py non gestisce i timestamp con fuso orario: sistemalo e aggiungi un test.",
 "Prepara una lista di attività per migrare il progetto da requests a httpx.",
 "Controlla se ci sono credenziali in chiaro nei file di configurazione.",
 "Aggiungi il logging con il modulo logging al posto delle print in src/main.py.",
 "Leggi il Dockerfile e rendilo multi-stage.",
 "Mostra gli ultimi 20 commit e riassumi cosa è cambiato.",
 "Trova le funzioni senza docstring in src/ e aggiungine una a ciascuna.",
 "Verifica che il server risponda su localhost:8080 con curl e riporta l'header Server.",
 "Scrivi una regola Sigma in rules/powershell_encoded.yml che rilevi PowerShell con -EncodedCommand.",
 "Analizza il file logs/auth.log ed estrai gli IP con più di 10 login falliti.",
 "Aggiungi un endpoint GET /health all'app Flask in app.py.",
 "Converti il file config.ini in config.yaml e aggiorna il codice che lo legge.",
 "Spiega cosa fa la funzione parse_packet in net/packet.c e trova eventuali buffer overflow.",
 "Esegui make e correggi gli errori di compilazione.",
]
EN = [
 "List the files in this directory and tell me what kind of project this is.",
 "Find all usages of the deprecated function old_hash() and replace them with new_hash().",
 "Read package.json and explain the build pipeline.",
 "Run the test suite and fix the first failing test.",
 "Add input validation to the /login handler in server.js.",
 "Create a GitHub Actions workflow that runs lint and tests on push.",
 "Search for hardcoded IP addresses in the source tree.",
 "Write a Python script tools/parse_nmap.py that converts nmap XML output to CSV.",
 "Where is the database connection configured? Show me the relevant code.",
 "Refactor utils/date.py to use datetime.timezone instead of pytz.",
 "Check git status and summarize the uncommitted changes.",
 "Add a Suricata rule in rules/local.rules that alerts on HTTP requests containing 'cmd.exe'.",
]
# conversazioni con tool già eseguita (tool_calls + tool result), per profilare la fase successiva
FOLLOWUPS = [
 ([{"role":"user","content":"Elenca i file di questa cartella e dimmi che tipo di progetto è."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_1","type":"function","function":{"name":"list","arguments":"{\"path\": \".\"}"}}]},
   {"role":"tool","tool_call_id":"call_1","content":"README.md\nrequirements.txt\nsrc/\nsrc/main.py\nsrc/scanner.py\nsrc/report.py\ntests/\ntests/test_scanner.py\nDockerfile\n.github/workflows/ci.yml"}], SYS_IT),
 ([{"role":"user","content":"Esegui i test con pytest e dimmi quali falliscono."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_2","type":"function","function":{"name":"bash","arguments":"{\"command\": \"python -m pytest -q\", \"description\": \"Run the test suite\"}"}}]},
   {"role":"tool","tool_call_id":"call_2","content":"....F..F\n=== FAILURES ===\n___ test_parse_timestamp_tz ___\nparser/syslog.py:42: ValueError: unconverted data remains: +02:00\n___ test_scan_timeout ___\nsrc/scanner.py:88: TimeoutError\n2 failed, 6 passed in 1.42s"}], SYS_IT),
 ([{"role":"user","content":"Trova tutte le occorrenze di 'TODO' nei file .py e riassumile."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_3","type":"function","function":{"name":"grep","arguments":"{\"pattern\": \"TODO\", \"include\": \"*.py\"}"}}]},
   {"role":"tool","tool_call_id":"call_3","content":"src/main.py:12: # TODO: gestire SIGTERM\nsrc/scanner.py:55: # TODO: timeout configurabile\nsrc/report.py:9: # TODO: export in JSON\ntests/test_scanner.py:3: # TODO: mock della rete"}], SYS_IT),
 ([{"role":"user","content":"Read README.md and propose three improvements."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_4","type":"function","function":{"name":"read","arguments":"{\"filePath\": \"/repo/README.md\"}"}}]},
   {"role":"tool","tool_call_id":"call_4","content":"# netscan\n\nSmall network scanner.\n\n## Usage\n\npython src/main.py 10.0.0.0/24\n\n## Tests\n\npytest"}], SYS_EN),
 ([{"role":"user","content":"Analizza il file logs/auth.log ed estrai gli IP con più di 10 login falliti."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_5","type":"function","function":{"name":"bash","arguments":"{\"command\": \"grep 'Failed password' logs/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head\", \"description\": \"Count failed logins per IP\"}"}}]},
   {"role":"tool","tool_call_id":"call_5","content":"     48 203.0.113.45\n     31 198.51.100.7\n     12 192.0.2.19\n      3 10.0.0.5"}], SYS_IT),
 ([{"role":"user","content":"Where is the database connection configured? Show me the relevant code."},
   {"role":"assistant","content":None,"tool_calls":[{"id":"call_6","type":"function","function":{"name":"grep","arguments":"{\"pattern\": \"connect\\\\(\", \"include\": \"*.js\"}"}}]},
   {"role":"tool","tool_call_id":"call_6","content":"db/index.js:14:  const client = await pg.connect(process.env.DATABASE_URL);\nserver.js:3:const db = require('./db');"}], SYS_EN),
]
out = []
def add(group, msgs, system, think, max_tokens):
    out.append({"id": f"{group}-{len(out):04d}", "group": group, "think": think, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}] + msgs, "tools": TOOLS, "tool_choice": "auto"})
for i, p in enumerate(IT): add("tools-it", [{"role": "user", "content": p}], SYS_IT, i % 5 == 0, 220)
for i, p in enumerate(EN): add("tools-en", [{"role": "user", "content": p}], SYS_EN, i % 4 == 0, 220)
for msgs, sysm in FOLLOWUPS: add("tools-followup", msgs, sysm, False, 220)
# ripeti i followup e alcune richieste in modalità think per coprire la sintassi anche dopo il ragionamento
for msgs, sysm in FOLLOWUPS[:3]: add("tools-followup-think", msgs, sysm, True, 320)
random.shuffle(out)
with open("profile_tools_corpus.jsonl", "w") as f:
    for d in out: f.write(json.dumps(d, ensure_ascii=False) + "\n")
import collections; print(len(out), collections.Counter(d["group"] for d in out), "think", sum(d["think"] for d in out))
