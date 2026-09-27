"""Assemble a filming selection from real, existing Kiosque article records."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
import io, json, shutil
from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = json.loads((ROOT/'articles-sources.json').read_text())
ORDER = [22,5,8,47,29,45,31,57,32,43,18,26,3,58,17,51,21,28,25,16,12,40,54,49]
SECTIONS = ['Sciences', 'Économie', 'Culture & idées', 'Climat & vivant', 'Tech & IA', 'Jeux vidéo']
CACHE = Path('/private/tmp/kiosque-marketing')
OLD = {i['article_id']:i for i in json.loads((CACHE/'edition.json').read_text())['items']}
(ROOT/'images').mkdir(exist_ok=True)

def get_image(item):
    ident = item['article_id']
    url = item['image']['url']
    dest = ROOT/'images'/f'{ident}.image'
    cached = CACHE/f'{ident}.image'
    try:
        if dest.exists():
            data = dest.read_bytes()
        elif cached.exists() and (OLD.get(ident,{}).get('image') or {}).get('url') == url:
            data = cached.read_bytes()
        else:
            req = Request(url, headers={'User-Agent':'Mozilla/5.0 KiosqueMarketingPreview/1.0'})
            with urlopen(req, timeout=18) as response:
                data = response.read(20_000_001)
            if len(data)>20_000_000: raise ValueError('Image too large')
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width,height = image.size
            mime = Image.MIME[image.format]
        if width<120 or height<90: raise ValueError('Thumbnail too small')
        dest.write_bytes(data)
        print(f'{ident}: {width}x{height}',flush=True)
        return ident, {'file':f'images/{ident}.image','mime':mime,'width':width,'height':height,'source_url':url}
    except Exception as error:
        print(f'{ident}: unavailable ({type(error).__name__}: {error})',flush=True)
        return ident,None

items = []
for number,index in enumerate(ORDER):
    item = dict(SOURCE[index])
    item['original_section'] = item['section']
    item['section'] = SECTIONS[number%6]
    item['format'] = item.get('format') or 'article'
    item['selection_kind'] = 'focused'
    item['role'] = 'lead' if number==0 else 'secondary' if number in (1,2) else None
    items.append(item)
with ThreadPoolExecutor(max_workers=6) as executor:
    images = dict(executor.map(get_image,items))
edition = {'id':'kiosque-marketing-real-selection','user_id':'marketing-scroll-demo',
    'title':'Le monde, au fil de vos curiosités.','created_at':'2026-09-27T19:04:50.240912Z',
    'status':'complete','items':items,'warnings':[],'diagnostics':{}}
(ROOT/'edition-reelle.json').write_text(json.dumps(edition,ensure_ascii=False,indent=2))
(ROOT/'images-reelles.json').write_text(json.dumps(images,ensure_ascii=False,indent=2))
print(f'{len(items)} real contents; {sum(bool(i) for i in images.values())} real images.',flush=True)
