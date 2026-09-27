"""Local-only filming server. No real accounts, databases or publisher services."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import json, mimetypes

ROOT=Path(__file__).resolve().parent
DIST=ROOT/'site'
EDITION=json.loads((ROOT/'edition-reelle.json').read_text())
IMAGES=json.loads((ROOT/'images-reelles.json').read_text())
ACCOUNT={'id':'marketing-scroll-demo','name':'Camille','email':'camille@example.test','reader_profile':{'name':'Camille','topics':['economy','science','culture','climate','tech','travel'],'notes':'Explorer de nouveaux sujets et comprendre le monde.','level':'intermediate','languages':['fr'],'size':18}}
DAILY={'registered':True,'enabled':True,'status':'ready','cover_id':EDITION['id'],'latest_cover_id':EDITION['id']}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self,data,typ='application/json',status=200):
        if typ=='application/json': data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/health': return self.send({'status':'ok'})
        if path=='/v1/auth/session': return self.send({'account':ACCOUNT,'csrf_token':'local-filming-only'})
        if path=='/v1/covers': return self.send([{k:EDITION[k] for k in ('id','title','created_at','status')}|{'item_count':len(EDITION['items'])}])
        if path.startswith('/v1/covers/'): return self.send(EDITION)
        if path=='/v1/likes': return self.send({'article_ids':[]})
        if path=='/v1/saved-articles': return self.send({'article_ids':[],'items':[]})
        if path.endswith('/daily-edition'): return self.send(DAILY)
        if path.endswith('/regeneration'): return self.send({'available':True,'status':'idle'})
        if path.startswith('/v1/collections') or path.startswith('/v1/readers/') or path=='/v1/archives': return self.send([])
        if path.startswith('/v1/articles/') and path.endswith('/image'):
            artwork=IMAGES.get(path.split('/')[3])
            if not artwork:
                # The real component correctly omits images smaller than 120px.
                return self.send((ROOT/'empty.png').read_bytes(),'image/png')
            return self.send((ROOT/artwork['file']).read_bytes(),artwork['mime'])
        if path=='/fonts/caslon.ttf':
            return self.send((ROOT.parent/'kiosque-title-card'/'assets'/'LibreCaslonDisplay-Regular.ttf').read_bytes(),'font/ttf')
        if path in ('/','/index.html'):
            html=(DIST/'index.html').read_text()
            init="""<script>
            localStorage.setItem('kiosque.theme.v1',JSON.stringify('editorial'));
            localStorage.setItem('kiosque.colorMode.v1',JSON.stringify('light'));
            </script>
            <style>@font-face{font-family:'Libre Caslon Display';src:url('/fonts/caslon.ttf') format('truetype');font-weight:400;font-style:normal;font-display:block}</style>
            """
            return self.send(html.replace('<head>','<head>'+init).encode(),'text/html; charset=utf-8')
        target=(DIST/path.lstrip('/')).resolve()
        if target.is_relative_to(DIST) and target.is_file(): return self.send(target.read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
        return self.send({'detail':'Not found'},status=404)

    def do_PUT(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        if self.path.endswith('/daily-edition'): return self.send(DAILY)
        return self.send({})

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        return self.send({})


if __name__=='__main__':
    print('Filming fixture available at http://127.0.0.1:8034',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8034),Handler).serve_forever()
