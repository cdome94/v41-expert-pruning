#!/usr/bin/env python3
"""Build the expert-usage profiling corpus for V4.1 Flash on the Spark.

Mix (target workload: Italian, cyber-security, code, agent/tool traffic):
  - hand-written Italian cyber/code/general prompts (below)
  - hand-written English cyber prompts
  - a seeded sample of the ds4 imatrix dataset (agent, source review, programming,
    language, general, algorithms, translation), both think and nothink
Output: profile_corpus.jsonl, one chat request per line:
  {"id","group","think":bool,"max_tokens",N,"messages":[...]} 
Held-out material (GUIDA.md, long_context_story_prompt.txt, cve_scorer code,
ds4-eval COMPSEC cases, quality-testing prompts) is deliberately NOT included.
"""
import json, random, sys, pathlib
random.seed(20261002)
ROOT = pathlib.Path('/home/utente/ds4-engine')
out = []
def add(group, user, system=None, think=False, max_tokens=160, extra_msgs=None):
    msgs = []
    if system: msgs.append({"role":"system","content":system})
    if extra_msgs: msgs.extend(extra_msgs)
    msgs.append({"role":"user","content":user})
    out.append({"id":f"{group}-{len(out):04d}","group":group,"think":think,"max_tokens":max_tokens,"messages":msgs})

SYS_IT = "Sei un assistente esperto di cybersecurity che lavora per una società italiana di sicurezza informatica. Rispondi in italiano, in modo tecnico e conciso."
SYS_CODE_IT = "Sei un assistente di programmazione. Rispondi in italiano con codice commentato e spiegazioni brevi."

