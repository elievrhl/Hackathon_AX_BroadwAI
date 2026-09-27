"""Render the two-minute Kiosque marketing film from captured UI and local French TTS.
Run with the bundled Python (Pillow, NumPy), ffmpeg and macOS `say` available.
  python build_video.py --audio
  python build_video.py --preview
  python build_video.py --render
No production writes, network calls or model API calls.
"""
from pathlib import Path
import argparse, json, math, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT/'assets'
WORK = Path('/private/tmp/kiosque-marketing/render')
WORK.mkdir(parents=True, exist_ok=True)
SCENES = json.loads((ROOT/'scenes.json').read_text())
W,H,FPS = 1920,1080,24
BG='#f4f1e8'; INK='#202d29'; RUST='#a34834'; MUTED='#6f766d'; LINE='#d8d4c8'
FONTROOT=Path('/System/Library/Fonts/Supplemental')
def font(size,kind='sans'):
    name={'serif':'Georgia.ttf','italic':'Georgia Italic.ttf','sans':'Arial.ttf','bold':'Arial Bold.ttf'}[kind]
    return ImageFont.truetype(str(FONTROOT/name),size)

def run(args):
    subprocess.run([str(v) for v in args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

def readwav(p):
    with wave.open(str(p),'rb') as f:
        assert f.getframerate()==48000 and f.getsampwidth()==2
        return np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768

def writewav(p,a):
    with wave.open(str(p),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
        f.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())

def srt_time(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def audio():
    full=np.zeros(120*48000);timing=[];start=0
    for si,s in enumerate(SCENES):
        pieces=[]
        for li,text in enumerate(s['lines']):
            stem=WORK/f'voice-{si:02}-{li:02}'
            if not stem.with_suffix('.wav').exists():
                run(['say','-v','Thomas','-r','163','-o',stem.with_suffix('.aiff'),text])
                run(['ffmpeg','-v','error','-y','-i',stem.with_suffix('.aiff'),'-ar','48000','-ac','1',stem.with_suffix('.wav')])
            a=readwav(stem.with_suffix('.wav'))
            # Keep natural intra-sentence pauses; remove only leading/trailing silence.
            nz=np.where(np.abs(a)>0.003)[0]
            if len(nz)==0: raise RuntimeError('Speech service returned empty audio')
            a=a[max(0,nz[0]-2400):min(len(a),nz[-1]+4500)]
            pieces.append(a)
        raw=sum(len(a)/48000 for a in pieces)+0.28*(len(pieces)-1)
        available=s['duration']-1.2
        tempo=max(0.88,raw/available)
        cursor=start+0.6
        for li,(text,a) in enumerate(zip(s['lines'],pieces)):
            p=WORK/f'normal-{si}-{li}.wav';q=WORK/f'fit-{si}-{li}.wav'
            writewav(p,a)
            run(['ffmpeg','-v','error','-y','-i',p,'-af',f'atempo={tempo:.6f}','-ar','48000','-ac','1',q])
            fitted=readwav(q);end=cursor+len(fitted)/48000
            if end>start+s['duration']-0.1: raise RuntimeError('Narration exceeds its scene')
            offset=round(cursor*48000);full[offset:offset+len(fitted)]+=fitted
            timing.append({'scene':si,'start':cursor,'end':end,'text':text})
            cursor=end+0.28/tempo
        print(f'Voice {si+1}/{len(SCENES)}: {raw:.1f}s → {cursor-start:.1f}s, tempo {tempo:.2f}',flush=True)
        start+=s['duration']
    writewav(WORK/'voice-raw.wav',full)
    run(['ffmpeg','-v','error','-y','-i',WORK/'voice-raw.wav','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-ac','1',ROOT/'voix-off.wav'])
    voice=readwav(ROOT/'voix-off.wav')[:120*48000]
    # Original, quiet harmonic bed. No samples or licensed music.
    sr=48000;bed=np.zeros(120*sr)
    chords=[(146.83,220,293.66),(130.81,196,261.63),(174.61,220,349.23),(196,246.94,293.66)]
    for k in range(20):
        t=np.arange(6*sr)/sr;chord=chords[k%4]
        env=np.minimum(t/1.3,1)*np.minimum((6-t)/1.5,1)
        tone=sum(np.sin(2*np.pi*f*t+0.04*np.sin(2*np.pi*0.3*t)) for f in chord)/3
        block=0.011*env*tone
        for j,f in enumerate(chord):
            u=t-(j*1.5+0.4);mask=u>=0
            block[mask]+=0.018*np.exp(-2.4*u[mask])*(np.sin(2*np.pi*f*2*u[mask])+0.25*np.sin(2*np.pi*f*4*u[mask]))
        bed[k*6*sr:(k+1)*6*sr]+=block
    bed[:sr]*=np.linspace(0,1,sr);bed[-2*sr:]*=np.linspace(1,0,2*sr)
    writewav(WORK/'mix.wav',voice+bed)
    (ROOT/'timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2))
    (ROOT/'sous-titres.srt').write_text('\n\n'.join(f'{i+1}\n{srt_time(t["start"])} --> {srt_time(t["end"])}\n{t["text"]}' for i,t in enumerate(timing))+'\n')
    md='# Kiosque — démo marketing de 2 minutes\n\nVoix off française. Captures de l’interface réelle, édition existante.\n\n'
    start=0
    for s in SCENES:
        md+=f'## {start//60:02}:{start%60:02}–{(start+s["duration"])//60:02}:{(start+s["duration"])%60:02} — {s["label"]}\n\n'+' '.join(s['lines'])+'\n\n';start+=s['duration']
    (ROOT/'script-voix-off.md').write_text(md)

CACHE={}
def asset(name,crop=None):
    key=(name,tuple(crop or []))
    if key not in CACHE:
        im=Image.open(ASSETS/name).convert('RGB')
        if crop: im=im.crop(crop)
        CACHE[key]=im
    return CACHE[key]

def text(d,pos,value,size=32,fill=INK,kind='sans',spacing=10):
    d.multiline_text(pos,value,font=font(size,kind),fill=fill,spacing=spacing)

def wrap(value,f,maxw):
    out=[]
    for paragraph in value.split('\n'):
        line=''
        for word in paragraph.split():
            trial=(line+' '+word).strip()
            if f.getlength(trial)>maxw and line:out.append(line);line=word
            else:line=trial
        out.append(line)
    return out

def card(canvas,im,box,progress=0,shadow=True):
    x,y,w,h=box
    # Slow camera movement; the UI itself is not re-created or altered.
    scale=min(w/im.width,h/im.height)*(1+0.007*math.sin(progress*math.pi))
    nw,nh=round(im.width*scale),round(im.height*scale)
    resized=im.resize((nw,nh),Image.Resampling.LANCZOS)
    x=round(x+(w-nw)/2); y=round(y+(h-nh)/2-4*math.sin(progress*math.pi))
    if shadow:
        layer=Image.new('RGBA',(W,H));ld=ImageDraw.Draw(layer)
        ld.rounded_rectangle((x+4,y+14,x+nw+4,y+nh+14),radius=14,fill=(35,32,24,35))
        layer=layer.filter(ImageFilter.GaussianBlur(14));canvas.alpha_composite(layer)
    canvas.paste(resized,(x,y))
    ImageDraw.Draw(canvas).rectangle((x-1,y-1,x+nw,y+nh),outline=LINE,width=1)
    return x,y,nw,nh

TIMING=[]
def frame(si,local,captions=True):
    s=SCENES[si];p=local/s['duration'];absolute=sum(x['duration'] for x in SCENES[:si])+local
    im=Image.new('RGBA',(W,H),BG);d=ImageDraw.Draw(im)
    d.line((88,140,1832,140),fill=LINE,width=2)
    text(d,(90,46),'Kiosque',57,kind='serif');text(d,(90+font(57,'serif').getlength('Kiosque'),46),'.',57,fill=RUST,kind='serif')
    text(d,(1535,68),'LE MONDE, À VOTRE MESURE',16,fill=MUTED)
    style=s['style'];label=s['label']
    if style=='intro':
        text(d,(95,212),label,20,RUST,'bold')
        text(d,(90,295),s['title'],79,kind='serif',spacing=17)
        text(d,(96,646),s['note'],33,fill=MUTED)
        d.ellipse((1300,150,1870,720),fill='#e9ddc9')
        card(im,asset('03-une.png',[0,0,1035,900]),(1095,234,710,620),p)
        d=ImageDraw.Draw(im);d.rectangle((96,760,493,818),fill=RUST)
        text(d,(119,776),'VOTRE JOURNAL PERSONNEL',20,'#ffffff','bold')
    elif style=='outro':
        d.ellipse((1190,210,1790,810),fill='#e6dcc9')
        card(im,asset('09-archives.png',[173,462,478,861]),(1320,252,330,500),p)
        text(d,(96,223),label,20,RUST,'bold')
        text(d,(90,290),s['title'],92,kind='serif',spacing=12)
        text(d,(97,561),'Kiosque.',88,RUST,'serif')
        text(d,(98,701),s['note'],32,fill=INK,spacing=12)
        d.line((98,823,650,823),fill=RUST,width=4)
    else:
        wide=style=='wide'
        left=96; top=215
        text(d,(left,top),label,20,RUST,'bold')
        title=s['title']
        if si==3: title='Votre une,\ncomposée\navec l’IA.'
        if si==5: title='Vos envies\névoluent.\nVotre journal\naussi.'
        text(d,(left,top+63),title,62 if wide else 72,kind='serif',spacing=12)
        bottom=top+63+len(title.split('\n'))*(74 if wide else 84)
        note=s['note']
        note='\n'.join(wrap(note,font(27),470 if wide else 680))
        text(d,(left,bottom+44),note,27,fill=MUTED,spacing=13)
        d.line((left,bottom+23,left+72,bottom+23),fill=RUST,width=4)
        second=bool(s.get('image2') and p>0.55)
        name=s.get('image2') if second else s['image'];crop=s.get('crop')
        if si==4 and 0.25<p<0.56:
            name='04-points.png';crop=[435,40,1165,654]
        if si==6 and second:
            # Two crops from the same archives screenshot keep the book legible.
            card(im,asset(name,[173,462,478,861]),(1110,258,430,563),p)
            text(ImageDraw.Draw(im),(1108,195),'VOS ÉDITIONS, CONSERVÉES',20,RUST,'bold')
        else:
            box={'wide':(614,208,1215,688),'portrait':(1020,177,766,725),'detail':(910,212,895,680),'chat':(854,180,974,728),'themes':(940,181,884,730)}[style]
            card(im,asset(name,crop),box,p)
        if s.get('tag'):
            d=ImageDraw.Draw(im)
            text(d,(630 if wide else 1040,918),s['tag'],16,MUTED)
    d=ImageDraw.Draw(im)
    # Quiet progress rail and captions are separate from the product UI.
    d.rectangle((0,966,W,H),fill=INK)
    if captions:
        subtitle=next((x['text'] for x in TIMING if x['start']<=absolute<x['end']),None)
        if subtitle:
            lines=wrap(subtitle,font(31),1730)
            y=989 if len(lines)==1 else 977
            for line in lines[:2]:
                x=(W-font(31).getlength(line))/2
                text(d,(x,y),line,31,'#fffdf6');y+=40
    d.rectangle((0,1074,round(W*absolute/120),1079),fill=RUST)
    # Paper-colored dissolves avoid harsh cuts and preserve caption contrast.
    edge=min(1,max(0,local/0.38),max(0,(s['duration']-local)/0.38))
    if edge<1:
        blank=Image.new('RGBA',(W,H),BG)
        im=Image.blend(blank,im,edge)
    return im.convert('RGB')

def previews():
    allpics=[]
    for i,s in enumerate(SCENES):
        pic=frame(i,min(3,s['duration']/2),False)
        pic.save(WORK/f'preview-{i}.png')
        allpics.append(pic.resize((640,360)))
    sheet=Image.new('RGB',(1920,1080),BG)
    for i,pic in enumerate(allpics):sheet.paste(pic,((i%3)*640,(i//3)*360))
    sheet.save(ROOT/'storyboard.jpg',quality=90)
    frame(3,7,False).save(ROOT/'apercu.jpg',quality=94)
    print('Previews ready',flush=True)

def render():
    output=ROOT/'Kiosque-demo-marketing-2min.mp4'
    cmd=['ffmpeg','-v','error','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(WORK/'mix.wav'),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-t','120','-movflags','+faststart',str(output)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for i,s in enumerate(SCENES):
        for n in range(s['duration']*FPS):proc.stdin.write(frame(i,n/FPS).tobytes())
        print(f'Rendered scene {i+1}/{len(SCENES)}',flush=True)
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
    print(output,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--audio',action='store_true');parser.add_argument('--preview',action='store_true');parser.add_argument('--render',action='store_true');args=parser.parse_args()
    if args.audio:audio()
    if (ROOT/'timing.json').exists():TIMING=json.loads((ROOT/'timing.json').read_text())
    if args.preview:previews()
    if args.render:render()
