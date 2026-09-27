"""Original upbeat Kiosque score, fitted to the supplied 74.48-second picture."""
from pathlib import Path
import math, json, re, subprocess, wave
import numpy as np

ROOT=Path(__file__).resolve().parent
SR=48000
START=14.0
PICTURE_END=74.48
DURATION=PICTURE_END-START
# 26 bars land exactly on the closing title at 66.60 s. The full groove
# enters on bar 3 at 20.069 s, beside the beginning of the product narration.
BAR=(66.60-START)/26
BEAT=BAR/4
BPM=60/BEAT
N=round(DURATION*SR)
RNG=np.random.default_rng(270920262)
FFMPEG='/opt/homebrew/bin/ffmpeg'
STEMS={k:np.zeros((N,2),np.float32) for k in ['keys','guitar','bass','drums','shaker','air','hook']}

def hz(note): return 440*2**((note-69)/12)
def times(duration): return np.arange(round(duration*SR))/SR
def add(name,sound,start,level,pan=0):
    offset=round(start*SR)
    if offset<0: sound=sound[-offset:];offset=0
    count=min(len(sound),N-offset)
    if count<=0:return
    theta=(pan+1)*math.pi/4
    s=np.asarray(sound[:count]*level,np.float32)
    STEMS[name][offset:offset+count,0]+=s*math.cos(theta)
    STEMS[name][offset:offset+count,1]+=s*math.sin(theta)

def noise(duration,lo,hi):
    t=times(duration);x=RNG.normal(size=len(t))
    f=np.fft.rfftfreq(len(x),1/SR)
    filt=(1-np.exp(-(f/lo)**4))*np.exp(-(f/hi)**6)
    x=np.fft.irfft(np.fft.rfft(x)*filt,n=len(x))
    return x/max(1e-8,np.sqrt(np.mean(x*x)))

def keys(note,gate=.27):
    t=times(gate+.65);p=2*np.pi*hz(note)*t
    tone=np.sin(p+.6*np.exp(-t/.16)*np.sin(2*p))
    tone+=.09*np.sin(3.003*p+.3)*np.exp(-t/.19)
    env=(1-np.exp(-t/.005))*np.exp(-t/1.1)*np.exp(-np.maximum(t-gate,0)/.12)
    return tone*env

def guitar(note,gate=.16):
    t=times(gate+.36);f=hz(note)*2**(RNG.uniform(-2,2)/1200)
    signal=np.zeros_like(t)
    for h in range(1,13):
        amplitude=math.sin(np.pi*h*.22)/h**1.1
        signal+=amplitude*np.cos(2*np.pi*f*h*t+RNG.uniform(-.04,.04))*np.exp(-t*(3.2+h*1.5))
    signal+=(.022*RNG.normal(size=len(t)))*np.exp(-t/.009)
    return signal*(1-np.exp(-t/.0015))*np.exp(-np.maximum(t-gate,0)/.04)

def bass(note,gate=.22):
    t=times(gate+.15);f=hz(note)
    p=2*np.pi*f*(t+.00011*(1-np.exp(-t/.008)))
    sig=np.sin(p)+.31*np.sin(2*p)*np.exp(-t/.35)+.14*np.sin(3*p)*np.exp(-t/.18)+.065*np.sin(4*p)*np.exp(-t/.10)
    env=(1-np.exp(-t/.005))*np.exp(-t/.95)*np.exp(-np.maximum(t-gate,0)/.045)
    return np.tanh(sig*1.15)*env

def kick():
    t=times(.39)
    phase=2*np.pi*(51*t+82*.014*(1-np.exp(-t/.014)))
    body=np.sin(phase)*np.exp(-t/.09)*(1-np.exp(-t/.0009))
    click=noise(.39,1900,5400)*np.exp(-t/.0035)*.043
    return body+click

def clap():
    t=times(.22);n=noise(.22,1000,7400);env=np.zeros_like(t)
    for when,amp in [(0,.6),(.010,.8),(.021,1)]:
        u=np.maximum(t-when,0)
        env+=amp*(t>=when)*(1-np.exp(-u/.0006))*np.exp(-u/(.024 if when<.02 else .043))
    return n*env*.46+.17*np.sin(2*np.pi*188*t)*np.exp(-t/.021)