IT_CYBER = [
 "Spiega la differenza tra IDS e IPS e quando conviene usare l'uno o l'altro in una rete aziendale.",
 "Analizza questa riga di log Apache e dimmi se è un tentativo di attacco:\n203.0.113.45 - - [12/Sep/2026:03:14:07 +0200] \"GET /index.php?page=../../../../etc/passwd HTTP/1.1\" 200 5123",
 "Cos'è una CVE con punteggio CVSS 9.8? Fai un esempio di come la gestiresti in un processo di patch management.",
 "Scrivi una regola Sigma che rilevi l'esecuzione di PowerShell con parametri codificati in base64 su Windows.",
 "Descrivi le fasi di una risposta a incidente secondo il NIST SP 800-61 e cosa fa il SOC in ciascuna.",
 "Un dipendente ha ricevuto un'email con allegato .docm che chiede di abilitare le macro. Che indicatori di phishing cerchi e come procedi?",
 "Spiega cos'è il lateral movement e quali log di Windows (Event ID) servono per individuarlo.",
 "Quali differenze ci sono tra TLS 1.2 e TLS 1.3 in termini di sicurezza e handshake?",
 "Scrivi una query KQL per Microsoft Sentinel che trovi più di 10 login falliti dallo stesso IP in 5 minuti.",
 "Spiega l'attacco Kerberoasting e come mitigarlo in Active Directory.",
 "Cos'è il principio del minimo privilegio e come lo applichi ai ruoli IAM su AWS?",
 "Che cosa prevede la direttiva NIS2 per un'azienda italiana del settore energia? Elenca gli obblighi principali.",
 "Un cliente ti chiede un vulnerability assessment e un penetration test: spiega la differenza e cosa include il report finale.",
 "Analizza questo header SMTP e dimmi se SPF, DKIM e DMARC sono passati:\nAuthentication-Results: mx.example.it; spf=fail smtp.mailfrom=banca-sicura.com; dkim=none; dmarc=fail",
 "Spiega come funziona un attacco SQL injection di tipo blind e come lo rilevi dai log del database.",
 "Elenca i controlli CIS più importanti per un server Linux esposto su Internet.",
 "Che cos'è una SBOM e perché è importante per la sicurezza della supply chain software?",
 "Spiega ransomware a doppia estorsione e quali misure di backup riducono l'impatto.",
 "Scrivi una regola YARA che identifichi un file PE con la stringa 'Invoke-Mimikatz' e una sezione .text anomala.",
 "Come configuri fail2ban per proteggere SSH su Debian? Mostra la configurazione della jail.",
 "Cos'è il GDPR data breach notification e entro quanto tempo va notificato al Garante?",
 "Spiega la differenza tra hashing, cifratura simmetrica e asimmetrica con esempi d'uso aziendali.",
 "Un server web mostra connessioni in uscita verso la porta 4444 di un IP sconosciuto. Cosa sospetti e quali passi di triage fai?",
 "Spiega cos'è lo zero trust e come si traduce in architettura di rete per una PMI.",
 "Scrivi uno script bash che estragga da /var/log/auth.log gli IP con più di 20 tentativi SSH falliti.",
 "Come funziona l'autenticazione a più fattori basata su FIDO2 e perché resiste al phishing?",
 "Spiega cos'è un WAF, quali attacchi OWASP Top 10 blocca e quali no.",
 "Descrivi il framework MITRE ATT&CK e come lo usi per mappare un incidente.",
 "Quali rischi di sicurezza comporta esporre un'API REST senza rate limiting? Proponi mitigazioni.",
 "Spiega cos'è il DNS tunneling e come individuarlo analizzando il traffico.",
 "Redigi una breve policy aziendale sull'uso delle password e dei password manager.",
 "Spiega la vulnerabilità Log4Shell (CVE-2021-44228) e perché è stata così grave.",
 "Un pentester ha trovato un bucket S3 pubblico con dati dei clienti. Scrivi il paragrafo del report con rischio, impatto e remediation.",
 "Cos'è l'hardening di un container Docker? Elenca le pratiche principali.",
 "Spiega cosa sono gli IoC e come li condividi in formato STIX/TAXII.",
 "Come si fa l'analisi di un dump di memoria con Volatility per trovare processi nascosti?",
 "Spiega la differenza tra SIEM, SOAR e XDR.",
 "Quali sono i rischi di un attacco man-in-the-middle su una rete Wi-Fi aziendale e come li mitighi con 802.1X?",
 "Descrivi un piano di disaster recovery con RPO e RTO per un'azienda con ERP on-premise.",
 "Spiega come funziona OAuth 2.0 con PKCE e quali errori di implementazione sono più comuni.",
]
IT_CODE = [
 "Scrivi una funzione Python che faccia il parsing di un file di log in formato syslog e restituisca un dizionario con il conteggio dei messaggi per host.",
 "Scrivi un programma C che legga un file binario a blocchi di 4096 byte e calcoli lo SHA-256 usando OpenSSL.",
 "Come posso rendere thread-safe questa classe Python che tiene un contatore condiviso? Mostra il codice con threading.Lock.",
 "Scrivi uno script bash che faccia il backup incrementale di una directory con rsync e ruoti i backup più vecchi di 30 giorni.",
 "Spiega la differenza tra mmap e read per leggere file molto grandi in C e quando conviene l'uno o l'altro.",
 "Scrivi una query SQL che trovi gli utenti con più di 3 ordini nell'ultimo mese e la somma degli importi.",
 "Converti questo codice Python 2 in Python 3:\nprint \"ciao\"\nfor k, v in d.iteritems():\n    print k, v",
 "Scrivi un Dockerfile multi-stage per un'applicazione Go che produca un'immagine minimale.",
 "Scrivi un test pytest per una funzione che valida indirizzi IPv4 e gestisce i casi limite.",
 "Spiega cos'è una race condition con un esempio in Go e come risolverla con i channel.",
 "Scrivi una funzione JavaScript che faccia il debounce di una chiamata API e spiega come funziona.",
 "Rivedi questo codice e trova i bug:\nint *p = malloc(10);\nfor (int i = 0; i <= 10; i++) p[i] = i;\nfree(p);\nprintf(\"%d\\n\", p[0]);",
 "Scrivi uno script Python che interroghi l'API di NVD per una CVE e stampi punteggio CVSS e descrizione.",
 "Come configuro un reverse proxy nginx con TLS e HSTS per un servizio su localhost:8000?",
 "Spiega cosa fa questo comando: find / -perm -4000 -type f 2>/dev/null e perché è rilevante per la sicurezza.",
 "Scrivi un parser in Python per il formato CSV esportato da un firewall con campi: data, src_ip, dst_ip, porta, azione. Produci un riepilogo per azione.",
 "Scrivi una funzione C che faccia il parsing sicuro di un intero da stringa senza overflow.",
 "Mostra come usare systemd per eseguire uno script Python ogni 10 minuti con un timer.",
 "Scrivi una regola iptables che permetta solo SSH da 10.0.0.0/8 e HTTP/HTTPS da ovunque, bloccando il resto.",
 "Spiega la differenza tra autenticazione con JWT e sessioni server-side, con pro e contro.",
]
IT_GENERAL = [
 "Riassumi in cinque punti i vantaggi del lavoro ibrido per un'azienda di consulenza informatica.",
 "Scrivi un'email formale a un cliente per comunicare il rinvio di una consegna di una settimana.",
 "Spiega a un bambino di dieci anni cos'è Internet.",
 "Traduci in inglese: 'Il sistema è stato aggiornato ieri sera e non si sono verificati disservizi.'",
 "Quali sono le principali differenze tra un contratto a tempo determinato e uno indeterminato in Italia?",
 "Scrivi una breve descrizione per il sito web di una società di cybersecurity con sede a Milano.",
 "Correggi gli errori in questa frase: 'Gli aggiornamento sono stato installato correttamente sul server.'",
 "Elenca i passaggi per preparare un buon risotto alla milanese.",
 "Spiega la differenza tra PEC e email ordinaria e quando è obbligatoria la PEC.",
 "Scrivi tre domande da fare in un colloquio a un analista SOC junior.",
]
EN_CYBER = [
 "Explain the difference between stateful and stateless firewalls with examples of rules.",
 "Write a Suricata rule that detects an HTTP request containing 'cmd.exe' in the URI.",
 "What is a pass-the-hash attack and how does Windows Credential Guard mitigate it?",
 "Analyze this nmap output and suggest next steps for a pentest:\n22/tcp open ssh OpenSSH 7.2p2\n80/tcp open http Apache 2.4.18\n445/tcp open microsoft-ds Samba 4.3.11",
 "Explain CVSS v3.1 base metrics and compute the score for a network-exploitable RCE with no privileges required and high impact.",
 "Write a Python script that parses a pcap with scapy and lists the top 10 talkers by bytes.",
 "Describe how TLS certificate pinning works in mobile apps and how attackers bypass it during authorized testing.",
 "What are the OWASP Top 10 2021 categories? Give one mitigation for each.",
 "Explain the SolarWinds supply chain attack and the lessons for build pipeline security.",
 "How does EDR detect process injection techniques such as CreateRemoteThread?",
 "Write a Sigma rule for detection of new scheduled tasks created by non-admin users.",
 "Explain how to triage a suspected phishing email: headers, URLs, attachments, and sandboxing.",
 "What is BGP hijacking and how does RPKI help?",
 "Compare SAST, DAST, and IAST for a CI/CD pipeline.",
 "Explain the Linux capabilities model and why CAP_SYS_ADMIN is dangerous in containers.",
]
for i, p in enumerate(IT_CYBER):  add("it-cyber", p, SYS_IT, think=(i % 4 == 0), max_tokens=220 if i % 4 else 400)
for i, p in enumerate(IT_CODE):   add("it-code", p, SYS_CODE_IT, think=(i % 5 == 0), max_tokens=260 if i % 5 else 400)
for i, p in enumerate(IT_GENERAL):add("it-general", p, None, think=False, max_tokens=180)
for i, p in enumerate(EN_CYBER):  add("en-cyber", p, None, think=(i % 4 == 0), max_tokens=220 if i % 4 else 400)

