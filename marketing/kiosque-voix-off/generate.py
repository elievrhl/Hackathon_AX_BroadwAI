"""Generate the approved Kiosque voiceover. Never logs credentials."""

import argparse
import json
import os
from pathlib import Path
import shlex
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
API = "https://api.gradium.ai/api"
VOICE_ID = "WWHSNJCSTm77dyGd"  # Valentin, French stock voice.


def api_key():
    key = os.environ.get("GRADIUM_API_KEY")
    if key:
        return key
    for line in (REPO / ".env").read_text().splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name == "GRADIUM_API_KEY":
            values = shlex.split(value, comments=True)
            if values:
                return values[0]
    raise RuntimeError("GRADIUM_API_KEY is not configured")


def request(path, data=None, content_type="application/json"):
    headers = {"x-api-key": api_key()}
    if data is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(API + path, data=data, headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as exc:
        # Do not log headers, request objects, or authentication material.
        raise RuntimeError(f"Gradium HTTP {exc.code}") from None


def catalog():
    with request("/voices/?include_catalog=true&limit=500") as response:
        voices = json.load(response)
    shortlist = [
        {k: v.get(k) for k in ("uid", "name", "description", "language", "tags")}
        for v in voices
        if v.get("is_catalog") and v.get("language") == "fr"
        and v.get("name") in ("Elise", "Élise", "Valentin", "Camille")
    ]
    (ROOT / "voice-shortlist.json").write_text(json.dumps(shortlist, ensure_ascii=False, indent=2))
    for voice in shortlist:
        print(voice["uid"], voice["name"], voice["description"], flush=True)


def generate(only):
    sections = json.loads((ROOT / "sections.json").read_text())
    raw_dir = ROOT / "sources"
    raw_dir.mkdir(exist_ok=True)
    for i, section in enumerate(sections, 1):
        if only and i not in only:
            continue
        output = raw_dir / (section["id"] + ".wav")
        if output.exists():
            print(f"Already generated: {output.name}", flush=True)
            continue
        payload = {
            "text": section["text"],
            "voice_id": VOICE_ID,
            "output_format": "wav",
            "only_audio": True,
            "model_name": "default",
            "json_config": {"temp": 0.65, "padding_bonus": 0.1, "rewrite_rules": "fr"},
        }
        print(f"Generating {i}/6: {section['title']}", flush=True)
        with request("/post/speech/tts", json.dumps(payload).encode()) as response:
            audio = response.read()
        if not audio.startswith(b"RIFF") or len(audio) < 10000:
            raise RuntimeError("Gradium did not return a valid WAV response")
        output.write_bytes(audio)
        (raw_dir / (section["id"] + ".request.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"Saved {output.name} ({len(audio)} bytes)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("catalog", "generate"))
    parser.add_argument("--only", type=int, nargs="+")
    args = parser.parse_args()
    if args.mode == "catalog":
        catalog()
    else:
        generate(args.only)
