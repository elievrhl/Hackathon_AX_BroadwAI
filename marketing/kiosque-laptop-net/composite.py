"""Replace only the filmed laptop display with an actual Kiosque UI capture.

Video compositing: subpixel translation tracking, perspective projection,
display luminance matching, antialiased mask and unchanged processed audio.
"""
from pathlib import Path
import json
import math
import subprocess
import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'kiosque-video-amelioree/Kiosque-video-amelioree-cadrage-original.mp4'
FFMPEG='/opt/homebrew/bin/ffmpeg'
W,H,FPS,COUNT=1920,1080,30,163
DURATION=5.43
ROI=(1240,665,500,340)
# Active display only; frame, bezel, camera, keyboard and reflections stay.
CORNERS=np.array([[1303.,712.],[1682.,716.],[1681.,953.],[1288.,931.]])


def track():
    x,y,w,h=ROI
    cmd=[FFMPEG,'-v','error','-i',str(BASE),'-vf',f'fps={FPS},crop={w}:{h}:{x}:{y},scale=250:170','-f','rawvideo','-pix_fmt','gray','-']
    data=subprocess.run(cmd,capture_output=True,check=True).stdout
    frames=np.frombuffer(data,np.uint8).reshape(-1,170,250).astype(np.float32)
    window=np.outer(np.hanning(170),np.hanning(250))
    reference=(frames[0]-frames[0].mean())*window
    fref=np.fft.rfft2(reference)
    shifts=[]
    for frame in frames:
        target=(frame-frame.mean())*window
        cross=np.fft.rfft2(target)*np.conj(fref)
        cross/=np.maximum(np.abs(cross),1e-7)
        corr=np.fft.irfft2(cross,s=target.shape)
        # This locked shot has only subpixel camera drift. Restrict matching
        # to a small region to avoid jumps from changing compressed text.
        ys=np.arange(-5,6);xs=np.arange(-5,6)
        area=corr[ys[:,None]%170,xs[None,:]%250]
        iy,ix=np.unravel_index(np.argmax(area),area.shape)
        yy,xx=int(ys[iy]),int(xs[ix])
        def sub(a,b,c):
            denom=a-2*b+c
            return float(np.clip(.5*(a-c)/denom,-.5,.5)) if abs(denom)>1e-9 else 0.
        dy=sub(corr[(yy-1)%170,xx%250],corr[yy%170,xx%250],corr[(yy+1)%170,xx%250])
        dx=sub(corr[yy%170,(xx-1)%250],corr[yy%170,xx%250],corr[yy%170,(xx+1)%250])
        shifts.append([(xx+dx)*2,(yy+dy)*2])
    shifts=np.array(shifts)
    smooth=shifts.copy()
    for i in range(len(shifts)):
        smooth[i]=np.median(shifts[max(0,i-1):min(len(shifts),i+2)],axis=0)
    print('Suivi écran, déplacement maximal (px) :',np.max(np.abs(smooth),axis=0).round(3).tolist(),flush=True)
    (ROOT/'suivi-ecran.json').write_text(json.dumps({'corners_reference':CORNERS.tolist(),'translations':smooth.tolist(),'fps':FPS},indent=2))
    return smooth


def screen_plate():
    image=Image.open(ROOT/'kiosque-capture-nette.png').convert('RGB')
    # Crop away the unrelated demo-account toolbar; retain the actual journal.
    image=image.crop((0,100,image.width,image.height))
    rgb=np.asarray(image).astype(np.float32)
    # Preserve contrast while matching the lit display's grey floor. The UI
    # stays readable; no invented text or generation is used.
    rgb=np.clip(rgb*.83+np.array([39.,40.,47.]),0,255).astype(np.uint8)
    return Image.fromarray(rgb).convert('RGBA')


def project(plate,shift):
    points=CORNERS+shift
    left,top=np.floor(points.min(axis=0)-3).astype(int)
    right,bottom=np.ceil(points.max(axis=0)+3).astype(int)
    destination=points-np.array([left,top])
    src=[(0,0),(plate.width,0),(plate.width,plate.height),(0,plate.height)]
    matrix=[];values=[]
    for (x,y),(u,v) in zip(destination,src):
        matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
        values.extend([u,v])
    coeff=np.linalg.solve(np.array(matrix),np.array(values))
    projected=plate.transform((right-left,bottom-top),Image.Transform.PERSPECTIVE,coeff,Image.Resampling.BICUBIC)
    # Supersample the quadrilateral's coverage to retain the real bezel edge.
    aa=4
    mask=Image.new('L',((right-left)*aa,(bottom-top)*aa))
    ImageDraw.Draw(mask).polygon([tuple(p*aa) for p in destination],fill=255)
    mask=mask.resize(projected.size,Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(.32))
    projected.putalpha(mask)
    return projected,(left,top)


def preview(plate,shift):
    raw=subprocess.run([FFMPEG,'-v','error','-ss','2.2','-i',str(BASE),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
    frame=Image.frombytes('RGB',(W,H),raw).convert('RGBA')
    old=frame.copy()
    layer,pos=project(plate,shift)
    frame.alpha_composite(layer,pos)
    frame.convert('RGB').save(ROOT/'apercu-ecran-net.png')
    # Close-up is for QA, not a reframing of the delivered clip.
    crop=(1220,670,1740,1000)
    comparison=Image.new('RGB',(1040,330))
    comparison.paste(old.crop(crop).convert('RGB'),(0,0))
    comparison.paste(frame.crop(crop).convert('RGB'),(520,0))
    comparison.save(ROOT/'comparaison-ecran.png')


def render(plate,shifts):
    fixed=ROOT/'Kiosque-laptop-net-cadrage-original.mp4'
    reader=subprocess.Popen([FFMPEG,'-v','error','-i',str(BASE),'-vf',f'fps={FPS}','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE)
    writer=subprocess.Popen([FFMPEG,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
        '-i',str(BASE),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p',
        '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','copy','-t',str(DURATION),'-movflags','+faststart',str(fixed)],stdin=subprocess.PIPE)
    n=0
    try:
        while True:
            data=reader.stdout.read(W*H*3)
            if not data:
                break
            if len(data)!=W*H*3:
                raise RuntimeError('Incomplete video frame')
            frame=Image.frombytes('RGB',(W,H),data).convert('RGBA')
            layer,pos=project(plate,shifts[min(n,len(shifts)-1)])
            frame.alpha_composite(layer,pos)
            writer.stdin.write(frame.convert('RGB').tobytes())
            n+=1
    finally:
        reader.stdout.close();writer.stdin.close()
    if reader.wait() or writer.wait():
        raise RuntimeError('Video export failed')
    dynamic=ROOT/'Kiosque-video-ecran-net.mp4'
    zoom="scale=3840:2160:flags=lanczos,zoompan=z='1+0.035*(on/162)*(on/162)*(3-2*on/162)':x='iw*0.42-iw/zoom*0.42':y='ih*0.30-ih/zoom*0.30':d=1:s=1920x1080:fps=30,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=limited"
    subprocess.run([FFMPEG,'-v','error','-y','-i',str(fixed),'-vf',zoom,'-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-c:a','copy','-t',str(DURATION),'-movflags','+faststart',str(dynamic)],check=True)
    print(dynamic,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    shifts=track();plate=screen_plate()
    preview(plate,shifts[66])
    if not args.preview:
        render(plate,shifts)


if __name__=='__main__':
    main()