# imatrix dataset sample (use the messages as-is, including tool system prompts)
rows = [json.loads(l) for l in open(ROOT/'gguf-tools/imatrix/dataset/prompts.jsonl')]
want = {"agent":40, "source":30, "programming":12, "language":16, "general":8, "algorithms":6, "translation":6, "long_context":2}
by = {}
for d in rows: by.setdefault(d['category'], []).append(d)
for cat, n in want.items():
    xs = [d for d in by[cat] if len(d['rendered']) < 9000]
    for d in random.sample(xs, n):
        msgs = [m for m in d['messages']]
        # keep only through the last user turn (drop the dataset's assistant answer)
        last_user = max(i for i, m in enumerate(msgs) if m['role'] == 'user')
        msgs = msgs[:last_user + 1]
        # drop tool-call turns that need tool results to be meaningful
        if any(m['role'] not in ('system','user','assistant') for m in msgs): continue
        out.append({"id":f"imx-{cat}-{len(out):04d}","group":"imatrix-"+cat,"think":d['mode']=='think',
                    "max_tokens":300 if d['mode']=='think' else 160,"messages":msgs})
random.shuffle(out)
with open('profile_corpus.jsonl','w') as fp:
    for d in out: fp.write(json.dumps(d, ensure_ascii=False)+'\n')
import collections
print(len(out), collections.Counter(d['group'] for d in out))
print('think', sum(d['think'] for d in out), 'approx prompt chars', sum(len(json.dumps(d['messages'])) for d in out))
