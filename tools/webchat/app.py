#!/usr/bin/env python3
"""Web chat con login per il modello servito da ds4-server (solo libreria standard).

  python3 app.py serve [--port 8080] [--bind 0.0.0.0] [--upstream http://127.0.0.1:8011]
  python3 app.py passwd UTENTE          imposta/cambia la password (chiede la password da stdin o la genera)
  python3 app.py users                  elenca gli utenti

Credenziali in ~/.ds4-webchat/users.json (hash scrypt + salt), chiave di firma dei cookie in
~/.ds4-webchat/secret. Sessione: cookie HMAC con scadenza 12 h. Il server del modello non è
esposto: il browser parla solo con questa app, che inoltra in streaming (SSE) dopo il login.
Rate limit sui tentativi di login: 5 falliti per IP -> 60 s di attesa.
"""
import argparse, base64, hashlib, hmac, http.cookies, json, os, secrets, sys, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

CONF = os.path.expanduser("~/.ds4-webchat")
USERS = os.path.join(CONF, "users.json")
SECRET = os.path.join(CONF, "secret")
SESSION_TTL = 12 * 3600
UPSTREAM = "http://127.0.0.1:8011"
MODELS = {"veloce": "deepseek-chat", "ragionamento": "deepseek-v4.1-flash"}

def load_users():
    try: return json.load(open(USERS))
    except FileNotFoundError: return {}
def save_users(u):
    os.makedirs(CONF, mode=0o700, exist_ok=True)
    tmp = USERS + ".tmp"; json.dump(u, open(tmp, "w"), indent=1); os.chmod(tmp, 0o600); os.replace(tmp, USERS)
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32, maxmem=64*1024*1024)
    return base64.b64encode(salt).decode(), base64.b64encode(h).decode()
def check_pw(user, pw):
    u = load_users().get(user)
    if not u: hash_pw(pw); return False   # tempo costante anche per utenti inesistenti
    salt = base64.b64decode(u["salt"]); h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32, maxmem=64*1024*1024)
    return hmac.compare_digest(base64.b64encode(h).decode(), u["hash"])
def secret():
    os.makedirs(CONF, mode=0o700, exist_ok=True)
    if not os.path.exists(SECRET):
        open(SECRET, "wb").write(secrets.token_bytes(32)); os.chmod(SECRET, 0o600)
    return open(SECRET, "rb").read()
