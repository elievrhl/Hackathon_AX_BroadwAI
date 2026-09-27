"""Native Kiosque motion design. Pillow/NumPy graphics, FFmpeg MP4 export.

No external generation service. Article photos are reused from the existing
product capture; device and editorial layouts are illustrative promo graphics.
"""
from pathlib import Path
from functools import lru_cache
import argparse
import importlib.util
import math
import shutil
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent
W, H, FPS, DURATION = 1920, 1080, 60, 12
PAPER = (247, 245, 239)
INK = (38, 39, 32)
ACCENT = (164, 59, 43)
MUTED = (109, 110, 100)
LINE = (218, 215, 203)
SERIF = ROOT.parent / "kiosque-title-card/assets/LibreCaslonDisplay-Regular.ttf"
SANS = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
SOURCE = Image.open(ROOT.parent / "kiosque-demo/assets/03-une.png").convert("RGB")
PHOTOS = [SOURCE.crop(box) for box in (
    (36, 334, 526, 554), (554, 346, 966, 527), (1074, 389, 1564, 569)
)]

spec = importlib.util.spec_from_file_location("kiosque_title", ROOT.parent / "kiosque-title-card/render.py")
TITLE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TITLE)


def clamp(v):
    return max(0., min(1., v))


def ease(v):
    return 1 - (1 - clamp(v)) ** 3


def smooth(v):
    v = clamp(v)
    return v * v * (3 - 2 * v)


def lerp(a, b, p):
    return a + (b - a) * p


@lru_cache(maxsize=120)
def font(size, sans=False):
    return ImageFont.truetype(str(SANS if sans else SERIF), round(size))


def text(draw, pos, value, size, fill=INK, sans=False, anchor="lt"):
    draw.text(pos, value, font=font(size, sans), fill=fill, anchor=anchor)


def spaced(draw, pos, value, size=17, tracking=3.2, fill=MUTED):
    x, y = pos
    f = font(size, True)
    for ch in value:
        draw.text((x, y), ch, font=f, fill=fill, anchor="lt")
        x += f.getlength(ch) + tracking


def mark(draw, pos, size=90):
    x, y = pos
    f = font(size)
    baseline = y - f.getbbox("Kiosque", anchor="ls")[1]
    draw.text((x, baseline), "Kiosque", font=f, fill=INK, anchor="ls")
    draw.text((x + f.getlength("Kiosque") - size*.014, baseline), ".", font=f, fill=ACCENT, anchor="ls")


def opacity(layer, alpha):
    if alpha >= .999:
        return layer
    result = layer.copy()
    result.putalpha(result.getchannel("A").point(lambda p: round(p * clamp(alpha))))
    return result


def place(canvas, layer, center, scale=1, angle=0, alpha=1):
    if alpha <= 0 or scale <= 0:
        return
    if abs(scale - 1) > .001:
        layer = layer.resize((max(1, round(layer.width*scale)), max(1, round(layer.height*scale))), Image.Resampling.LANCZOS)
    if abs(angle) > .02:
        layer = layer.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    layer = opacity(layer, alpha)
    canvas.alpha_composite(layer, (round(center[0]-layer.width/2), round(center[1]-layer.height/2)))


@lru_cache(maxsize=25)
def shadow(w, h, radius=24, strength=30):
    layer = Image.new("RGBA", (w+radius*4, h+radius*4))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((radius*2, radius*2, radius*2+w, radius*2+h), radius=12, fill=(*INK, strength))
    return layer.filter(ImageFilter.GaussianBlur(radius))


def reveal(canvas, value, x, y, size, p, fill=INK, sans=False):
    p = clamp(p)
    if not p:
        return
    f = font(size, sans)
    bb = f.getbbox(value, anchor="lt")
    layer = Image.new("RGBA", (math.ceil(f.getlength(value))+18, bb[3]-bb[1]+22))
    d = ImageDraw.Draw(layer)
    text(d, (4, 6 + round((1-ease(p))*layer.height)), value, size, fill, sans)
    if p < .6:
        layer = layer.filter(ImageFilter.GaussianBlur(1.8*(1-p/.6)))
    canvas.alpha_composite(opacity(layer, ease(p)), (round(x), round(y)))


