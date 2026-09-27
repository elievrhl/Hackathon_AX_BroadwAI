"""Build the source directory and a portable HTML copy with a live import snapshot."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from broadwai.models import canonical_url

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "broadwai" / "static"


def public_url(value):
    try:
        return canonical_url(value)
    except (ValueError, TypeError, AttributeError):
        return ""


def build_data(catalog, registered, *, generated_at=None):
    live = {(row["kind"], row["url"]): row for row in registered}
    labels = {topic["id"]: topic["label"] for topic in catalog["topics"]}
    entries = list(catalog["sources"])
    keys = {(e["source"]["kind"], e["source"]["url"]) for e in entries}
    for row in registered:
        if (row["kind"], row["url"]) not in keys:
            entries.append(
                {
                    "id": "existing-" + row["id"],
                    "source": row,
                    "topics": [],
                    "languages": [],
                    "selection_reason": "Source déjà présente dans le site avant cette sélection.",
                    "editorial_note": "Source préexistante ; pas évaluée dans cette sélection.",
                    "verification": {"status": "legacy"},
                }
            )
    sources = []
    for entry in entries:
        definition = entry["source"]
        verification = entry.get("verification", {})
        registered_source = live.get((definition["kind"], definition["url"]))
        homepage = public_url(entry.get("homepage_url") or verification.get("feed_homepage"))
        if not homepage and verification.get("sample_urls"):
            example = urlsplit(verification["sample_urls"][0])
            homepage = public_url(f"{example.scheme}://{example.netloc}/")
        if not homepage:
            example = urlsplit(definition["url"])
            homepage = public_url(f"{example.scheme}://{example.netloc}/")
        domain = (urlsplit(homepage).hostname or "").removeprefix("www.")
        publisher = entry.get("publisher_name") or domain
        format_ = (
            "youtube"
            if entry.get("format") == "youtube" or "youtube.com/feeds/" in definition["url"]
            else "podcast"
            if definition["kind"] == "podcast"
            else "article"
        )
        sources.append(
            {
                "id": entry["id"],
                "name": definition["name"],
                "kind": definition["kind"],
                "url": definition["url"],
                "format": format_,
                "publisher": publisher,
                "publisherDomain": domain,
                "homepage": homepage,
                "topics": entry["topics"],
                "topicLabels": [labels[t] for t in entry["topics"]],
                "languages": entry["languages"],
                "description": entry.get("selection_reason", ""),
                "editorialNote": entry.get("editorial_note", ""),
                "accessNote": entry.get("access_note", ""),
                "provenance": public_url(
                    entry.get("provenance_url") or entry.get("discovery_url") or homepage
                ),
                "provenanceNote": entry.get("provenance_note", ""),
                "qualityNotes": entry.get("quality_notes", []),
                "status": verification.get("status", "pending"),
                "selected": (
                    verification.get("status") == "ok"
                    and definition.get("enabled", True)
                    and entry.get("editorial_status") != "excluded"
                ),
                "checkedAt": verification.get("checked_at"),
                "latestAt": verification.get("latest_published_at"),
                "error": verification.get("error", ""),
                "samples": verification.get("sample_urls", []),
                "sampleTitles": {
                    sample["url"]: sample["title"]
                    for sample in entry.get("quality_review", {}).get("sample_titles", [])
                },
                "imported": registered_source is not None,
                "articleCount": registered_source["article_count"] if registered_source else 0,
                "enabled": registered_source["enabled"] if registered_source else False,
            }
        )
    return {
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "topics": catalog["topics"],
        "sources": sources,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--catalog", type=Path, default=ROOT / "examples/source-catalog.json")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    if args.snapshot:
        registered = json.loads(args.snapshot.read_text(encoding="utf-8"))
    else:
        response = httpx.get(args.base_url.rstrip("/") + "/v1/sources", trust_env=False, timeout=30)
        response.raise_for_status()
        registered = response.json()
    data = build_data(catalog, registered)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    js = f"window.SOURCE_DIRECTORY = {encoded};\n"
    (STATIC / "source-directory-data.js").write_text(js, encoding="utf-8")
    html = (STATIC / "sources.html").read_text(encoding="utf-8")
    css = (STATIC / "source-directory.css").read_text(encoding="utf-8")
    script = (STATIC / "source-directory.js").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="/admin/assets/source-directory.css">', f"<style>{css}</style>"
    )
    html = html.replace('<script src="/admin/assets/source-directory-data.js" defer></script>', "")
    html = html.replace('<script src="/admin/assets/source-directory.js" defer></script>', "")
    html = html.replace("</body>", f"<script>{js}</script><script>{script}</script></body>")
    (ROOT / "examples/sources.html").write_text(html, encoding="utf-8")
    print(
        json.dumps(
            {
                "entries": len(data["sources"]),
                "imported": sum(s["imported"] for s in data["sources"]),
                "directory": "/admin/assets/sources.html",
            }
        )
    )


if __name__ == "__main__":
    main()
