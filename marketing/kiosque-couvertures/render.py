"""Ten-second original Kiosque cover carousel. Generated art, native typography."""

from pathlib import Path
from functools import lru_cache
import argparse
import json
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent
W, H, FPS, DURATION = 1920, 1080, 60, 10
CW, CH = 520, 754
PAPER = (247, 245, 239)
INK = (38, 39, 32)
ACCENT = (164, 59, 43)
MUTED = (112, 110, 100)
SERIF = ROOT.parent / "kiosque-title-card/assets/LibreCaslonDisplay-Regular.ttf"
SANS = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FFMPEG = "/opt/homebrew/bin/ffmpeg"
SPECS = json.loads((ROOT/"prompts.json").read_text())
THEME_COLORS = [(137, 100, 48),(62, 87, 132),(167, 74, 53),(49, 111, 83),(104, 82, 149),(46, 110, 114)]


def clamp(v):
    return min(1, max(0, v))


def smoother(v):
    v = clamp(v)
    return v*v*v*(v*(v*6-15)+10)


def position(t):
    for i in range(5):
        start = .72 + i*1.6
        if t < start:
            return float(i)
        if t < start+.82:
            return i + smoother((t-start)/.82)
    return 5.


@lru_cache(maxsize=80)
def font(size, sans=False):
    return ImageFont.truetype(str(SANS if sans else SERIF),size)


def tracked(draw, pos, text, size, tracking, fill):
    x,y=pos
    f=font(size,True)
    for char in text:
        draw.text((x,y),char,font=f,fill=fill,anchor="lt")
        x+=f.getlength(char)+tracking
    return x


def wordmark(draw, xy, size, color):
    x,y=xy
    f=font(size)
    draw.text((x,y),"Kiosque",font=f,fill=color,anchor="lt")
    # Align the period to the same baseline as the wordmark.
    baseline=y-f.getbbox("Kiosque",anchor="ls")[1]
    draw.text((x+f.getlength("Kiosque")-.01*size,baseline),".",font=f,fill=ACCENT,anchor="ls")


@lru_cache(maxsize=6)
def cover(i):
    spec=SPECS[i]
    picture=Image.open(ROOT/"assets"/(spec["slug"]+".png")).convert("RGB")
    art=ImageOps.fit(picture,(CW,CH),method=Image.Resampling.LANCZOS).convert("RGBA")
    y=np.arange(CH)/CH
    upper=.47*np.exp(-y/0.145)
    lower=.90*smoother_array(np.maximum(y-.49,0)/.48)
    alpha=np.clip(upper+lower,0,.91)
    shade=Image.new("RGBA",(CW,CH),(13,18,19,255))
    shade.putalpha(Image.fromarray(np.tile((alpha*255).astype(np.uint8)[:,None],(1,CW))))
    art.alpha_composite(shade)
    d=ImageDraw.Draw(art)
    wordmark(d,(29,25),83,(252,249,241))
    d.line((30,126,CW-30,126),fill=(255,250,237,105),width=1)
    tracked(d,(32,145),"L’ENVIE DE DÉCOUVRIR",12,2.0,(251,247,235))
    d.line((32,548,75,548),fill=(255,242,217),width=3)
    tracked(d,(32,570),spec["theme"],19,3.0,(252,246,232))
    for j,line in enumerate(spec["title"].split("\n")):
        assert font(50).getlength(line) <= CW-60, (spec["theme"],line)
        d.text((30,607+j*55),line,font=font(50),fill=(255,252,245),anchor="lt")
    d.rectangle((0,0,CW-1,CH-1),outline=(255,249,233,105),width=1)
    mask=Image.new("L",(CW,CH))
    ImageDraw.Draw(mask).rounded_rectangle((0,0,CW-1,CH-1),radius=5,fill=255)
    art.putalpha(mask)
    return art


def smoother_array(v):
    v=np.clip(v,0,1)
    return v*v*v*(v*(v*6-15)+10)


@lru_cache(maxsize=1)
def background():
    # Quiet paper stage, with a faint warm radial light behind the covers.
    yy,xx=np.mgrid[0:H,0:W]
    glow=np.exp(-(((xx-W*.5)/(W*.7))**2+((yy-H*.4)/(H*.8))**2)*2)
    pixels=np.empty((H,W,3),dtype=np.uint8)
    for c,color in enumerate(PAPER):
        pixels[:,:,c]=np.clip(color-4+glow*5,0,255)
    image=Image.fromarray(pixels).convert("RGBA")
    d=ImageDraw.Draw(image)
    wordmark(d,(86,48),80,INK)
    d.text((W-88,72),"Toutes vos curiosités.",font=font(57),fill=INK,anchor="rt")
    d.line((87,172,W-87,172),fill=(218,215,203),width=1)
    return image


