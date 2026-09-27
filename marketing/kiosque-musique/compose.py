"""Original instrumental cue for Kiosque, synthesized locally without samples."""

from pathlib import Path
import json
import math
import re
import subprocess
import wave

import numpy as np

ROOT = Path(__file__).resolve().parent
SR = 48000
BPM = 96
BEAT = 60 / BPM
BAR = BEAT * 4
DURATION = 63.84
N = round(DURATION * SR)
RNG = np.random.default_rng(27092026)
FFMPEG = "/opt/homebrew/bin/ffmpeg"
STEMS = {name: np.zeros((N, 2), dtype=np.float32) for name in ("keys", "pad", "bass", "pluck", "drums")}


def freq(note):
    return 440 * 2 ** ((note - 69) / 12)


def timebase(duration):
    return np.arange(round(duration * SR), dtype=np.float64) / SR


def add(track, sound, start, level, pan=0):
    start = max(0, round(start * SR))
    count = min(len(sound), N - start)
    if count <= 0:
        return
    angle = (pan + 1) * math.pi / 4
    sound = np.asarray(sound[:count] * level, dtype=np.float32)
    STEMS[track][start:start+count, 0] += sound * math.cos(angle)
    STEMS[track][start:start+count, 1] += sound * math.sin(angle)


def band_noise(duration, low, high):
    noise = RNG.normal(size=round(duration * SR))
    bins = np.fft.rfftfreq(len(noise), 1 / SR)
    # Smooth band edges avoid sharp resonances in small percussion sounds.
    highpass = 1 - np.exp(-(bins / low) ** 4)
    lowpass = np.exp(-(bins / high) ** 6)
    result = np.fft.irfft(np.fft.rfft(noise) * highpass * lowpass, n=len(noise))
    return result / max(np.sqrt(np.mean(result * result)), 1e-8)


def electric_piano(note, velocity, gate=2.0):
    t = timebase(gate + 1.4)
    f = freq(note) * 2 ** (RNG.uniform(-1.2, 1.2) / 1200)
    p = 2 * np.pi * f * t
    index = (.32 + velocity * .38) * np.exp(-t / .42)
    tone = np.sin(p + index * np.sin(2*p))
    tone += .12 * np.sin(2.002*p + .12) * np.exp(-t / .72)
    tone += .045 * np.sin(3.99*p) * np.exp(-t / .23)
    attack = 1 - np.exp(-t / .007)
    decay = np.exp(-t / (2.0 - (note-60) * .025))
    release = np.exp(-np.maximum(t - gate, 0) / .37)
    tremolo = .96 + .04 * np.sin(2*np.pi*4.4*t + note)
    return tone * attack * decay * release * tremolo * velocity


def soft_pad(note, duration):
    t = timebase(duration + 1.2)
    f = freq(note)
    drift = .018 * np.sin(2*np.pi*.23*t + note)
    p = 2*np.pi*f*t + drift
    tone = .55*np.sin(p) + .2*np.sin(p*1.0018+.7) + .18*np.sin(p*.9983-.7)
    tone += .055*np.sin(2*p) + .018*np.sin(3*p)
    attack = np.sin(np.minimum(t / 1.0, 1) * np.pi/2)**2
    release = np.exp(-np.maximum(t-duration+.35, 0) / .48)
    return tone * attack * release


def bass(note, gate):
    t = timebase(gate + .20)
    p = 2*np.pi*freq(note)*t
    signal = np.sin(p) + .21*np.sin(2*p)*np.exp(-t/.55) + .035*np.sin(3*p)
    env = (1-np.exp(-t/.015)) * np.exp(-t/2.2) * np.exp(-np.maximum(t-gate, 0)/.065)
    return signal * env


def pluck(note, gate=1.0):
    t = timebase(gate + 1.0)
    p = 2*np.pi*freq(note)*t
    signal = np.sin(p) * np.exp(-t/.78)
    signal += .15*np.sin(2*p+.2)*np.exp(-t/.22)
    signal += .045*np.sin(3*p)*np.exp(-t/.10)
    return signal*(1-np.exp(-t/.004))*np.exp(-np.maximum(t-gate,0)/.28)


def kick():
    t = timebase(.36)
    # Integrated falling pitch; smooth low-frequency pulse.
    phase = 2*np.pi*(49*t + 39*.018*(1-np.exp(-t/.018)))
    return np.sin(phase)*(1-np.exp(-t/.002))*np.exp(-t/.082) + .06*np.sin(2*np.pi*180*t)*np.exp(-t/.011)