@lru_cache(maxsize=3)
def card(i):
    layer = Image.new("RGBA", (406, 436), (255, 254, 250, 255))
    d = ImageDraw.Draw(layer)
    categories = ["CLIMAT & BIODIVERSITÉ", "SCIENCES & IDÉES", "JEUX VIDÉO & DESIGN"]
    headlines = ["Une planète\nà explorer.", "Des idées\nà découvrir.", "Des mondes\nà imaginer."]
    spaced(d, (0, 4), categories[i], 14, 1.8, ACCENT)
    photo = ImageOps.fit(PHOTOS[i], (406, 220), method=Image.Resampling.LANCZOS)
    layer.paste(photo, (0, 41))
    for n, line in enumerate(headlines[i].split("\n")):
        text(d, (0, 284 + n*49), line, 47)
    d.line((0, 400, 406, 400), fill=LINE, width=1)
    text(d, (0, 415), "Votre sélection, à votre rythme.", 15, MUTED, True)
    return layer


def journal(t):
    canvas = Image.new("RGBA", (W,H), (*PAPER,255))
    d = ImageDraw.Draw(canvas)
    spaced(d, (86, 65), "KIOSQUE / VOTRE JOURNAL PERSONNEL", 17, 2.8)
    phrase = "Vos curiosités. Votre journal."
    x = (W-font(104).getlength(phrase))/2
    reveal(canvas, phrase, x, 132, 104, t/.8)
    py = 302 + 50*(1-ease((t-.15)/1.5))
    page_alpha = ease((t-.15)/.8)
    place(canvas, shadow(1400, 660, 30, 25), (960, py+346), alpha=page_alpha)
    page = Image.new("RGBA", (1400,660), (255,254,250,255))
    pd = ImageDraw.Draw(page)
    pd.rectangle((0,0,1399,659), outline=(226,223,213), width=1)
    mark(pd, (47,29), 90)
    spaced(pd, (1006,62), "UNE SÉLECTION POUR VOUS", 13, 1.5)
    text(pd, (48,134), "Climat, sciences, culture : suivez ce qui vous anime.", 22, MUTED, True)
    pd.line((48,177,1352,177), fill=LINE,width=1)
    place(canvas, page, (960,py+330), alpha=page_alpha)
    destinations = [(511,py+414), (960,py+414), (1409,py+414)]
    starts = [(-310,830), (995,1380), (2240,470)]
    turns = [17,-11,-16]
    for i in range(3):
        p = ease((t-.38-i*.20)/1.55)
        x = lerp(starts[i][0],destinations[i][0],p)
        y = lerp(starts[i][1],destinations[i][1],p) - math.sin(p*math.pi)*100
        scale = .85+.15*p
        theta = turns[i]*(1-p)
        alpha = ease((t-.38-i*.20)/.4)
        place(canvas, shadow(406,436,18,25), (x,y+12), scale,theta,alpha*(1-p))
        place(canvas,card(i),(x,y),scale,theta,alpha)
    return canvas


@lru_cache(maxsize=1)
def mobile_content():
    content = Image.new("RGBA", (450,1400), (*PAPER,255))
    d=ImageDraw.Draw(content)
    text(d,(27,8),"Votre sélection du jour",32)
    text(d,(27,56),"CLIMAT & BIODIVERSITÉ",16,ACCENT,True)
    content.paste(ImageOps.fit(PHOTOS[0],(396,226),method=Image.Resampling.LANCZOS),(27,92))
    text(d,(27,345),"Une planète",51)
    text(d,(27,402),"à explorer.",51)
    text(d,(27,475),"Des histoires qui méritent",22,MUTED,True)
    text(d,(27,508),"toute votre attention.",22,MUTED,True)
    d.line((27,565,423,565),fill=LINE,width=1)
    text(d,(27,589),"JEUX VIDÉO & DESIGN",16,ACCENT,True)
    content.paste(ImageOps.fit(PHOTOS[2],(396,208),method=Image.Resampling.LANCZOS),(27,626))
    text(d,(27,858),"Des mondes",49)
    text(d,(27,914),"à imaginer.",49)
    return content


