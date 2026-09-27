"""Export shareable audit metrics without full articles, credentials or private profiles."""

import argparse
import json
from pathlib import Path


def export_pass(directory):
    results = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    rows = []
    for result in results:
        row = {
            key: result.get(key)
            for key in (
                "profile",
                "id",
                "status",
                "error",
                "count",
                "target",
                "seconds",
                "cost",
                "counts",
                "cache_hits",
                "violations",
                "excerpt_only",
                "uncovered_needs",
            )
        }
        row["source_count"] = len(result.get("sources", {}))
        path = directory / (result["profile"] + ".json")
        if not path.exists():
            path = directory / (result["profile"] + "-error.json")
        if path.exists():
            cover = json.loads(path.read_text(encoding="utf-8"))
            row["readings"] = [
                {
                    "title": item["title"],
                    "url": item["url"],
                    "section": item["section"],
                    "summary": item["brief"]["summary"][:600],
                    "reason": item["reason"],
                    "reading_kind": item.get("reading_kind"),
                    "extraction_status": item.get("extraction_status"),
                    "caveats": item["brief"]["caveats"],
                }
                for item in cover.get("items", [])
            ]
            row["model_usage"] = {}
            for call in cover["usage"].get("model_calls", []):
                usage = row["model_usage"].setdefault(
                    call["kind"], {"calls": 0, "input": 0, "output": 0}
                )
                usage["calls"] += 1
                usage["input"] += (call.get("usage") or {}).get("input_tokens", 0)
                usage["output"] += (call.get("usage") or {}).get("output_tokens", 0)
            events = cover.get("diagnostics", {}).get("events", [])
            row["budget_stops"] = [w for w in cover.get("warnings", []) if "USD" in w]
            row["prepared"] = sum(e["kind"] == "candidate_ready" for e in events)
            row["validation_errors"] = [
                error
                for event in events
                if event["kind"] == "validation"
                for error in event.get("errors", [])
            ]
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(export_pass(args.input), ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
