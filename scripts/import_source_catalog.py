"""Import checked catalogue entries, with a resumable collection and an append-only report."""

import argparse
import json
import time
from pathlib import Path

import httpx

from scripts.validate_source_catalog import export_sources


def request(client, method, path, **kwargs):
    for attempt in range(4):
        try:
            response = client.request(method, path, **kwargs)
            if response.status_code not in {409, 502, 503, 504}:
                response.raise_for_status()
                return response
            if response.status_code == 409 and "Collecte en cours" not in response.text:
                return response
        except httpx.TransportError:
            if attempt == 3:
                raise
        if attempt < 3:
            time.sleep(2 * (attempt + 1))
    response.raise_for_status()
    return response


def import_catalog(client, catalog, *, collect, report_path):
    definitions = export_sources(catalog)
    rows = request(client, "GET", "/v1/sources").json()
    existing = {(row["kind"], row["url"]): row for row in rows}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as report:
        for definition in definitions:
            key = (definition["kind"], definition["url"])
            source = existing.get(key)
            event = {"name": definition["name"], "url": definition["url"]}
            if source is None:
                response = request(client, "POST", "/v1/sources", json=definition)
                if response.status_code == 409:
                    rows = request(client, "GET", "/v1/sources").json()
                    source = next((row for row in rows if (row["kind"], row["url"]) == key), None)
                    if source is None:
                        response.raise_for_status()
                else:
                    source = response.json()
                existing[key] = source
                event["registered"] = True
            if collect and source["enabled"] and not source.get("article_count", 0):
                result = request(client, "POST", f"/v1/sources/{source['id']}/collect").json()
                event["collection"] = result["results"][0]
                event["collection"].pop("article_ids", None)
            else:
                event["collection_skipped"] = True
            report.write(json.dumps(event, ensure_ascii=False) + "\n")
            report.flush()
            print(json.dumps(event, ensure_ascii=True), flush=True)
    return request(client, "GET", "/v1/sources").json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--catalog", type=Path, default=Path("examples/source-catalog.json"))
    parser.add_argument("--report", type=Path, default=Path("data/catalog-import.jsonl"))
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        rows = import_catalog(client, catalog, collect=args.collect, report_path=args.report)
    snapshot = args.report.with_suffix(".snapshot.json")
    snapshot.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registered_total": len(rows), "snapshot": str(snapshot)}))


if __name__ == "__main__":
    main()
