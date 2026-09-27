from types import SimpleNamespace

from broadwai.library import artwork


def test_collage_prefers_known_images_deduplicates_and_skips_rejected_images():
    def item(id, image=None, checked=False, section="Culture"):
        return SimpleNamespace(article_id=id, image=image, image_checked=checked, section=section)

    cover = SimpleNamespace(
        id="edition",
        items=[
            item("unknown"),
            item("rejected", checked=True),
            item("photo", image=True, section="Technologie"),
            item("photo", image=True),
            item("other", image=True),
            item("fourth"),
        ],
    )
    result = artwork(cover)
    assert result["photos"] == ["photo", "other", "unknown"]
    assert result["sections"] == ["Culture", "Technologie"]
    assert artwork(cover) == result
    assert artwork(SimpleNamespace(id="empty", items=[]))["photos"] == []
