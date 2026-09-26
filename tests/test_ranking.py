from broadwai.models import Interest, Profile
from broadwai.ranking import diversify, rank
from tests.fakes import article


def test_profiles_produce_different_rankings():
    python = article(1, title="Python concurrence et performances").model_copy(
        update={"text": "Python programmation asyncio concurrence"},
    )
    history = article(2, title="Architecture romaine et aqueducs").model_copy(
        update={"text": "Rome architecture romaine aqueducs histoire"},
    )
    first = Profile(user_id="a", interests=[Interest(topic="Python")])
    second = Profile(user_id="b", interests=[Interest(topic="architecture romaine")])
    assert rank([python, history], first)[0].article.id == python.id
    assert rank([python, history], second)[0].article.id == history.id


def test_exclusions_languages_seen_and_diversification():
    articles = [article(1), article(2), article(3)]
    articles[1] = articles[1].model_copy(update={"language": "en"})
    profile = Profile(
        user_id="a",
        interests=[Interest(topic="Python")],
        languages=["fr"],
        seen_article_ids=[articles[0].id],
    )
    ranked = rank(articles, profile)
    assert [r.article.id for r in ranked] == [articles[2].id]
    profile.excluded_sources = [articles[2].source]
    assert rank(articles, profile) == []


def test_similar_titles_are_not_repeated_and_sources_are_capped():
    first = article(1, title="Python annonce une nouvelle version rapide")
    duplicate = article(2, title=first.title)
    another = article(3, title="Python générateurs pour débutants", source=first.source)
    profile = Profile(user_id="a", interests=[Interest(topic="Python")])
    result = diversify(rank([first, duplicate, another], profile), 10, 1)
    assert len(result) <= 2
    assert len({r.article.title for r in result}) == len(result)
    assert len({r.article.source for r in result}) == len(result)


def test_syndicated_body_is_deduplicated_despite_different_titles():
    first = article(1, title="Une analyse Python")
    reprint = article(2, title="Décryptage des systèmes distribués").model_copy(
        update={"text": first.text}
    )
    profile = Profile(user_id="a", interests=[Interest(topic="Python")])
    result = diversify(rank([first, reprint], profile), 10, 3)
    assert len(result) == 1


def test_diversification_tokenizes_each_title_only_once(monkeypatch):
    import broadwai.ranking as ranking

    profile = Profile(user_id="a", interests=[Interest(topic="Python")])
    rows = rank([article(i, title=f"Python angle{i} enjeu{i}") for i in range(100)], profile)
    original, calls = ranking.tokens, []

    def counted(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(ranking, "tokens", counted)
    assert len(diversify(rows, 64, 2)) == 64
    assert len(calls) == 100