def rim():
    t = timebase(.15)
    wood = .58*np.sin(2*np.pi*890*t)*np.exp(-t/.011) + .28*np.sin(2*np.pi*1530*t)*np.exp(-t/.008)
    body = .18*np.sin(2*np.pi*215*t)*np.exp(-t/.027)
    brush = band_noise(.15, 1700, 6900)*np.exp(-t/.020)*.17
    return (wood+body+brush) * (1-np.exp(-t/.0006))


def shaker():
    t = timebase(.10)
    env = (1-np.exp(-t/.004))*np.exp(-t/.019)
    return band_noise(.10, 3400, 10000)*env


# Two-bar harmony: Gmaj9, Em9, Cmaj9, D6/9. Close voice leading avoids
# distracting jumps while extended chords give the cue a gentle, bright color.
CHORDS = [
    ([59, 62, 66, 69], 43, "Gmaj9"),
    ([59, 62, 66, 67], 40, "Em9"),
    ([59, 62, 64, 67], 36, "Cmaj9"),
    ([57, 59, 64, 66], 38, "D6/9"),
]


def arrange():
    for bar in range(24):
        notes, root, _ = CHORDS[(bar // 2) % 4]
        start = bar * BAR
        intensity = .64 if bar < 4 else (.84 if bar < 8 else 1.0)
        if bar >= 20:
            intensity = .72
        hits = [(0, .87)]
        if 4 <= bar < 20:
            hits.append((2.5 if bar % 2 == 0 else 2.75, .43))
        elif bar % 2 == 1 and bar < 20:
            hits.append((2.5, .35))
        for beat, velocity in hits:
            for j, note in enumerate(notes):
                human = RNG.uniform(-.006, .006) if beat else 0
                add("keys", electric_piano(note, velocity * intensity * RNG.uniform(.93, 1.03), gate=1.75),
                    start + beat*BEAT + j*.012 + human, .070, (j-1.5)*.18)

        if bar % 2 == 0:
            for j, note in enumerate(notes[:3]):
                add("pad", soft_pad(note-12, BAR*2), start, .023*intensity, (j-1)*.65)

        if 4 <= bar < 22:
            add("bass", bass(root, BEAT*1.48), start+.007, .105*intensity)
            add("bass", bass(root+12, BEAT*.72), start+BEAT*1.75+.012, .050*intensity)
            add("bass", bass(root, BEAT*1.20), start+BEAT*2.5+.005, .088*intensity)
        elif bar in (0, 2, 22):
            add("bass", bass(root, BEAT*2.5), start, .075)

        if 4 <= bar < 22:
            for b, vel in ((0, 1), (2, .70)):
                add("drums", kick(), start+b*BEAT, .18*vel*intensity)
            if 8 <= bar < 20 and bar % 2:
                add("drums", kick(), start+3.5*BEAT, .07)
            for b in (1, 3):
                add("drums", rim(), start+b*BEAT+.010, .062*intensity, -.13)
            for eighth in range(8):
                swing = .012 if eighth % 2 else 0
                hit = start + eighth*.5*BEAT + swing + RNG.uniform(-.005, .005)
                vel = .020 if eighth % 2 else .012
                add("drums", shaker(), hit, vel*intensity*RNG.uniform(.8,1.15), .28 if eighth%2 else -.23)

    # A sparse original signature, varied across the cue; no continuous lead
    # competing with the narrator's speech.
    motifs = [
        (0, [(0,74), (1.5,78), (3,76), (4.5,71)]),
        (4, [(1,76), (2.5,74), (4.5,71)]),
        (8, [(0,74), (1.5,78), (3,81), (4.5,78), (6,76)]),
        (12, [(1,76), (2.5,79), (4.5,76), (6,74)]),
        (16, [(0,74), (1.5,78), (3,76), (4.5,71)]),
        (20, [(0,76), (2,74), (4.5,71)]),
    ]
    for bar, pattern in motifs:
        for k, (b, note) in enumerate(pattern):
            add("pluck", pluck(note), bar*BAR+b*BEAT+.075, .047*RNG.uniform(.82,1.0), (-.22,.16,.28,-.1)[k%4])

    # Resolve onto Gmaj9 at 60 s, with a clean tail for the closing title.
    for j, note in enumerate((55,59,62,66,69)):
        add("keys", electric_piano(note,.80,gate=2.2),60+j*.019,.065,(j-2)*.15)
    add("bass", bass(43,2.0),60,.073)
    add("pluck", pluck(74,1.3),60.13,.033,.18)
    for j, note in enumerate((55,59,62)):
        add("pad",soft_pad(note,2.0),59.90,.02,(j-1)*.65)


def delay_reverb(track, wet, delay_seconds=.3125):
    dry = track.copy()
    # Staggered, filtered taps give stereo depth without a long muddy wash.
    for delay, gain in ((.071,.22),(.109,.18),(.163,.15),(.229,.12),(.347,.09),(.503,.065),(.719,.035)):
        offset = round(delay*SR)
        track[offset:] += dry[:-offset, ::-1] * (wet*gain)
    for step in range(1,4):
        offset = round(delay_seconds*step*SR)
        track[offset:] += dry[:-offset, ::-1 if step%2 else 1] * (wet*.17*(.43**(step-1)))
    return track


def write_wav(path, signal):
    # 24-bit PCM master; all synthesis and mixing are performed in floating point.
    data = np.round(np.clip(signal,-.999999,.999999)*8388607).astype(np.int32)
    packed = np.stack((data & 255, (data >> 8) & 255, (data >> 16) & 255),axis=-1).astype(np.uint8)
    with wave.open(str(path),"wb") as w:
        w.setparams((2,3,SR,0,"NONE","not compressed"))
        w.writeframes(packed.tobytes())


def ffmpeg(*args):
    return subprocess.run([FFMPEG,"-hide_banner","-nostdin","-y",*map(str,args)],check=True,capture_output=True,text=True)


def measure(path):
    result=ffmpeg("-i",path,"-af","loudnorm=I=-18:TP=-1.5:LRA=9:print_format=json","-f","null","-")
    return json.loads(re.findall(r'\{\s*"input_i".*?\}',result.stderr,re.S)[-1])


def master():
    sources=ROOT/"sources"
    sources.mkdir(exist_ok=True)
    arrange()
    delay_reverb(STEMS["keys"], .72)
    delay_reverb(STEMS["pluck"], .92)
    delay_reverb(STEMS["pad"], .32)
    delay_reverb(STEMS["drums"], .10)
    music=sum(STEMS.values())
    t=np.arange(N)/SR
    # Soft arrival, musical resolution, then a two-second tail fade to silence.
    music *= np.minimum(t/.055,1)[:,None]
    fade=np.cos(np.minimum(np.maximum(t-61.20,0)/(DURATION-61.20),1)*np.pi/2)**2
    music *= fade[:,None]
    peak=float(np.max(np.abs(music)))
    music *= .80 / peak
    raw=sources/"composition.wav"
    write_wav(raw,music)
    filtered=sources/"composition-equilibree.wav"
    ffmpeg("-i",raw,"-af","highpass=f=30,lowpass=f=11500,equalizer=f=260:t=q:w=0.7:g=-1.2","-c:a","pcm_s24le",filtered)
    initial=measure(filtered)
    gain=min(-18-float(initial["input_i"]),-1.5-float(initial["input_tp"]))
    wav=ROOT/"Kiosque-musique-fond.wav"
    ffmpeg("-i",filtered,"-af",f"volume={gain:.6f}dB","-c:a","pcm_s24le",wav)
    ffmpeg("-i",wav,"-c:a","libmp3lame","-b:a","256k","-metadata","title=Kiosque — Curiosité","-metadata","artist=Composition originale pour Kiosque",ROOT/"Kiosque-musique-fond.mp3")
    report={"title":"Curiosité", "duration_seconds":DURATION,"bpm":BPM,"key":"G major","sample_rate":SR,"composition":"Original, locally synthesized, no third-party samples","loudness":measure(wav),"master_gain_db":gain}

    narration=ROOT.parent/"kiosque-voix-off"/"Kiosque-voix-off-Gradium.wav"
    if narration.exists():
        # Leave the original narration and its timing unchanged. The music sits
        # below the speech with a gentle sidechain and a small midrange dip.
        preview=ROOT/"Kiosque-pitch-avec-musique.wav"
        graph=("[0:a]asplit=2[voice][control];"
               "[1:a]volume=-8.5dB,equalizer=f=1900:t=q:w=0.6:g=-2.5[bed];"
               "[bed][control]sidechaincompress=threshold=0.045:ratio=2.3:attack=22:release=360:makeup=1:link=average[ducked];"
               "[voice]pan=stereo|c0=0.70710678*c0|c1=0.70710678*c0[v];"
               "[v][ducked]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.8414:level=false:latency=true[out]")
        ffmpeg("-i",narration,"-i",wav,"-filter_complex",graph,"-map","[out]","-ar",SR,"-c:a","pcm_s24le",preview)
        ffmpeg("-i",preview,"-c:a","libmp3lame","-b:a","256k",ROOT/"Kiosque-pitch-avec-musique.mp3")
        report["mix_loudness"]=measure(preview)
    (ROOT/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    master()