def device(t):
    w,h=500,1010
    layer=Image.new("RGBA",(w,h))
    d=ImageDraw.Draw(layer)
    d.rounded_rectangle((0,1,498,1008),radius=77,fill=(28,29,28),outline=(130,129,120),width=3)
    d.rounded_rectangle((5,5,494,1004),radius=73,outline=(56,57,53),width=3)
    screen=Image.new("RGBA",(450,954),(*PAPER,255))
    s=ImageDraw.Draw(screen)
    text(s,(27,19),"9:41",18,INK,True)
    for i in range(4):
        s.rounded_rectangle((367+i*6,34-i*4,370+i*6,40),radius=1,fill=INK)
    s.rounded_rectangle((402,24,427,38),radius=4,outline=INK,width=2)
    s.rectangle((406,28,421,34),fill=INK)
    mark(s,(26,85),84)
    text(s,(28,174),"Votre journal personnel",19,MUTED,True)
    text(s,(29,222),"La une",21,ACCENT,True)
    text(s,(127,222),"Climat",21,MUTED,True)
    text(s,(228,222),"Culture",21,MUTED,True)
    text(s,(342,222),"Idées",21,MUTED,True)
    s.line((26,259,424,259),fill=LINE,width=1)
    s.line((26,259,92,259),fill=ACCENT,width=3)
    scroll=round(90*smooth((t-1.4)/2.5))
    body=mobile_content().crop((0,scroll,450,scroll+640))
    screen.alpha_composite(body,(0,284))
    s=ImageDraw.Draw(screen)
    s.rounded_rectangle((139,16,309,54),radius=20,fill=(19,20,19))
    s.ellipse((284,26,298,40),fill=(37,43,46))
    s.rounded_rectangle((153,933,297,940),radius=4,fill=INK)
    mask=Image.new("L",screen.size)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,449,953),radius=53,fill=255)
    screen.putalpha(mask)
    layer.alpha_composite(screen,(25,28))
    return layer


def project_phone(canvas, layer, center, height, yaw, tilt):
    # Project the actual device plane through a perspective camera, then warp
    # its texture with the inverse homography. The entire phone stays in frame.
    sw,sh=layer.size
    corners=np.array([[-sw/2,-sh/2,0],[sw/2,-sh/2,0],[sw/2,sh/2,0],[-sw/2,sh/2,0]],dtype=float)
    ry=math.radians(yaw); rz=math.radians(tilt); rx=math.radians(-4)
    Y=np.array([[math.cos(ry),0,math.sin(ry)],[0,1,0],[-math.sin(ry),0,math.cos(ry)]])
    X=np.array([[1,0,0],[0,math.cos(rx),-math.sin(rx)],[0,math.sin(rx),math.cos(rx)]])
    Z=np.array([[math.cos(rz),-math.sin(rz),0],[math.sin(rz),math.cos(rz),0],[0,0,1]])
    pts=corners@(Z@X@Y).T
    scale=height/sh
    p=np.stack([pts[:,0]*1500/(1500+pts[:,2])*scale+center[0],pts[:,1]*1500/(1500+pts[:,2])*scale+center[1]],axis=1)
    left,top=np.floor(p.min(axis=0)-3).astype(int)
    right,bottom=np.ceil(p.max(axis=0)+3).astype(int)
    dst=p-np.array([left,top])
    src=[(0,0),(sw,0),(sw,sh),(0,sh)]
    matrix=[]; values=[]
    for (x,y),(u,v) in zip(dst,src):
        matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
        values.extend([u,v])
    coeff=np.linalg.solve(np.array(matrix),np.array(values))
    warped=layer.transform((right-left,bottom-top),Image.Transform.PERSPECTIVE,coeff,Image.Resampling.BICUBIC)
    # A narrow dark offset gives the device a visible physical edge during yaw.
    edge=Image.new("RGBA",warped.size,(43,43,39,0))
    edge.putalpha(warped.getchannel("A"))
    canvas.alpha_composite(edge,(left+round(5+abs(yaw)*.16),top+2))
    canvas.alpha_composite(warped,(left,top))


def phone_scene(t):
    canvas=Image.new("RGBA",(W,H),(*PAPER,255))
    d=ImageDraw.Draw(canvas)
    mark(d,(97,70),68)
    reveal(canvas,"Votre journal.",158,345,120,(t-.1)/.85)
    reveal(canvas,"À votre rythme.",158,491,120,(t-.38)/.85,ACCENT)
    reveal(canvas,"Des découvertes choisies pour vous.",164,680,29,(t-.7)/.8,MUTED,True)
    categories=["Climat","Culture","Jeux vidéo"]
    px=164
    for i,label in enumerate(categories):
        p=ease((t-.95-i*.13)/.6)
        width=round(font(21,True).getlength(label))+44
        pill=Image.new("RGBA",(width,48))
        pd=ImageDraw.Draw(pill)
        pd.rounded_rectangle((0,0,width-1,47),radius=24,outline=LINE,width=1)
        text(pd,(22,13),label,21,MUTED,True)
        canvas.alpha_composite(opacity(pill,p),(px,round(768+(1-p)*20)))
        px+=width+12
    p=ease(t/1.1)
    cx=lerp(1460,1330,p)+10*math.sin(t*.75)
    cy=lerp(660,537,p)+9*math.sin(t*1.5)
    h=lerp(800,866,p)
    # Broad soft ground shadow anchors the suspended device.
    shadow_layer=Image.new("RGBA",(700,160))
    ImageDraw.Draw(shadow_layer).ellipse((95,55,605,102),fill=(*INK,30))
    shadow_layer=shadow_layer.filter(ImageFilter.GaussianBlur(24))
    canvas.alpha_composite(opacity(shadow_layer,p),(round(cx-350),902))
    project_phone(canvas,device(t),(cx,cy),h,lerp(-24,10,smooth(t/4.8)),lerp(-8,3,smooth(t/4.8)))
    return canvas


