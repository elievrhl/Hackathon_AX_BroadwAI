from copy import deepcopy

from scripts.build_source_directory import build_data, public_url


def test_directory_distinguishes_selection_from_live_import_and_keeps_legacy_sources():
    catalog = {
        "topics": [{"id": "science", "label": "Sciences"}],
        "sources": [
            {
                "id": "test",
                "source": {
                    "name": "Science",
                    "kind": "rss",
                    "url": "https://example.org/rss",
                    "enabled": True,
                },
                "topics": ["science"],
                "languages": ["fr"],
                "selection_reason": "Recherche",
                "verification": {"status": "ok", "feed_homepage": "https://example.org/"},
            }
        ],
    }
    rows = [
        {
            "id": "db1",
            "name": "Science",
            "kind": "rss",
            "url": "https://example.org/rss",
            "enabled": False,
            "article_count": 7,
        },
        {
            "id": "db2",
            "name": "Legacy",
            "kind": "rss",
            "url": "https://legacy.example.org/rss",
            "enabled": True,
            "article_count": 3,
            "private_field": "must-not-be-exported",
        },
    ]
    before = deepcopy(catalog)
    data = build_data(catalog, rows, generated_at="2026-09-27T00:00:00Z")
    first, legacy = data["sources"]
    assert first["selected"] and first["imported"] and not first["enabled"]
    assert first["articleCount"] == 7 and first["topicLabels"] == ["Sciences"]
    assert legacy["imported"] and not legacy["selected"] and legacy["status"] == "legacy"
    assert "must-not-be-exported" not in str(data)
    assert catalog == before
    assert not build_data(catalog, [])["sources"][0]["imported"]


def test_directory_links_reject_active_content_and_credentials():
    for url in [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://secret:password@example.org",
        None,
    ]:
        assert public_url(url) == ""
    assert public_url("https://example.org/about") == "https://example.org/about"
