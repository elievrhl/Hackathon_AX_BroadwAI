"""Eight-second Kiosque brand reveal, using the product's Libre Caslon Display.

Requires Pillow, NumPy and FFmpeg. Run: python render.py
All animation and sound are generated locally. No external service is called.
"""
from pathlib import Path
from functools import lru_cache
import math
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
W, H, FPS, DURATION = 1920, 1080, 60, 8
PAPER = (247, 245, 239)
INK = (38, 39, 32)
ACCENT = (164, 59, 43)
MUTED = (109, 110, 100)
SERIF = ROOT / "assets/LibreCaslonDisplay-Regular.ttf"
SANS = Path("/System/Library/Fonts/Supplemental/Arial.ttf")


def clamp(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def smooth(x):
    x = clamp(x)
    return x * x * x * (x * (x * 6 - 15) + 10)


@lru_cache(maxsize=None)
def font(size, sans=False):
    return ImageFont.truetype(str(SANS if sans else SERIF), size)


@lru_cache(maxsize=None)
def glyph(char, size, color):
    f = font(size)
    bounds = f.getbbox(char, anchor="ls")
    left, top, right, bottom = bounds
    pad = 22
    layer = Image.new("RGBA", (right - left + pad * 2, bottom - top + pad * 2))
    ImageDraw.Draw(layer).text((pad - left, pad - top), char, font=f, fill=color, anchor="ls")
    return layer, left - pad, top - pad


def fade_layer(layer, opacity):
    if opacity >= 0.999:
        return layer
    layer = layer.copy()
    layer.putalpha(layer.getchannel("A").point(lambda v: round(v * opacity)))
    return layer


@lru_cache(maxsize=None)
def phrase(value, size, color, tracking=0, sans=False):
    f = font(size, sans)
    if tracking:
        width = sum(f.getlength(c) for c in value) + tracking * (len(value) - 1)
    else:
        width = f.getlength(value)
    left, top, right, bottom = f.getbbox(value, anchor="lt")
    pad = 24
    layer = Image.new("RGBA", (math.ceil(width) + pad * 2, bottom - top + pad * 2))
    d = ImageDraw.Draw(layer)
    if tracking:
        x = pad
        for c in value:
            d.text((x, pad - top), c, font=f, fill=color, anchor="lt")
            x += f.getlength(c) + tracking
    else:
        d.text((pad, pad - top), value, font=f, fill=color, anchor="lt")
    return layer


def reveal_phrase(canvas, value, y, t, start, color=INK, size=108, duration=0.8):
    progress = clamp((t - start) / duration)
    if progress == 0:
        return
    layer = phrase(value, size, color)
    travel = round((1 - ease(progress)) * (layer.height + 8))
    # Rise through a fixed clipping mask, like type emerging from the page.
    mask_window = Image.new("RGBA", layer.size)
    mask_window.alpha_composite(layer, (0, travel))
    if progress < 0.55:
        mask_window = mask_window.filter(ImageFilter.GaussianBlur((1 - progress / 0.55) * 2.0))
    mask_window = fade_layer(mask_window, ease(progress))
    canvas.alpha_composite(mask_window, ((W - layer.width) // 2, y))


def frame(t):
    canvas = Image.new("RGBA", (W, H), (*PAPER, 255))
    # The logo becomes a compact masthead before the promise enters beneath it.
    settle = smooth((t - 1.65) / 1.2)
    scale = 1 - 0.25 * settle
    baseline = 604 - 172 * settle
    size = 412
    f = font(size)
    tracking = -0.047 * size
    chars = "Kiosque"
    advances = [f.getlength(c) + tracking for c in chars]
    dot_gap = 9
    dot_radius = 18
    total = sum(advances) - tracking + dot_gap + 2 * dot_radius
    origin = (W - total * scale) / 2
    pen = 0
    for i, c in enumerate(chars):
        progress = clamp((t - 0.12 - i * 0.075) / 0.77)
        if progress > 0:
            layer, ox, oy = glyph(c, size, INK)
            rise = 98 * (1 - ease(progress))
            if progress < 0.65:
                layer = layer.filter(ImageFilter.GaussianBlur((1 - progress / 0.65) * 5))
            layer = fade_layer(layer, smooth(progress))
            target = (max(1, round(layer.width * scale)), max(1, round(layer.height * scale)))
            layer = layer.resize(target, Image.Resampling.LANCZOS)
            canvas.alpha_composite(layer, (round(origin + (pen + ox) * scale), round(baseline + (oy + rise) * scale)))
        pen += advances[i]

    # The terracotta full stop lands last, then stays part of the wordmark.
    dp = clamp((t - 0.82) / 0.68)
    if dp:
        bounce = 1 + 0.22 * math.sin(dp * math.pi) * (1 - dp)
        radius = dot_radius * scale * bounce
        cx = origin + (total - dot_radius) * scale
        cy = baseline - dot_radius * scale - 82 * (1 - ease(dp))
        d = ImageDraw.Draw(canvas)
        color = tuple(round(PAPER[i] + (ACCENT[i] - PAPER[i]) * ease(dp)) for i in range(3))
        d.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=color)

    # A tiny rule grows out from the center; the background remains uniform.
    rule = ease((t - 2.48) / 0.58)
    if rule:
        d = ImageDraw.Draw(canvas)
        d.rectangle((W/2 - 43*rule, 511, W/2 + 43*rule, 514), fill=ACCENT)

    reveal_phrase(canvas, "Moins de bruit.", 548, t, 2.90, INK)
    reveal_phrase(canvas, "Plus de découvertes.", 676, t, 3.82, ACCENT)

    sub = smooth((t - 4.72) / 0.7)
    if sub:
        label = phrase("VOTRE JOURNAL PERSONNEL", 21, MUTED, 4, True)
        label = fade_layer(label, sub)
        canvas.alpha_composite(label, ((W-label.width)//2, round(867 + 8*(1-sub))))
    return canvas.convert("RGB")


def soundtrack(path):
    sr = 48000
    count = DURATION * sr
    stereo = np.zeros((count, 2), dtype=np.float64)
    rng = np.random.default_rng(12)

    def place(signal, start, pan=0.0):
        offset = round(start * sr)
        n = min(len(signal), count-offset)
        stereo[offset:offset+n, 0] += signal[:n] * math.sqrt((1-pan)/2)
        stereo[offset:offset+n, 1] += signal[:n] * math.sqrt((1+pan)/2)

    # A soft, original paper-like sweep follows the opening typography.
    t = np.arange(round(1.45*sr))/sr
    noise = rng.standard_normal(len(t))
    noise = np.convolve(noise, np.ones(14)/14, mode="same")
    place(0.035 * noise * np.sin(np.pi*t/1.45)**2, 0.10, -0.2)

    # Muted impact when the brand's full stop lands.
    t = np.arange(round(0.33*sr))/sr
    strike = (np.sin(2*np.pi*165*t) + 0.22*np.sin(2*np.pi*510*t)) * np.exp(-24*t)
    strike *= np.minimum(t/0.005, 1)
    place(0.16*strike, 1.34, 0.08)

    # Three warm notes articulate the two lines, then resolve into the hold.
    for start, frequency, pan in ((2.95,329.63,-0.2),(3.87,493.88,0.18),(4.82,659.25,0.0)):
        t = np.arange(round(2.6*sr))/sr
        env = np.minimum(t/0.02,1) * np.exp(-2.1*t)
        tone = (np.sin(2*np.pi*frequency*t) + 0.23*np.sin(2*np.pi*frequency*2*t)) * env
        place(0.105*tone, start, pan)

    # Almost imperceptible sustained harmony supports the final reading time.
    t = np.arange(round(4.8*sr))/sr
    envelope = np.minimum(t/1.0,1) * np.minimum((4.8-t)/1.5,1)
    harmony = sum(np.sin(2*np.pi*f*t) for f in (164.81,246.94,329.63))/3
    place(0.03*envelope*harmony, 3.2)
    fade = np.linspace(1,0,round(0.6*sr))
    stereo[-len(fade):] *= fade[:,None]
    peak = np.max(np.abs(stereo))
    stereo *= 0.36 / max(peak, 0.36)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(sr)
        out.writeframes((np.clip(stereo,-1,1)*32767).astype("<i2").tobytes())


def main():
    # Static checkpoints are useful for timing and layout review.
    times = [0.5, 1.4, 2.7, 3.4, 4.25, 5.6]
    sheet = Image.new("RGB", (1920,720), PAPER)
    for i,t in enumerate(times):
        panel = frame(t).resize((640,360), Image.Resampling.LANCZOS)
        sheet.paste(panel, ((i%3)*640, (i//3)*360))
    sheet.save(ROOT/"storyboard.jpg", quality=93)
    frame(6).save(ROOT/"Kiosque-title-card-apercu.png")

    output = ROOT/"Kiosque-title-card-8s.mp4"
    with tempfile.TemporaryDirectory(prefix="kiosque-title-") as tmp:
        sound = Path(tmp)/"sound.wav"
        soundtrack(sound)
        cmd = ["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(sound),"-c:v","libx264","-preset","fast","-crf","17","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-t",str(DURATION),"-movflags","+faststart",str(output)]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for n in range(DURATION*FPS):
            process.stdin.write(frame(n/FPS).tobytes())
            if n and n % (FPS*2) == 0:
                print(f"Animation : {n//FPS}/{DURATION} s", flush=True)
        process.stdin.close()
        if process.wait():
            raise RuntimeError("Video encoding failed")
    subprocess.run(["ffmpeg","-v","error","-y","-i",str(output),"-c:v","copy","-an","-movflags","+faststart",str(ROOT/"Kiosque-title-card-8s-sans-son.mp4")],check=True)
    print(output, flush=True)


if __name__ == "__main__":
    main()
