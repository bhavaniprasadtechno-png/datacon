from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    chroma_url: str = "http://localhost:8001"
    chroma_persist_dir: str = "./.chroma"
    query_engine_db_path: str = "./data/snapshot.duckdb"
    # LiteLLM orchestrates the provider call from a single "provider/model"
    # string (SRS §2.2), so swapping providers is a config change, not a
    # code change.
    together_api_key: str | None = None
    llm_model: str = "Qwen/Qwen3.7-Plus"
    internal_auth_token: str = "dev-internal-token"

    @property
    def is_llm_configured(self) -> bool:
        import os
        return bool(
            self.together_api_key
            or os.environ.get("TOGETHER_API_KEY")
        )


settings = Settings()

import os

if settings.together_api_key and not os.environ.get("TOGETHER_API_KEY"):
    os.environ["TOGETHER_API_KEY"] = settings.together_api_key