def hat(opened=False):
    duration=.24 if opened else .10;t=times(duration)
    metal=sum(np.sign(np.sin(2*np.pi*f*t)) for f in [423,647,973,1357,1679,2131])/6
    f=np.fft.rfftfreq(len(t),1/SR)
    metal=np.fft.irfft(np.fft.rfft(metal)*(1-np.exp(-(f/5200)**4)),n=len(t))
    sig=.78*noise(duration,6000,13500)+.22*metal
    return sig*(1-np.exp(-t/.0007))*np.exp(-t/(.055 if opened else .015))

def shaker():
    t=times(.082)
    return noise(.082,4900,12400)*(1-np.exp(-t/.006))*np.exp(-t/.014)

def air(note,duration):
    t=times(duration+.65);p=2*np.pi*hz(note)*t
    sig=.7*np.sin(p)+.16*np.sin(p*1.0014)+.14*np.sin(p*.9986+.2)
    env=np.sin(np.minimum(t/.4,1)*np.pi/2)**2*np.exp(-np.maximum(t-duration,0)/.17)
    return sig*env

def hook(note):
    t=times(.88);p=2*np.pi*hz(note)*t
    sig=np.sin(p+.24*np.sin(3*p)*np.exp(-t/.07))+.13*np.sin(2*p)*np.exp(-t/.12)
    return sig*(1-np.exp(-t/.0025))*np.exp(-t/.19)

CHORDS=[
    ([55,59,62,66],40,'Em9'),
    ([55,59,61,66],33,'A13'),
    ([54,57,61,64],38,'Dmaj9'),
    ([54,57,61,62],35,'Bm9'),
]

def chord(start,notes,level=.048,gate=.27):
    for j,n in enumerate(notes):
        add('keys',keys(n,gate),start+j*.006,level,(j-1.5)*.25)