@lru_cache(maxsize=1)
def shadow():
    pad=48
    im=Image.new("RGBA",(CW+pad*2,CH+pad*2))
    ImageDraw.Draw(im).rounded_rectangle((pad,pad+10,pad+CW,pad+CH+10),radius=6,fill=(35,29,20,62))
    return im.filter(ImageFilter.GaussianBlur(21))


def place(canvas, layer, x,y,scale,angle):
    if abs(scale-1)>.0001:
        layer=layer.resize((round(layer.width*scale),round(layer.height*scale)),Image.Resampling.LANCZOS)
    if abs(angle)>.025:
        layer=layer.rotate(angle,Image.Resampling.BICUBIC,expand=True)
    canvas.alpha_composite(layer,(round(x-layer.width/2),round(y-layer.height/2)))


def frame(t):
    canvas=background().copy()
    q=position(t)
    # Keep one neighboring cover visible at each end without suggesting
    # an endless product feed. All six covers occur once, in a finite ribbon.
    x_center=790 + 170*smoother(q/.7) + 170*smoother((q-4.3)/.7)
    elements=[]
    for i in range(6):
        delta=i-q
        x=x_center+delta*625
        if x < -410 or x>W+410:
            continue
        distance=min(abs(delta),2)
        focus=math.exp(-((delta/.90)**2))
        scale=.86+.14*focus
        y=580+26*(1-focus)
        angle=-2.6*max(-1,min(1,delta))
        elements.append((focus,i,x,y,scale,angle))
    for _,i,x,y,scale,angle in sorted(elements):
        place(canvas,shadow(),x,y+8,scale,angle)
        place(canvas,cover(i),x,y,scale,angle)
    d=ImageDraw.Draw(canvas)
    labels=[s["theme"] for s in SPECS]
    widths=[font(16,True).getlength(v)+10 for v in labels]
    gap=42
    x=(W-sum(widths)-gap*5)/2
    for i,(label,width) in enumerate(zip(labels,widths)):
        strength=max(0,1-abs(i-q))
        color=tuple(round(MUTED[c]*(1-strength)+THEME_COLORS[i][c]*strength) for c in range(3))
        d.text((x+width/2,1002),label,font=font(16,True),fill=color,anchor="mt")
        if strength>.02:
            line_y=1032
            half=(width*.50)*strength
            d.line((x+width/2-half,line_y,x+width/2+half,line_y),fill=color,width=2)
        x+=width+gap
    return canvas.convert("RGB")


def preview():
    times=[.30,1.65,3.25,4.85,6.45,8.25]
    board=Image.new("RGB",(1440,670),PAPER)
    d=ImageDraw.Draw(board)
    for index,t in enumerate(times):
        shot=frame(t).resize((464,261),Image.Resampling.LANCZOS)
        col=index%3
        row=index//3
        board.paste(shot,(16+col*477,18+row*335))
        d.text((16+col*477,292+row*335),f"{t:04.2f} s · {SPECS[index]['theme']}",font=font(20,True),fill=INK)
    board.save(ROOT/"storyboard.jpg",quality=94)
    frame(3.25).save(ROOT/"apercu.png")
    covers_dir=ROOT/"couvertures"
    covers_dir.mkdir(exist_ok=True)
    for i,spec in enumerate(SPECS):
        cover(i).save(covers_dir/(spec["slug"]+".png"))


def render():
    output=ROOT/"Kiosque-couvertures-10s.mp4"
    cmd=[FFMPEG,"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-an","-c:v","libx264","-preset","fast","-crf","17","-pix_fmt","yuv420p","-movflags","+faststart",str(output)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as process:
        for index in range(FPS*DURATION):
            process.stdin.write(frame(index/FPS).tobytes())
            if index%120==0:
                print(f"Rendered {index}/{FPS*DURATION} frames",flush=True)
        process.stdin.close()
        assert process.wait()==0
    music=ROOT.parent/"kiosque-musique"/"Kiosque-musique-fond.wav"
    if music.exists():
        subprocess.run([FFMPEG,"-hide_banner","-loglevel","error","-y","-i",str(output),"-ss","53.84","-i",str(music),"-map","0:v:0","-map","1:a:0","-c:v","copy","-af","afade=t=in:st=0:d=0.2,afade=t=out:st=9.5:d=0.5","-c:a","aac","-b:a","192k","-t","10","-movflags","+faststart",str(ROOT/"Kiosque-couvertures-10s-avec-musique.mp4")],check=True)
    print(output,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--preview",action="store_true")
    args=parser.parse_args()
    preview()
    if not args.preview:
        render()
