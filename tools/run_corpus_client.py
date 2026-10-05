#!/usr/bin/env python3
"""Send profile_corpus.jsonl to a ds4-server sequentially; save outputs + timings.
Usage: run_corpus_client.py CORPUS OUT.jsonl [--port 8011] [--limit N] [--resume]
"""
import json, sys, time, argparse, urllib.request, urllib.error, os
ap=argparse.ArgumentParser(); ap.add_argument('corpus'); ap.add_argument('out')
ap.add_argument('--port',type=int,default=8011); ap.add_argument('--limit',type=int)
ap.add_argument('--resume',action='store_true'); ap.add_argument('--temperature',type=float,default=0.0)
a=ap.parse_args()
base=f'http://127.0.0.1:{a.port}'
done=set()
if a.resume and os.path.exists(a.out):
    for l in open(a.out):
        try: done.add(json.loads(l)['id'])
        except Exception: pass
# wait for the server
t0=time.time()
while True:
    try:
        urllib.request.urlopen(base+'/v1/models',timeout=5).read(); break
    except Exception as e:
        if time.time()-t0>3600: sys.exit('server never came up: %s'%e)
        time.sleep(10)
print('server up after %.0fs'%(time.time()-t0),flush=True)
reqs=[json.loads(l) for l in open(a.corpus)]
if a.limit: reqs=reqs[:a.limit]
with open(a.out,'a') as fo:
    for i,r in enumerate(reqs):
        if r['id'] in done: continue
        body={'model':'deepseek-v4.1-flash','messages':r['messages'],'max_tokens':r['max_tokens'],
              'temperature':a.temperature,'stream':False,'think':bool(r['think'])}
        if r.get('tools'): body['tools']=r['tools']; body['tool_choice']=r.get('tool_choice','auto')
        data=json.dumps(body).encode()
        t=time.time()
        try:
            resp=urllib.request.urlopen(urllib.request.Request(base+'/v1/chat/completions',data=data,
                 headers={'Content-Type':'application/json'}),timeout=3600)
            js=json.loads(resp.read())
            dt=time.time()-t
            ch=js.get('choices',[{}])[0].get('message',{})
            rec={'id':r['id'],'group':r['group'],'think':r['think'],'seconds':round(dt,1),
                 'usage':js.get('usage'),'content':ch.get('content'),'reasoning':ch.get('reasoning_content') or ch.get('reasoning'),
                 'tool_calls':ch.get('tool_calls'),
                 'finish':js.get('choices',[{}])[0].get('finish_reason')}
        except urllib.error.HTTPError as e:
            rec={'id':r['id'],'group':r['group'],'error':e.code,'body':e.read().decode(errors='replace')[:500],'seconds':round(time.time()-t,1)}
        except Exception as e:
            rec={'id':r['id'],'group':r['group'],'error':str(e),'seconds':round(time.time()-t,1)}
        fo.write(json.dumps(rec,ensure_ascii=False)+'\n'); fo.flush()
        u=rec.get('usage') or {}
        print(f"[{i+1}/{len(reqs)}] {r['id']} {rec['seconds']}s prompt={u.get('prompt_tokens')} out={u.get('completion_tokens')} {'ERR '+str(rec.get('error')) if 'error' in rec else ''}",flush=True)
print('done')