def groove(bar):
    start=bar*BAR
    notes,root,_=CHORDS[(bar//2)%4]
    full=bar>=3
    intensity=.75 if bar<3 else 1
    # A small breathing space before the editor-in-chief sequence.
    if bar==12:intensity=.64
    if bar==25:intensity=.72
    for b,vel in [(0,.88),(.75,.64),(1.5,.78),(2.75,.78),(3.5,.52)]:
        if not full and b not in (0,1.5,2.75):continue
        chord(start+b*BEAT,notes,.050*vel*intensity,.25 if b==0 else .14)
    if full:
        for k,b in enumerate([.5,1.25,2.5,3.25]):
            for j,n in enumerate(notes[1:]):
                add('guitar',guitar(n+12,.11),start+b*BEAT+j*.005,.030*intensity,(-.55,.55)[k%2])
    if bar%2==0:
        for j,n in enumerate(notes[:3]):add('air',air(n-12,BAR*1.8),start,.010,(j-1)*.75)
    bassline=[(0,root,.78,.87),(.75,root,.34,.62),(1.5,root+12,.31,.65),(2,root,.66,.83),(2.75,root+7,.30,.54),(3.5,root+12,.30,.58)]
    if not full:bassline=[(0,root,1.25,.72),(2.5,root,.55,.64)]
    for b,n,gate,v in bassline:add('bass',bass(n,gate*BEAT),start+b*BEAT+.005,.18*v*intensity)
    kicks=[(0,1),(1.75,.74),(2.5,.89)] if bar%2==0 else [(0,1),(1.5,.72),(2,.9),(3.5,.7)]
    if not full:kicks=[(0,.72),(2,.55)]
    if bar in (12,25):kicks=kicks[:2]
    for b,v in kicks:add('drums',kick(),start+b*BEAT,.26*v)
    for b in (1,3):add('drums',clap(),start+b*BEAT+.007,.095*intensity,.06)
    for eighth in range(8):
        if not full and eighth%2==0:continue
        b=eighth/2
        add('drums',hat(opened=(eighth==7 and full and bar%4==3)),start+b*BEAT+(.009 if eighth%2 else 0),(.032 if eighth%2 else .019)*intensity,.28)
    if full:
        for step in range(16):
            if step%4==0:continue
            strength=[.5,.47,.78,.50][step%4]*RNG.uniform(.85,1.1)
            add('shaker',shaker(),start+step*BEAT/4+(.008 if step%2 else 0),.020*strength*intensity,(-.45,.45)[step%2])
    if bar%4==3 and bar not in (11,25):
        add('drums',clap(),start+3.75*BEAT,.022,-.17)

def reverberate(name,wet):
    dry=STEMS[name].copy()
    for time,gain in [(.037,.32),(.067,.24),(.109,.16),(.157,.11),(.231,.065)]:
        n=round(time*SR);STEMS[name][n:]+=dry[:-n,::-1]*(wet*gain)

def write(path,x):
    q=np.round(np.clip(x,-.999999,.999999)*8388607).astype(np.int32)
    packed=np.stack([q&255,(q>>8)&255,(q>>16)&255],axis=-1).astype(np.uint8)
    with wave.open(str(path),'wb') as f:
        f.setparams((2,3,SR,0,'NONE','not compressed'));f.writeframes(packed.tobytes())

def ff(*args):
    return subprocess.run([FFMPEG,'-hide_banner','-nostdin','-y',*map(str,args)],capture_output=True,text=True,check=True)

def measure(path):
    r=ff('-i',path,'-af','loudnorm=I=-17:TP=-1.5:LRA=9:print_format=json','-f','null','-')
    return json.loads(re.findall(r'\{\s*"input_i".*?\}',r.stderr,re.S)[-1])

def main():
    for bar in range(26):groove(bar)
    # Original five-note signature: brief gaps keep the narrator unobstructed.
    for bar in [0,7,15,23]:
        for k,(b,n) in enumerate([(0,76),(.75,78),(1.5,71),(2.75,74),(3.5,76)]):
            add('hook',hook(n),bar*BAR+b*BEAT+.035,.036 if bar==0 else .022,[-.22,.22,0,.30,-.20][k])
    # Reveal: a final groove continues into the Kiosque title, then opens out
    # around the existing E/B/E sonic logo instead of competing with its notes.
    for bar in (26,27):groove(bar)
    for j,n in enumerate([52,55,59,62,66]):
        add('keys',keys(n,1.8),52.6+j*.011,.062,(j-2)*.2)
        add('air',air(n-12,4.6),52.6,.013,(j-2)*.35)
    add('bass',bass(40,1.1),52.6,.17)
    # The source title-card's final E lands at video 71.42 s.
    resolution=71.42-START
    chord(resolution,[52,55,59,64,66],.071,1.65)
    add('bass',bass(40,1.5),resolution,.14)
    for j,n in enumerate([52,55,59]):add('air',air(n,1.7),resolution,.019,(j-1)*.6)
    for track,amount in [('keys',.48),('guitar',.32),('hook',.66),('drums',.08),('air',.3)]:reverberate(track,amount)
    music=sum(STEMS.values())
    t=np.arange(N)/SR
    # No anticipatory riser: the first musical sample belongs to 14.00 s.
    music*=np.minimum(t/.028,1)[:,None]
    fade=np.cos(np.minimum(np.maximum(t-(DURATION-1.4),0)/1.4,1)*np.pi/2)**2
    music*=fade[:,None]
    music*=.78/max(np.abs(music).max(),1e-8)
    raw=ROOT/'composition-brute.wav';write(raw,music)
    clean=ROOT/'composition-equilibree.wav'
    ff('-i',raw,'-af','highpass=f=32,lowpass=f=14500,equalizer=f=300:t=q:w=0.75:g=-1.8,equalizer=f=2100:t=q:w=0.6:g=-2.0','-ar',SR,'-c:a','pcm_s24le',clean)
    initial=measure(clean)
    gain=min(-17-float(initial['input_i']),-2-float(initial['input_tp']))
    out=ROOT/'Kiosque-Impulse-musique-seule.wav'
    ff('-i',clean,'-af',f'volume={gain:.6f}dB','-c:a','pcm_s24le',out)
    ff('-i',out,'-c:a','libmp3lame','-b:a','256k','-metadata','title=Kiosque — Impulse','-metadata','artist=Composition originale pour Kiosque',ROOT/'Kiosque-Impulse-musique-seule.mp3')
    report={'title':'Impulse','original_composition':True,'external_samples':False,'bpm':BPM,'start_in_video':START,'duration_music':DURATION,'video_duration':PICTURE_END,'full_groove_at':START+3*BAR,'closing_title_at':66.6,'closing_resolution_at':71.42,'key':'E Dorian / E minor','loudness':measure(out)}
    (ROOT/'composition.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
