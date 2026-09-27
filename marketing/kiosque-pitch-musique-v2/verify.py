from pathlib import Path
import subprocess,json,numpy as np

ROOT=Path(__file__).resolve().parent
ORIGINAL=Path('/Users/jadelezzi/Desktop/Anki_AI/WhatsApp Video 2026-09-27 at 22.55.49.mp4')
OUTPUT=ROOT/'Kiosque-pitch-avec-musique.mp4'

def read(path):
    data=subprocess.check_output(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(path),'-vn','-ar','48000','-ac','2','-f','f32le','-'])
    return np.frombuffer(data,dtype='<f4').reshape(-1,2)

def video_hash(path):
    return subprocess.check_output(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-c','copy','-f','hash','-hash','sha256','-'],text=True).strip()

music=read(ROOT/'Kiosque-musique-calee-14s.wav')
mix=read(ROOT/'Kiosque-pitch-mix-final.wav')
source=read(ROOT/'son-original.wav')
assert len(music)==round(74.48*48000),(len(music),round(74.48*48000))
assert np.max(np.abs(music[:14*48000]))==0
first=float(np.nonzero(np.max(np.abs(music),axis=1)>1e-6)[0][0]/48000)
assert 14<=first<=14.01
n=int(13.9*48000)
intro_error=float(np.max(np.abs(mix[:n]-source[:n]*10**(-3.5/20))))
assert intro_error<1e-6,intro_error
h1,h2=video_hash(ORIGINAL),video_hash(OUTPUT)
assert h1==h2
probe=json.loads(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,duration','-of','json',str(OUTPUT)]))
subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(OUTPUT),'-f','null','-'],check=True,stdout=subprocess.DEVNULL)
sections=[]
for a,b in [(14.45,19),(20.1,29.4),(30.4,39.5),(40.4,49.7),(51.1,56.9),(57.5,65.6),(66.6,73)]:
    start,end=int(a*48000),int(b*48000)
    v=source[start:end]*10**(-3.5/20);m=music[start:end]
    vr=float(20*np.log10(np.sqrt(np.mean(v*v))+1e-12))
    mr=float(20*np.log10(np.sqrt(np.mean(m*m))+1e-12))
    sections.append({'start_s':a,'end_s':b,'original_audio_rms_db':round(vr,2),'music_rms_db':round(mr,2),'original_above_music_db':round(vr-mr,2)})
report={'music_is_silent_before_14s':True,'first_music_sample_s':first,'intro_audio_matches_original_with_gain_only_max_error':intro_error,'picture_bitstream_identical':True,'video_sha256':h1,'full_decode_ok':True,'technical':probe,'levels':sections}
(ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
