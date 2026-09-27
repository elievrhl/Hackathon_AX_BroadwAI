"""Persistent spend guard for sequential audit processes (including concurrent summaries).

Reserve before dispatch, reconcile only when usage is returned. Unknown/failed calls keep
their reservation. No secrets, prompts, or article text are written to this ledger.
"""

import json
from pathlib import Path
from uuid import uuid4

from broadwai.llm import BudgetExceeded
from broadwai.pricing import RATES


class SpendGuard:
    def __init__(self, path, limit=3.0, ceiling=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(".lock")
        self.lock.touch(exist_ok=False)
        try:
            self.data = (
                json.loads(self.path.read_text())
                if self.path.exists()
                else {
                    "limit_usd": limit,
                    "calls": [],
                }
            )
            if self.data["limit_usd"] != limit:
                raise ValueError("Cannot silently change the approved dollar limit")
            self.ceiling = min(limit, ceiling if ceiling is not None else limit)
            self.save()
        except BaseException:
            self.lock.unlink()
            raise

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def held(self):
        return sum(c["held_usd"] for c in self.data["calls"])

    def reserve(self, kwargs):
        model = kwargs["model"]
        if model not in RATES:
            raise BudgetExceeded("Unknown model price: audit call blocked")
        output = kwargs.get("max_output_tokens")
        if not isinstance(output, int) or not 0 < output <= 16000:
            raise BudgetExceeded("Unbounded output: audit call blocked")
        request = {k: v for k, v in kwargs.items() if k != "text_format"}
        schema = kwargs.get("text_format")
        if schema:
            request["text_format"] = schema.model_json_schema()
        # UTF-8 bytes are a conservative text-token bound; allow serialization overhead.
        inputs = min(400_000, len(json.dumps(request).encode()) * 2 + 8192)
        tool_cost = 0.0
        if kwargs.get("tools"):
            if kwargs.get("max_tool_calls") != 1 or any(
                t["type"] != "web_search" for t in kwargs["tools"]
            ):
                raise BudgetExceeded("Unbounded hosted tools: audit call blocked")
            # Hosted search injects content: reserve the entire documented context window.
            inputs, tool_cost = 400_000, 0.10
        rates = RATES[model]
        upper = 1.2 * ((inputs * rates[0] + output * rates[2]) / 1e6 + tool_cost)
        if self.held + upper > self.ceiling:
            raise BudgetExceeded("Plafond USD partagé de l'audit : appel non envoyé")
        record = {"id": uuid4().hex, "model": model, "held_usd": upper, "status": "reserved"}
        self.data["calls"].append(record)
        self.save()
        return record

    def settle(self, record, response):
        usage = getattr(response, "usage", None)
        if not usage:
            return
        rates = RATES[record["model"]]
        web = sum(
            getattr(item, "type", None) == "web_search_call"
            for item in (getattr(response, "output", None) or [])
        )
        # Ignore input-cache discounts for safety, retain a 20% cushion.
        cost = (usage.input_tokens * rates[0] + usage.output_tokens * rates[2]) / 1e6 + web * 0.01
        record.update(held_usd=cost * 1.2, standard_uncached_usd=cost, status="settled")
        self.save()

    def wrap(self, call):
        async def guarded(**kwargs):
            kwargs["service_tier"] = "default"
            record = self.reserve(kwargs)
            try:
                response = await call(**kwargs)
            except BaseException:
                record["status"] = "unknown_charge"
                self.save()
                raise
            self.settle(record, response)
            return response

        return guarded

    def attach(self, model):
        if str(model.client.base_url) != "https://api.openai.com/v1/":
            raise ValueError("Audit allows only the standard OpenAI API endpoint")
        model.client.responses.parse = self.wrap(model.client.responses.parse)
        model.client.responses.create = self.wrap(model.client.responses.create)

    def close(self):
        self.save()
        self.lock.unlink()
