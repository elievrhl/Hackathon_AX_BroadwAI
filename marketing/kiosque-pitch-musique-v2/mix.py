"""Fit the original score beneath the existing voice without changing picture."""
from pathlib import Path
import json, re, subprocess

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/jadelezzi/Desktop/Anki_AI/WhatsApp Video 2026-09-27 at 22.55.49.mp4')
FFMPEG='/opt/homebrew/bin/ffmpeg'

def ff(*args):
    return subprocess.run([FFMPEG,'-hide_banner','-nostdin','-y',*map(str,args)],capture_output=True,text=True,check=True)

def measure(path):
    result=ff('-i',path,'-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-')
    return json.loads(re.findall(r'\{\s*"input_i".*?\}',result.stderr,re.S)[-1])

graph=(
    '[0:a]volume=-3.5dB,asplit=2[voice][control0];'
    '[control0]highpass=f=160,lowpass=f=5200,'
    "volume='if(lt(t,66.3),1,0)':eval=frame[control];"
    '[1:a]adelay=14000|14000,apad=whole_dur=74.48,atrim=end=74.48,'
    "volume='pow(10,(-7+5*clip((t-66.6)/0.65,0,1)-2.5*clip((t-50.8)/0.25,0,1)*clip((57.5-t)/0.25,0,1))/20)':eval=frame[bed];"
    '[bed][control]sidechaincompress=threshold=0.06:ratio=3:attack=20:release=330:'
    'makeup=1:detection=rms:link=average:knee=3,'
    'apad=whole_dur=74.48,atrim=end=74.48,asplit=2[music][bedmix];'
    '[voice][bedmix]amix=inputs=2:normalize=0:duration=longest,'
    'alimiter=limit=0.81283:level=false:latency=true,atrim=end=74.48[mix]'
)
stem=ROOT/'Kiosque-musique-calee-14s.wav'
mix=ROOT/'Kiosque-pitch-mix-final.wav'
ff('-i',ROOT/'son-original.wav','-i',ROOT/'Kiosque-Impulse-musique-seule.wav',
   '-filter_complex',graph,'-map','[music]','-ar','48000','-c:a','pcm_s24le',stem,
   '-map','[mix]','-ar','48000','-c:a','pcm_s24le',mix)
ff('-i',stem,'-c:a','libmp3lame','-b:a','256k',ROOT/'Kiosque-musique-calee-14s.mp3')
output=ROOT/'Kiosque-pitch-avec-musique.mp4'
ff('-i',SOURCE,'-i',mix,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',
   '-b:a','256k','-ar','48000','-t','74.48','-movflags','+faststart',
   '-metadata','title=Kiosque — Pitch avec musique originale',output)
report={'music_start_s':14.0,'picture_copy':True,'voice_and_original_sound_gain_db':-3.5,
        'speech_ducking':{'threshold':.06,'ratio':3,'attack_ms':20,'release_ms':330},
        'closing_music_lift_db':5,'closing_music_lift_start_s':66.6,
        'quieter_voice_passage_extra_music_reduction_db':2.5,
        'mix_loudness':measure(mix),'encoded_loudness':measure(output)}
(ROOT/'mixage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