def make_token(user):
    exp = int(time.time()) + SESSION_TTL
    body = f"{user}|{exp}".encode()
    sig = hmac.new(secret(), body, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(body).decode() + "." + sig
def check_token(tok):
    try:
        b64, sig = tok.split("."); body = base64.urlsafe_b64decode(b64.encode())
        if not hmac.compare_digest(hmac.new(secret(), body, hashlib.sha256).hexdigest(), sig): return None
        user, exp = body.decode().split("|")
        if int(exp) < time.time() or user not in load_users(): return None
        return user
    except Exception: return None

PAGE = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chat V4.1 Spark</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#2a2f3a;--fg:#e6e6e6;--mut:#9aa3b2;--acc:#4f8cff;--me:#1f2a44;--ai:#1b1f27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;display:flex;flex-direction:column;height:100vh}
header{display:flex;gap:12px;align-items:center;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--line)}
header b{flex:1}select,button,input{font:inherit;background:#0f1115;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
button.p{background:var(--acc);border-color:var(--acc);color:#fff;cursor:pointer}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.m{max-width:900px;padding:10px 14px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}
.me{background:var(--me);align-self:flex-end}.ai{background:var(--ai);align-self:flex-start;border:1px solid var(--line)}
.r{color:var(--mut);font-size:13px;border-left:3px solid var(--line);padding-left:10px;margin-bottom:8px;white-space:pre-wrap}
.s{color:var(--mut);font-size:12px;margin-top:6px}
form#f{display:flex;gap:8px;padding:12px 16px;background:var(--panel);border-top:1px solid var(--line)}
textarea{flex:1;resize:none;height:64px;font:inherit;background:#0f1115;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px}
</style></head><body>
<header><b>DeepSeek V4.1 Flash · Spark</b>
<label>Modello <select id="model"><option value="veloce">veloce (senza ragionamento)</option><option value="ragionamento">con ragionamento</option></select></label>
<button id="reset">Nuova chat</button><a href="/logout"><button>Esci</button></a></header>
<div id="log"></div>
<form id="f"><textarea id="t" placeholder="Scrivi... (Invio per inviare, Shift+Invio a capo)"></textarea><button class="p" id="send">Invia</button></form>
<script>
const log=document.getElementById('log'),t=document.getElementById('t'),f=document.getElementById('f'),send=document.getElementById('send');
let hist=JSON.parse(sessionStorage.getItem('hist')||'[]'),busy=false;
function add(cls,txt){const d=document.createElement('div');d.className='m '+cls;d.textContent=txt;log.appendChild(d);log.scrollTop=log.scrollHeight;return d}
hist.forEach(m=>add(m.role==='user'?'me':'ai',m.content));
document.getElementById('reset').onclick=()=>{hist=[];sessionStorage.removeItem('hist');log.innerHTML=''};
t.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();f.requestSubmit()}});
f.onsubmit=async e=>{e.preventDefault();if(busy)return;const q=t.value.trim();if(!q)return;t.value='';
 hist.push({role:'user',content:q});add('me',q);busy=true;send.disabled=true;
 const box=add('ai','');const r=document.createElement('div');r.className='r';r.style.display='none';const body=document.createElement('div');const st=document.createElement('div');st.className='s';box.append(r,body,st);
 let ans='',reas='',n=0,t0=performance.now(),first=0;
 try{const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:document.getElementById('model').value,messages:hist})});
  if(res.status===401){location.href='/login';return}
  const rd=res.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+1);if(!line.startsWith('data: '))continue;const p=line.slice(6);if(p==='[DONE]')continue;
    let j;try{j=JSON.parse(p)}catch{continue}if(j.error){body.textContent='Errore: '+j.error;continue}
    const d=(j.choices&&j.choices[0]&&j.choices[0].delta)||{};
    if(d.reasoning_content){reas+=d.reasoning_content;r.style.display='';r.textContent=reas}
    if(d.content){if(!first)first=performance.now();ans+=d.content;n++;body.textContent=ans}
    st.textContent=(reas?'ragionamento '+reas.length+' car. · ':'')+(first?((n/((performance.now()-first)/1000))||0).toFixed(1)+' tok/s':'in attesa del primo token...');log.scrollTop=log.scrollHeight}}
  hist.push({role:'assistant',content:ans});sessionStorage.setItem('hist',JSON.stringify(hist));
 }catch(err){body.textContent='Errore di rete: '+err}finally{busy=false;send.disabled=false;t.focus()}};