def frame(t):
    if t<4.05:
        return journal(t).convert("RGB")
    if t<4.6:
        a=journal(t)
        b=phone_scene(t-4.05)
        return Image.blend(a,b,smooth((t-4.05)/.55)).convert("RGB")
    if t<8.5:
        return phone_scene(t-4.05).convert("RGB")
    title=TITLE.frame((t-8.5)*2.12+.10)
    if t<8.88:
        return Image.blend(phone_scene(t-4.05).convert("RGB"),title,smooth((t-8.5)/.38))
    return title


def soundtrack(path):
    sr=48000
    stereo=np.zeros((round(DURATION*sr),2),dtype=np.float64)
    rng=np.random.default_rng(56)
    def place(sig,start,pan=0):
        n=round(start*sr); count=min(len(sig),len(stereo)-n)
        stereo[n:n+count,0]+=sig[:count]*math.sqrt((1-pan)/2)
        stereo[n:n+count,1]+=sig[:count]*math.sqrt((1+pan)/2)
    for start,freq,level,pan in [(0.18,329.63,.11,-.2),(1.1,493.88,.095,.2),(1.43,659.25,.07,-.1),(1.76,739.99,.06,.15),(4.45,246.94,.13,-.1),(5.07,493.88,.1,.2),(8.96,329.63,.12,0),(9.99,493.88,.09,-.2),(10.44,659.25,.08,.2)]:
        t=np.arange(round(2.8*sr))/sr
        env=(1-np.exp(-85*t))*np.exp(-1.85*t)
        sig=(np.sin(2*np.pi*freq*t)+.17*np.sin(2*np.pi*2*freq*t))*env*level
        place(sig,start,pan)
    for start,length,level in [(.4,.8,.04),(.75,.85,.035),(1.05,.9,.035),(4.05,.85,.05),(8.5,.6,.035)]:
        t=np.arange(round(length*sr))/sr
        noise=np.convolve(rng.standard_normal(len(t)),np.ones(24)/24,mode="same")
        place(noise*np.sin(np.pi*t/length)**2*level,start)
    t=np.arange(round(11.4*sr))/sr
    envelope=np.minimum(t/1.4,1)*np.minimum((11.4-t)/1.3,1)
    harmony=sum(np.sin(2*np.pi*f*t) for f in (164.81,246.94,329.63))/3
    place(.035*envelope*harmony,.3)
    stereo[-round(.7*sr):]*=np.linspace(1,0,round(.7*sr))[:,None]
    with wave.open(str(path),"wb") as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(sr)
        out.writeframes((np.clip(stereo,-1,1)*32767).astype("<i2").tobytes())


def preview():
    sheet=Image.new("RGB",(1920,1080),PAPER)
    for i,t in enumerate([.7,1.5,3.4,4.8,6.0,7.9,9.05,10.25,11.6]):
        panel=frame(t).resize((640,360),Image.Resampling.LANCZOS)
        sheet.paste(panel,((i%3)*640,(i//3)*360))
    sheet.save(ROOT/"storyboard.jpg",quality=94)
    frame(6.7).save(ROOT/"apercu.png")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--preview",action="store_true")
    args=parser.parse_args()
    preview()
    if args.preview:
        return
    output=ROOT/"Kiosque-motion-design-12s.mp4"
    with tempfile.TemporaryDirectory(prefix="kiosque-motion-") as temp:
        audio=Path(temp)/"sound.wav"
        soundtrack(audio)
        cmd=[FFMPEG,"-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(audio),"-c:v","libx264","-preset","fast","-crf","17","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-t",str(DURATION),"-movflags","+faststart",str(output)]
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            for n in range(FPS*DURATION):
                process.stdin.write(frame(n/FPS).tobytes())
                if n and n%(FPS*2)==0:
                    print(f"Rendu : {n//FPS}/{DURATION} s",flush=True)
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError("FFmpeg export failed")
    subprocess.run([FFMPEG,"-v","error","-y","-i",str(output),"-c:v","copy","-an","-movflags","+faststart",str(ROOT/"Kiosque-motion-design-12s-sans-son.mp4")],check=True)
    print(output,flush=True)


if __name__=="__main__":
    main()
