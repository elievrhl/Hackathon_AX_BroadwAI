from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
import json, mimetypes
ROOT=Path('/Users/jadelezzi/Documents/GitHub/Hackathon_AX_BroadwAI')
DIST=Path('/private/tmp/kiosque-marketing/dist')
DATA=Path('/private/tmp/kiosque-marketing')
cover=json.loads((DATA/'edition.json').read_text())
cover.update(user_id='local-marketing-demo', diagnostics={}, usage={}, trace=[])
saved=[]

def saved_data():
    return {'article_ids':saved,'items':[dict(i,cover_id=cover['id']) for i in cover['items'] if i['article_id'] in saved]}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,data,typ='application/json',status=200):
        if typ=='application/json': data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/health': return self.send({'status':'ok','llm_configured':True})
        if path=='/v1/covers': return self.send([{k:cover[k] for k in ('id','title','created_at','status')}|{'item_count':len(cover['items'])}])
        if path.startswith('/v1/covers/'): return self.send(cover)
        if path=='/v1/likes': return self.send({'article_ids':[]})
        if path=='/v1/saved-articles': return self.send(saved_data())
        if path=='/v1/archives': return self.send([{k:cover[k] for k in ('id','title','created_at','status')}|{'item_count':len(cover['items']),'artwork':{'photos':[i['article_id'] for i in cover['items'] if i.get('image')][:3], 'sections':list(dict.fromkeys(i['section'] for i in cover['items']))[:3],'palette':0}}])
        if path.startswith('/v1/collections') or path.startswith('/v1/readers/'): return self.send([])
        if path.startswith('/v1/articles/') and path.endswith('/image'):
            cache=DATA/(path.split('/')[3]+'.image')
            try:
                if not cache.exists():
                    with urlopen('http://127.0.0.1:8010'+self.path,timeout=40) as r: cache.write_bytes(r.read())
                return self.send(cache.read_bytes(),'image/jpeg')
            except Exception: return self.send({},status=404)
        if path in ('/','/index.html','/setup'):
            html=(DIST/'index.html').read_text()
            bootstrap="""<script>
            localStorage.setItem('kiosque.accounts.v1',JSON.stringify([{id:'local-marketing-demo',name:'Camille',email:'camille@example.test'}]));
            localStorage.setItem('kiosque.session.v1',JSON.stringify('local-marketing-demo'));
            localStorage.setItem('kiosque.colorMode.v1',JSON.stringify('dark'));
            localStorage.setItem('kiosque.theme.v1',JSON.stringify('minimal'));
            if(location.pathname==='/setup') { localStorage.removeItem('kiosque.reader.v1:local-marketing-demo'); localStorage.removeItem('kiosque.lastCover:local-marketing-demo'); }
            else { localStorage.setItem('kiosque.reader.v1:local-marketing-demo', JSON.stringify({name:'Camille',topics:['gaming','climate','world','culture'],notes:'Comprendre le monde et découvrir de nouvelles idées.',level:'intermediate',languages:['fr','en'],size:18})); localStorage.setItem('kiosque.lastCover:local-marketing-demo',JSON.stringify('COVERID')); }
            </script>""".replace('COVERID',cover['id'])
            return self.send(html.replace('<head>','<head>'+bootstrap).encode(),'text/html; charset=utf-8')
        target=(DIST/path.lstrip('/')).resolve()
        if target.is_relative_to(DIST) and target.is_file(): return self.send(target.read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
        return self.send({},status=404)
    def do_PUT(self):
        path=urlsplit(self.path).path
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        if path.startswith('/v1/saved-articles/'):
            article_id=path.rsplit('/',1)[-1]
            if article_id not in saved: saved.append(article_id)
            return self.send(saved_data())
        return self.send({})
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        return self.send({'detail':'Génération et conversation désactivées pour le tournage.'},status=503)

ThreadingHTTPServer(('127.0.0.1',8031),Handler).serve_forever()