</script></body></html>"""
LOGIN = """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Accesso</title>
<style>body{margin:0;background:#0f1115;color:#e6e6e6;font:15px system-ui,sans-serif;display:grid;place-items:center;height:100vh}
form{background:#171a21;border:1px solid #2a2f3a;border-radius:12px;padding:28px;width:320px;display:flex;flex-direction:column;gap:10px}
input,button{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid #2a2f3a;background:#0f1115;color:#e6e6e6}button{background:#4f8cff;border-color:#4f8cff;color:#fff;cursor:pointer}
.e{color:#ff7b7b;font-size:13px}</style></head><body>
<form method="post" action="/login"><b>Chat V4.1 · Spark</b><input name="user" placeholder="utente" autocomplete="username" required autofocus>
<input name="pw" type="password" placeholder="password" autocomplete="current-password" required><button>Entra</button>%s</form></body></html>"""

fails = {}; flock = threading.Lock()
def limited(ip):
    with flock:
        n, until = fails.get(ip, (0, 0))
        return n >= 5 and time.time() < until
def record_fail(ip):
    with flock:
        n, _ = fails.get(ip, (0, 0)); fails[ip] = (n + 1, time.time() + 60)
def clear_fail(ip):
    with flock: fails.pop(ip, None)

class H(BaseHTTPRequestHandler):
    server_version = "ds4-webchat/1"
    def log_message(self, fmt, *a): sys.stderr.write("%s %s %s\n" % (time.strftime("%F %T"), self.client_address[0], fmt % a))
    def user(self):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", "")); tok = c.get("s")
        return check_token(tok.value) if tok else None
    def send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Frame-Options", "DENY")
        for k, v in extra: self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def redirect(self, to, extra=()):
        self.send_response(303); self.send_header("Location", to)
        for k, v in extra: self.send_header(k, v)
        self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        if self.path == "/login": return self.send(200, LOGIN % "")
        if self.path == "/logout": return self.redirect("/login", [("Set-Cookie", "s=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")])
        if self.path == "/healthz": return self.send(200, "ok", "text/plain")
        if not self.user(): return self.redirect("/login")
        if self.path in ("/", "/index.html"): return self.send(200, PAGE)
        self.send(404, "not found", "text/plain")
    def body_json(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > 2_000_000: raise ValueError("body too large")
        return self.rfile.read(n)
    def do_POST(self):
        ip = self.client_address[0]
        if self.path == "/login":
            if limited(ip): return self.send(429, LOGIN % '<div class="e">Troppi tentativi: riprova tra un minuto.</div>')
            q = parse_qs(self.body_json().decode()); u = q.get("user", [""])[0].strip(); p = q.get("pw", [""])[0]
            if u and check_pw(u, p):
                clear_fail(ip); tok = make_token(u)
                return self.redirect("/", [("Set-Cookie", f"s={tok}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Strict")])
            record_fail(ip); time.sleep(1)
            return self.send(401, LOGIN % '<div class="e">Credenziali non valide.</div>')
        if self.path == "/api/chat":
            user = self.user()
            if not user: return self.send(401, '{"error":"login"}', "application/json")
            try:
                req = json.loads(self.body_json()); msgs = req.get("messages") or []
                model = MODELS.get(req.get("model", "veloce"), MODELS["veloce"])
                if not isinstance(msgs, list) or len(msgs) > 200: raise ValueError("messages")
                msgs = [{"role": m["role"], "content": str(m["content"])[:60000]} for m in msgs if m.get("role") in ("user", "assistant")]
            except Exception as e:
                return self.send(400, json.dumps({"error": str(e)}), "application/json")
            sysmsg = {"role": "system", "content": "Sei un assistente tecnico. Rispondi in italiano in modo preciso e conciso."}
            body = {"model": model, "messages": [sysmsg] + msgs, "stream": True, "max_tokens": 4096, "temperature": 0.7}
            if model == MODELS["ragionamento"]: body["reasoning_effort"] = "low"
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store"); self.end_headers()
            try:
                r = urllib.request.urlopen(urllib.request.Request(UPSTREAM + "/v1/chat/completions", data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json"}), timeout=3600)
                for line in r:
                    self.wfile.write(line); self.wfile.flush()
            except urllib.error.HTTPError as e:
                self.wfile.write(("data: " + json.dumps({"error": f"upstream {e.code}: {e.read().decode(errors='replace')[:300]}"}) + "\n\n").encode())
            except Exception as e:
                try: self.wfile.write(("data: " + json.dumps({"error": str(e)}) + "\n\n").encode())
                except Exception: pass
            return
        self.send(404, "not found", "text/plain")

def main():
    global UPSTREAM
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8080); s.add_argument("--bind", default="0.0.0.0"); s.add_argument("--upstream", default=UPSTREAM)
    p = sub.add_parser("passwd"); p.add_argument("user"); p.add_argument("--generate", action="store_true")
    sub.add_parser("users")
    a = ap.parse_args()
    if a.cmd == "users":
        for u in load_users(): print(u)
    elif a.cmd == "passwd":
        if a.generate or not sys.stdin.isatty(): pw = sys.stdin.readline().strip() if not sys.stdin.isatty() and not a.generate else secrets.token_urlsafe(12)
        else:
            import getpass; pw = getpass.getpass("nuova password: ")
        if len(pw) < 8: sys.exit("password troppo corta (min 8)")
        users = load_users(); salt, h = hash_pw(pw); users[a.user] = {"salt": salt, "hash": h}; save_users(users)
        print(f"utente '{a.user}' aggiornato" + (f", password generata: {pw}" if a.generate else ""))
    else:
        UPSTREAM = a.upstream; secret()
        if not load_users(): sys.exit("nessun utente: crea prima un account con  python3 app.py passwd UTENTE --generate")
        srv = ThreadingHTTPServer((a.bind, a.port), H); srv.daemon_threads = True
        print(f"webchat su http://{a.bind}:{a.port} -> {UPSTREAM}", flush=True); srv.serve_forever()
if __name__ == "__main__": main()
