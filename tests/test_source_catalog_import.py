import json

import httpx

from scripts.import_source_catalog import import_catalog


def test_import_resumes_empty_sources_preserves_paused_and_skips_rejected(tmp_path):
    definitions = [
        {"name": str(i), "kind": "rss", "url": f"https://example.org/{i}"} for i in range(5)
    ]
    catalog = {
        "topics": [{"id": "science"}],
        "sources": [
            {
                "id": str(i),
                "source": definition,
                "topics": ["science"],
                "verification": {"status": "ok" if i < 4 else "failed"},
            }
            for i, definition in enumerate(definitions)
        ],
    }
    rows = [
        {**definitions[i], "id": str(i), "enabled": i != 2, "article_count": 5 if i == 0 else 0}
        for i in range(3)
    ]
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=rows)
        if request.url.path == "/v1/sources":
            definition = json.loads(request.content)
            row = {**definition, "id": "3", "article_count": 0}
            rows.append(row)
            return httpx.Response(201, json=row)
        id_ = request.url.path.split("/")[-2]
        next(row for row in rows if row["id"] == id_)["article_count"] = 5
        return httpx.Response(
            200, json={"results": [{"collected": 5, "errors": [], "article_ids": ["a"]}]}
        )

    report = tmp_path / "report.jsonl"
    with httpx.Client(
        base_url="http://127.0.0.1:8010", transport=httpx.MockTransport(handler)
    ) as client:
        import_catalog(client, catalog, collect=True, report_path=report)
        first_calls = list(calls)
        calls.clear()
        import_catalog(client, catalog, collect=True, report_path=report)
    assert ("POST", "/v1/sources/1/collect") in first_calls
    assert ("POST", "/v1/sources/3/collect") in first_calls
    assert ("POST", "/v1/sources/2/collect") not in first_calls
    assert sum(method == "POST" and path == "/v1/sources" for method, path in first_calls) == 1
    assert all(method == "GET" for method, _ in calls)
    assert len(report.read_text().splitlines()) == 8
