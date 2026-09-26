"""Register real public sources through the admin API, optionally collecting them."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from broadwai.network import PublicFetcher, RetrievalError
from broadwai.retrieval import parse_feed
from broadwai.sources import SourceInput


def main(base_url: str, collect: bool, source_file: Path, limit: int, only_new: bool):
    definitions = [
        SourceInput.model_validate({**item, "limit_per_source": limit})
        for item in json.loads(source_file.read_text(encoding="utf-8"))
    ]
    report = []
    with httpx.Client(base_url=base_url, timeout=180, trust_env=False) as client:
        response = client.get("/v1/sources")
        response.raise_for_status()
        existing = {(s["kind"], s["url"]): s for s in response.json()}
        for definition in definitions:
            source = existing.get((definition.kind, definition.url))
            if source and only_new:
                continue
            if source is None:
                # Do not register broken candidate feeds. This check makes no LLM calls.
                if definition.kind == "rss":
                    try:
                        download = asyncio.run(PublicFetcher().get(definition.url))
                        candidates = parse_feed(download.body, download.url, limit)
                        if not candidates:
                            raise RetrievalError("Flux sans article exploitable")
                    except (RetrievalError, ValueError) as exc:
                        result = {"source": definition.name, "status": "skipped", "error": str(exc)}
                        report.append(result)
                        print(json.dumps(result, ensure_ascii=True), flush=True)
                        continue
                response = client.post("/v1/sources", json=definition.model_dump())
                response.raise_for_status()
                source = response.json()
                existing[(definition.kind, definition.url)] = source
            print(
                json.dumps({"source": source["name"], "id": source["id"]}, ensure_ascii=True),
                flush=True,
            )
            if collect and source["enabled"]:
                response = client.post(f"/v1/sources/{source['id']}/collect")
                response.raise_for_status()
                result = response.json()["results"][0]
                result.pop("article_ids", None)
                report.append(result)
                print(json.dumps(result, ensure_ascii=True), flush=True)
        response = client.get("/health")
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=True))
    Path("data").mkdir(exist_ok=True)
    Path("data/sources-import-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--source-file", type=Path, default=Path("examples/sources.json"))
    parser.add_argument("--limit", type=int, choices=range(1, 51), default=20, metavar="1-50")
    parser.add_argument("--only-new", action="store_true")
    args = parser.parse_args()
    main(args.base_url, args.collect, args.source_file, args.limit, args.only_new)
