"""Conservative sound/image enhancement, with optional subtle camera push.

Keeps the shot, speech, temporal order and approximately 5.43-second duration.
No generated imagery, face changes, frame interpolation, replacement voice or
music. The separate fixed-frame export preserves the original composition.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
SOURCE = ROOT / "source.mp4"
PRE_AUDIO = (
    "highpass=f=75,afftdn=nr=6:nf=-55:tn=1,"
    "atrim=start=0.025,asetpts=PTS-STARTPTS,"
    "equalizer=f=220:t=q:w=0.9:g=-1.7,"
    "equalizer=f=2800:t=q:w=0.8:g=2.3,"
    "equalizer=f=6500:t=q:w=0.8:g=0.8,"
    "acompressor=threshold=0.05:ratio=2.2:attack=14:release=150:makeup=1.4:knee=2.5:detection=rms"
)
GRADE = (
    "hqdn3d=0.85:0.65:1.25:1.0,"
    "colorbalance=rs=0.004:gs=-0.003:bs=0.004:rm=0.005:gm=-0.003:bm=0.008,"
    "eq=contrast=1.035:brightness=0.002:saturation=1.04:gamma=1.01"
)


def run(command):
    return subprocess.run(command, text=True, capture_output=True, check=True)


def probe(path):
    return json.loads(run([FFPROBE,"-v","error","-show_format","-show_streams","-of","json",str(path)]).stdout)


def normalize_measurement(filters):
    result=run([FFMPEG,"-hide_banner","-nostats","-i",str(SOURCE),"-af",filters,"-vn","-f","null","-"])
    return json.loads(re.findall(r'\{\s*"input_i".*?\}',result.stderr,re.S)[-1])


def main():
    metadata=probe(SOURCE)
    duration=float(metadata["format"]["duration"])
    original=normalize_measurement("loudnorm=I=-16:TP=-1.5:LRA=8:print_format=json")
    measured=normalize_measurement(PRE_AUDIO+",loudnorm=I=-16:TP=-1.5:LRA=8:print_format=json")
    norm=(f"loudnorm=I=-16:TP=-1.5:LRA=8:measured_I={measured['input_i']}:"
          f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
          f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
    audio=f"{PRE_AUDIO},{norm},aresample=48000,atrim=duration={duration},asetpts=PTS-STARTPTS"
    # These exports have identical sound processing and color treatment.
    filters={
        "dynamique": GRADE + ",scale=3840:2160:flags=lanczos,"
            "zoompan=z='1+0.035*(on/162)*(on/162)*(3-2*on/162)':"
            "x='iw*0.42-iw/zoom*0.42':y='ih*0.30-ih/zoom*0.30':d=1:s=1920x1080:fps=30,"
            "unsharp=5:5:0.32:3:3:0,setsar=1",
        "cadrage-original": GRADE + ",scale=1920:1080:flags=lanczos,unsharp=5:5:0.32:3:3:0,setsar=1",
    }
    for variant,video in filters.items():
        video += ",setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=limited"
        output=ROOT/f"Kiosque-video-amelioree-{variant}.mp4"
        command=[FFMPEG,"-hide_banner","-loglevel","error","-y","-i",str(SOURCE),
                 "-map","0:v:0","-map","0:a:0","-vf",video,"-af",audio,
                 "-c:v","libx264","-preset","slow","-crf","17","-pix_fmt","yuv420p",
                 "-color_primaries","bt709","-color_trc","bt709","-colorspace","bt709",
                 "-c:a","aac","-b:a","192k","-ar","48000","-t",str(duration),
                 "-movflags","+faststart","-map_metadata","-1"]
        if variant=="cadrage-original":
            command += ["-fps_mode","passthrough"]
        command += [str(output)]
        run(command)
        print(output,flush=True)
    (ROOT/"mesures-source.json").write_text(json.dumps({
        "source": metadata,
        "original_loudness": original,
        "processed_before_normalization": measured,
        "audio_filter":audio,
        "video_filters":filters,
    },indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
