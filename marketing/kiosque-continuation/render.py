"""Build a 10-second photographic animatic, not generated live-action footage.

Image assets were made with the built-in image generator. FFmpeg handles the
camera moves, opening-screen dissolve, shot transitions and existing title.
Run with Python containing NumPy, and FFmpeg installed locally.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

import numpy as np

ROOT = Path(__file__).resolve().parent
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
OUTPUT = ROOT / "Kiosque-suite-animee-10s.mp4"


def soundtrack(path):
    sr = 48000
    duration = 10
    sound = np.zeros((duration * sr, 2), dtype=np.float64)
    rng = np.random.default_rng(31)

    def place(signal, start, pan=0):
        offset = round(start * sr)
        count = min(len(signal), len(sound) - offset)
        sound[offset:offset + count, 0] += signal[:count] * np.sqrt((1 - pan) / 2)
        sound[offset:offset + count, 1] += signal[:count] * np.sqrt((1 + pan) / 2)

    # An original, quiet paper-like sweep accompanies the screen opening.
    t = np.arange(round(0.9 * sr)) / sr
    noise = np.convolve(rng.standard_normal(len(t)), np.ones(22) / 22, mode="same")
    place(0.045 * noise * np.sin(np.pi * t / 0.9) ** 2, 0.52, -0.15)

    # Soft felt-like bell notes, timed to the product and final signature.
    for start, frequency, level, pan in [
        (0.78, 329.63, 0.16, -0.15),
        (1.70, 493.88, 0.12, 0.15),
        (4.62, 659.25, 0.12, -0.08),
        (7.33, 329.63, 0.11, -0.15),
        (7.85, 493.88, 0.10, 0.16),
        (8.30, 659.25, 0.09, 0),
    ]:
        t = np.arange(round(2.9 * sr)) / sr
        envelope = (1 - np.exp(-80 * t)) * np.exp(-1.7 * t)
        tone = (np.sin(2 * np.pi * frequency * t)
                + 0.16 * np.sin(2 * np.pi * frequency * 2 * t)
                + 0.04 * np.sin(2 * np.pi * frequency * 3 * t))
        place(level * tone * envelope, start, pan)

    t = np.arange(round(8.8 * sr)) / sr
    envelope = np.minimum(t / 1.5, 1) * np.minimum((8.8 - t) / 1.5, 1)
    harmony = sum(np.sin(2 * np.pi * f * t) for f in (164.81, 246.94, 329.63)) / 3
    place(0.035 * harmony * envelope, 0.8)
    fade = np.linspace(1, 0, round(0.7 * sr))
    sound[-len(fade):] *= fade[:, None]
    sound = np.clip(sound, -0.95, 0.95)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sr)
        output.writeframes((sound * 32767).astype("<i2").tobytes())


def main():
    with tempfile.TemporaryDirectory(prefix="kiosque-suite-") as temp:
        audio = Path(temp) / "ambiance.wav"
        soundtrack(audio)
        # Both phone frames share a camera move so the app-opening dissolve
        # preserves the handset position. Zoom is computed at 4K for smoothness.
        graph = "\n".join([
            "[0:v]scale=1920:1080,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[a];",
            "[1:v]scale=1920:1080,setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[b];",
            "[a][b]blend=all_expr='A*(1-min(max((T-1.05)/0.45,0),1))+B*min(max((T-1.05)/0.45,0),1)',"
            "scale=3840:2160,zoompan=z='1+0.055*on/125':x='iw*0.60-iw/zoom*0.60':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30,"
            "trim=duration=4.2,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.28,"
            "tpad=start_mode=add:start_duration=0.5:color=black,trim=duration=4.7,settb=AVTB[phone];",
            "[2:v]scale=3840:2160,setsar=1,zoompan=z='1+0.040*on/80':x='iw*0.57-iw/zoom*0.57':y='ih*0.43-ih/zoom*0.43':d=1:s=1920x1080:fps=30,"
            "trim=duration=2.7,setpts=PTS-STARTPTS,format=yuv420p,settb=AVTB[face];",
            "[3:v]setpts=0.3875*(PTS-STARTPTS),fps=30,scale=1920:1080,setsar=1,format=yuv420p,"
            "tpad=stop_mode=clone:stop_duration=0.1,trim=duration=3.1,settb=AVTB[title];",
            "[phone][face]xfade=transition=fade:duration=0.2:offset=4.5[story];",
            "[story][title]xfade=transition=fade:duration=0.3:offset=6.9,trim=duration=10,format=yuv420p[out]",
        ])
        command = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "2"]
        for name in ("plan-telephone-ouverture.png", "plan-telephone-journal.png", "plan-reaction.png"):
            command += ["-loop", "1", "-framerate", "30", "-i", str(ROOT / name)]
        command += ["-i", str(ROOT.parent / "kiosque-title-card/Kiosque-title-card-8s-sans-son.mp4"),
                    "-i", str(audio), "-filter_complex", graph, "-map", "[out]", "-map", "4:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", "10", "-movflags", "+faststart",
                    str(OUTPUT)]
        subprocess.run(command, check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(OUTPUT), "-c:v", "copy", "-an",
                    "-movflags", "+faststart", str(ROOT / "Kiosque-suite-animee-10s-sans-son.mp4")], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "3", "-i", str(OUTPUT), "-frames:v", "1",
                    str(ROOT / "apercu.jpg")], check=True)
    print(OUTPUT, flush=True)


if __name__ == "__main__":
    main()
