"""Render an 8-second, 60-fps scroll from the actual browser page capture."""
from pathlib import Path
import json, math, subprocess
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parent
W,H,FPS,DURATION=1920,1080,60,8
FFMPEG='/opt/homebrew/bin/ffmpeg'
META=json.loads((ROOT/'capture-metadata.json').read_text())
PAGE=Image.open(ROOT/'page-complete.png').convert('RGB')
assert PAGE.width==W
assert META['scrollEnd']+META['cssHeight']<META['footerTop']-299


def scroll(t):
    """A short settling beat, a smooth acceleration, then continuous motion."""
    hold=.55
    ramp=.85
    u=max(0,t-hold)
    velocity=META['scrollEnd']/(DURATION-hold-ramp/2)
    if u<ramp:
        distance=velocity*(u/2-ramp*math.sin(math.pi*u/ramp)/(2*math.pi))
    else:
        distance=velocity*(u-ramp/2)
    return distance*META['scale']


def pointer():
    scale=4
    im=Image.new('RGBA',(40*scale,49*scale))
    d=ImageDraw.Draw(im)
    points=[(4,3),(4,30),(11,24),(17,37),(22,35),(16,22),(27,21)]
    points=[(x*scale,y*scale) for x,y in points]
    d.polygon(points,fill=(36,37,32,255))
    d.line(points+[points[0]],fill=(255,255,255,245),width=5,joint='curve')
    return im.resize((27,34),Image.Resampling.LANCZOS)


CURSOR=pointer()


def frame(t):
    # A subpixel translation avoids stepping in a 60 fps trackpad-like motion.
    y=scroll(t)
    image=PAGE.transform((W,H),Image.Transform.AFFINE,(1,0,0,0,1,y),resample=Image.Resampling.BICUBIC)
    image=image.convert('RGBA')
    # The pointer stays in the page gutter and never obscures a headline.
    p=min(1,t/1.3)
    ease=p*p*(3-2*p)
    image.alpha_composite(CURSOR,(round(1881-7*ease),round(538+16*ease)))
    return image.convert('RGB')


def preview():
    times=(0,2.5,5,7.983333)
    board=Image.new('RGB',(1280,760),(247,245,239))
    for i,t in enumerate(times):
        shot=frame(t)
        shot.resize((640,360),Image.Resampling.LANCZOS).save(ROOT/f'controle-{i+1}.jpg',quality=94)
        board.paste(shot.resize((640,360),Image.Resampling.LANCZOS),((i%2)*640,(i//2)*380))
    board.save(ROOT/'storyboard.jpg',quality=94)
    frame(0).save(ROOT/'apercu.png')


def render():
    output=ROOT/'Kiosque-vrais-articles-scroll-8s.mp4'
    command=[FFMPEG,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
        for i in range(FPS*DURATION):
            process.stdin.write(frame(i/FPS).tobytes())
            if i%120==0: print(f'{i}/{FPS*DURATION} frames',flush=True)
        process.stdin.close()
        assert process.wait()==0
    music=ROOT.parent/'kiosque-musique'/'Kiosque-musique-fond.wav'
    if music.exists():
        subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(output),'-ss','20','-i',str(music),'-map','0:v:0','-map','1:a:0','-c:v','copy','-af','afade=t=in:st=0:d=0.25,afade=t=out:st=7.65:d=0.35','-c:a','aac','-b:a','192k','-t','8','-movflags','+faststart',str(ROOT/'Kiosque-vrais-articles-scroll-8s-avec-musique.mp4')],check=True)
    last_scroll=scroll((FPS*DURATION-1)/FPS)/META['scale']
    timing={'duration_seconds':DURATION,'fps':FPS,'frames':FPS*DURATION,'width':W,'height':H,'first_scroll_css_px':scroll(0),'last_scroll_css_px':last_scroll,'footer_top_css_px':META['footerTop'],'remaining_content_below_last_frame_css_px':META['footerTop']-last_scroll-META['cssHeight'],'scrolling_at_end':scroll(7.99)>scroll(7.98)}
    assert timing['remaining_content_below_last_frame_css_px']>300
    (ROOT/'scroll-verification.json').write_text(json.dumps(timing,indent=2))
    print(json.dumps(timing,indent=2),flush=True)


if __name__=='__main__':
    preview()
    render()
