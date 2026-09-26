from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("postgresql://broadwai:broadwai@localhost:5432/broadwai")
    openai_api_key: SecretStr | None = None
    summary_model: str = ""
    editor_model: str = ""
    image_review_enabled: bool = True
    image_review_model: str = "gpt-5.4-nano"
    web_search_enabled: bool = True
    max_discovered_articles: int = Field(20, ge=0, le=20)
    max_source_proposals: int = Field(2, ge=0, le=5)
    shortlist_size: int = Field(12, ge=1, le=40)
    max_agent_steps: int = Field(6, ge=1, le=12)
    max_summary_calls: int = Field(24, ge=1, le=60)
    max_web_searches: int = Field(2, ge=0, le=5)
    max_fetches: int = Field(24, ge=0, le=40)
    editorial_pool_size: int = Field(96, ge=20, le=150)
    min_editorial_score: int = Field(70, ge=0, le=100)
    max_article_age_days: int = Field(7, ge=1, le=365)
    max_research_age_days: int = Field(365, ge=1, le=3650)
    final_token_reserve: int = Field(30_000, ge=1000, le=100_000)
    max_token_budget: int = Field(500_000, ge=1000, le=1_000_000)
    request_timeout: float = Field(15, gt=0, le=60)
    max_download_bytes: int = Field(2_000_000, ge=1000, le=10_000_000)
    max_article_chars: int = Field(18_000, ge=1000, le=60_000)
    max_catalog_articles: int = Field(3000, ge=10, le=50_000)

    @property
    def llm_ready(self) -> bool:
        return bool(
            self.openai_api_key
            and self.openai_api_key.get_secret_value()
            and self.summary_model
            and self.editor_model
        )
