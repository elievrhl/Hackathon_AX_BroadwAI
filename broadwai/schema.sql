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
CREATE TABLE IF NOT EXISTS library_editions (
    user_id TEXT NOT NULL,
    cover_id TEXT NOT NULL REFERENCES covers(id) ON DELETE CASCADE,
    artwork JSONB NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, cover_id)
);
CREATE INDEX IF NOT EXISTS library_editions_recent
    ON library_editions(user_id, saved_at DESC);
CREATE TABLE IF NOT EXISTS article_likes (
    user_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    cover_id TEXT NOT NULL REFERENCES covers(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    liked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, article_id)
);
CREATE INDEX IF NOT EXISTS article_likes_recent ON article_likes(user_id, liked_at DESC);
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
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS comment TEXT NOT NULL DEFAULT '';
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS preference_id TEXT;

CREATE TABLE IF NOT EXISTS reader_preferences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    target_key TEXT NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS reader_preferences_user ON reader_preferences(user_id);
CREATE TABLE IF NOT EXISTS reader_messages (
    user_id TEXT NOT NULL,
    id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, id)
);
CREATE INDEX IF NOT EXISTS reader_messages_recent ON reader_messages(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS reader_preferences_active_target
    ON reader_preferences(user_id, target_key) WHERE payload->>'status' = 'active';

-- Additive admin schema: existing articles/covers remain unchanged.
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('rss', 'hacker_news', 'website', 'podcast')),
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
    CHECK (kind IN ('rss', 'hacker_news', 'website', 'podcast'));
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

-- Article playlists: adding/removing a membership never deletes the catalog article.
CREATE TABLE IF NOT EXISTS article_collections (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 160),
    description TEXT NOT NULL DEFAULT '',
    import_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, import_key)
);
CREATE INDEX IF NOT EXISTS article_collections_user ON article_collections(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS collection_articles (
    collection_id TEXT NOT NULL REFERENCES article_collections(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(collection_id, article_id)
);
-- Retain a migration receipt even when a reader later deletes a migrated collection.
CREATE TABLE IF NOT EXISTS library_collection_migrations (
    user_id TEXT NOT NULL,
    cover_id TEXT NOT NULL,
    PRIMARY KEY(user_id, cover_id)
);
INSERT INTO article_collections (id,user_id,name,created_at,updated_at)
SELECT 'legacy-' || md5(l.user_id || ':' || l.cover_id), l.user_id,
       left(c.payload->>'title',160), l.saved_at, l.saved_at
FROM library_editions l JOIN covers c ON c.id=l.cover_id AND c.user_id=l.user_id
WHERE NOT EXISTS (SELECT 1 FROM library_collection_migrations m
                  WHERE m.user_id=l.user_id AND m.cover_id=l.cover_id)
ON CONFLICT DO NOTHING;
INSERT INTO collection_articles (collection_id,article_id,payload,added_at)
SELECT 'legacy-' || md5(l.user_id || ':' || l.cover_id), item->>'article_id',
       item || jsonb_build_object('cover_id',l.cover_id), l.saved_at
FROM library_editions l JOIN covers c ON c.id=l.cover_id AND c.user_id=l.user_id,
     LATERAL jsonb_array_elements(c.payload->'items') item
WHERE NOT EXISTS (SELECT 1 FROM library_collection_migrations m
                  WHERE m.user_id=l.user_id AND m.cover_id=l.cover_id)
ON CONFLICT DO NOTHING;
INSERT INTO library_collection_migrations (user_id,cover_id)
SELECT user_id,cover_id FROM library_editions ON CONFLICT DO NOTHING;
