"""Isolated manual UI fixture: python -m tests.serve_feedback_fixture (no paid calls or DB).

Build frontend first, then visit http://127.0.0.1:8012/reader/ .
All data lives only in this test process. It never serves the production port.
"""

import asyncio

import uvicorn

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.models import utcnow
from broadwai.reader_chat import ReaderReply
from tests.fakes import FakeCollector, FakeSearch, MemoryStore, ScriptedModel, article


class ChatFixtureModel(ScriptedModel):
    """Predictable UI exercise only; never used by the production app."""

    async def reader_message(self, state, budget):
        await asyncio.sleep(1)
        message = state["message"].lower()
        if "erreur" in message:
            from broadwai.llm import ModelError

            raise ModelError("Erreur de test")
        old = state["preferences"]
        if "oublie" in message and old:
            return ReaderReply.model_validate(
                {
                    "reply": "C’est noté, je retire cette envie de votre fiche.",
                    "changes": [{"preference_id": old[0]["id"], "preference": None}],
                }
            )
        if "histoire" in message:
            return ReaderReply.model_validate(
                {
                    "reply": "Avec plaisir. Je garde une place pour l’histoire des sciences, "
                    "en complément de vos sujets habituels. "
                    "Cette envie est maintenant dans votre fiche.",
                    "changes": [
                        {
                            "preference_id": next(
                                (p["id"] for p in old if p["target"] == "Histoire des sciences"),
                                None,
                            ),
                            "preference": {
                                "action": "diversify",
                                "target_kind": "topic",
                                "target": "Histoire des sciences",
                                "explanation": "Découvrir les idées et les personnes "
                                "qui ont fait avancer les sciences.",
                                "scope": "persistent",
                            },
                        }
                    ],
                }
            )
        return ReaderReply(reply="Quel sujet aimeriez-vous explorer en particulier ?", changes=[])


store = MemoryStore(
    [
        article(i, title=title).model_copy(update={"image_checked_at": utcnow()})
        for i, title in enumerate(
            [
                "Python : comprendre les interpréteurs",
                "Python : architectures distribuées",
                "Histoire des instruments scientifiques",
                "Python : gérer la mémoire",
                "Python : tester ses applications",
                "Histoire de la mesure du temps",
                "Python : compiler efficacement",
                "Python : concevoir une API",
            ]
        )
    ]
)
app = create_app(
    Settings(_env_file=None, openai_api_key=None, image_review_enabled=False),
    store=store,
    model=ChatFixtureModel(),
    collector=FakeCollector(store),
    search=FakeSearch(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8012)
