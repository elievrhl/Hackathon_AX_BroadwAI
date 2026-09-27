"""Validated source definitions shipped with the server, independent of its cwd."""

import json
from importlib.resources import files

from broadwai.sources import SourceInput


def bundled_sources():
    entries = json.loads(files("broadwai").joinpath("source_catalog.json").read_text("utf-8"))
    sources = {}
    for entry in entries:
        source = SourceInput.model_validate(entry)
        if source.enabled:
            sources.setdefault((source.kind, source.url), source.model_dump())
    if not sources:
        raise ValueError("Le catalogue initial des sources est vide")
    return list(sources.values())
