"""Extract readable text and retain the links inside that content for source attribution."""

from urllib.parse import urljoin

import trafilatura
from lxml.etree import strip_tags
from trafilatura.xml import xmltotxt

from broadwai.models import ArticleLink
from broadwai.network import RetrievalError, validate_destination


def extract_content(html, url: str) -> tuple[str, list[ArticleLink]]:
    document = trafilatura.bare_extraction(
        html, url=url, include_comments=False, include_tables=True, include_links=True
    )
    if document is None:
        return "", []
    links = []
    seen = set()
    # Inspect the cleaned article body, not navigation or recommendations in the raw page.
    for ref in document.body.iter("ref"):
        href = ref.get("target", "")
        if not href or href.startswith("#"):
            continue
        try:
            target = validate_destination(urljoin(url, href))
        except (ValueError, RetrievalError):
            continue
        label = " ".join(ref.itertext()).strip()
        if not label or len(target) > 2000 or target in seen or target == url:
            continue
        links.append(ArticleLink(label=label[:500], url=target))
        seen.add(target)
        if len(links) == 40:
            break
    # Keep the original prose readable and quoteable; send URLs as separate context.
    strip_tags(document.body, "ref")
    return xmltotxt(document.body, include_formatting=False), links
