"""Assemble, level and verify the Kiosque narration without changing its pace."""

import argparse
import csv
import json
import os
import re
import subprocess
import wave
import zipfile

from generate import ROOT

FFMPEG = "/opt/homebrew/bin/ffmpeg"
MASTER = ROOT / "Kiosque-voix-off-Gradium.wav"


def run(*args):
    return subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-y", *map(str, args)], check=True, capture_output=True, text=True)


def loudness(path):
    result = run("-i", path, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-")
    return json.loads(re.findall(r'\{\s*"input_i".*?\}', result.stderr, flags=re.S)[-1])


def wav_bytes(path):
    with wave.open(str(path)) as w:
        assert (w.getframerate(), w.getsampwidth(), w.getnchannels()) == (48000, 2, 1)
        data = w.readframes(w.getnframes())
        return data


def assemble():
    sections = json.loads((ROOT / "sections.json").read_text())
    parts_dir = ROOT / "passages"
    parts_dir.mkdir(exist_ok=True)
    # Preserve the provider's natural breaths and pauses within each paragraph.
    rate = 48000
    gap = bytes(round(rate * .32) * 2)
    lead = bytes(round(rate * .16) * 2)
    assembled = bytearray(lead)
    timing = []
    for i, section in enumerate(sections):
        data = wav_bytes(ROOT / "sources" / (section["id"] + ".wav"))
        start = len(assembled) / (rate * 2)
        assembled.extend(data)
        end = len(assembled) / (rate * 2)
        timing.append({"passage": i+1, "title": section["title"], "start_s": round(start, 3), "end_s": round(end, 3), "duration_s": round(end-start, 3), "file": section["id"] + ".wav"})
        if i < len(sections) - 1:
            assembled.extend(gap)
    raw_master = ROOT / "sources" / "assemblage.wav"
    with wave.open(str(raw_master), "wb") as w:
        w.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        w.writeframes(assembled)
    measured = loudness(raw_master)
    # Constant gain preserves the voice's natural dynamics, leaving peak headroom.
    gain = min(-16 - float(measured["input_i"]), -1.5 - float(measured["input_tp"]))
    filt = f"volume={gain:.5f}dB"
    run("-i", raw_master, "-af", filt, "-ar", rate, "-c:a", "pcm_s16le", MASTER)
    run("-i", MASTER, "-c:a", "libmp3lame", "-b:a", "192k", "-metadata", "title=Kiosque — Voix off", "-metadata", "artist=Voix Valentin / Gradium", ROOT / "Kiosque-voix-off-Gradium.mp3")
    for section in sections:
        filename = section["id"] + ".wav"
        run("-i", ROOT / "sources" / filename, "-af", filt, "-c:a", "pcm_s16le", parts_dir / filename)
    (ROOT / "chapitres.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2))
    with (ROOT / "chapitres.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=timing[0].keys())
        writer.writeheader()
        writer.writerows(timing)
    (ROOT / "script.txt").write_text("\n\n".join(s["text"] for s in sections) + "\n")
    verification = {"duration_s": len(assembled) / (rate * 2), "gain_db": gain, "source_loudness": measured, "final_loudness": loudness(MASTER), "voice": "Valentin", "provider": "Gradium", "sample_rate": rate}
    (ROOT / "verification-audio.json").write_text(json.dumps(verification, indent=2))
    with zipfile.ZipFile(ROOT / "Kiosque-6-passages-WAV.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(parts_dir.glob("*.wav")):
            z.write(path, path.name)
        for name in ("chapitres.csv", "script.txt"):
            z.write(ROOT / name, name)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


def transcribe():
    # QA runs entirely offline, using a separately downloaded public model.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from faster_whisper import WhisperModel

    model = WhisperModel("/private/tmp/kiosque-whisper-base", device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    segments, info = model.transcribe(str(MASTER), language="fr", beam_size=5, word_timestamps=True, condition_on_previous_text=False)
    results = []
    for segment in segments:
        results.append({"start": segment.start, "end": segment.end, "text": segment.text, "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability} for w in segment.words]})
        print(f"{segment.start:.2f}–{segment.end:.2f}: {segment.text}", flush=True)
    (ROOT / "verification-transcription.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    transcript = " ".join(m["text"].strip() for m in results)
    (ROOT / "verification-transcription.txt").write_text(transcript + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("assemble", "transcribe"))
    args = parser.parse_args()
    assemble() if args.mode == "assemble" else transcribe()
