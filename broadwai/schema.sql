-- Initial, repeatable schema. Future changes should be versioned migrations.
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_collected_at ON articles (collected_at DESC);
CREATE TABLE IF NOT EXISTS briefs (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    version TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY(article_id, content_hash, version)
);
CREATE TABLE IF NOT EXISTS covers (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS covers_user_id ON covers(user_id);
-- Paid image decisions are shared by all editions and survive server restarts.
CREATE TABLE IF NOT EXISTS image_reviews (
    cache_key TEXT PRIMARY KEY,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'error')),
    payload JSONB NOT NULL,
    retry_after TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS image_reviews_article ON image_reviews(article_id);
CREATE TABLE IF NOT EXISTS feedback (
    user_id TEXT NOT NULL,
    cover_id TEXT NOT NULL REFERENCES covers(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN
        ('impression', 'open', 'useful', 'already_known', 'not_interested')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, cover_id, article_id, kind)
);

-- Additive admin schema: existing articles/covers remain unchanged.
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('rss', 'hacker_news', 'website')),
    url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    limit_per_source INTEGER NOT NULL CHECK (limit_per_source BETWEEN 1 AND 50),
    last_collected_at TIMESTAMPTZ,
    last_report JSONB,
    UNIQUE(kind, url)
);
-- Upgrade existing installations without changing sources or their article history.
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_kind_check;
ALTER TABLE sources ADD CONSTRAINT sources_kind_check
    CHECK (kind IN ('rss', 'hacker_news', 'website'));
CREATE TABLE IF NOT EXISTS source_articles (
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY(source_id, article_id)
);
CREATE INDEX IF NOT EXISTS source_articles_article ON source_articles(article_id);

CREATE TABLE IF NOT EXISTS source_proposals (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    justification TEXT NOT NULL,
    discovered_from TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected')),
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL
);
ALTER TABLE source_proposals ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'rss'
    CHECK (kind IN ('rss', 'website'));
