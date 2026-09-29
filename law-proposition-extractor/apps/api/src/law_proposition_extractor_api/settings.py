from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Comma-separated override for browser CORS origins (env: ``CORS_ALLOWED_ORIGINS``).
    #: When unset or blank after splitting, defaults apply (localhost / 127.0.0.1 :3000–3001).
    cors_allowed_origins_csv: str | None = Field(
        default=None,
        validation_alias="CORS_ALLOWED_ORIGINS",
        repr=False,
    )

    app_name: str = "Law Proposition Extractor API"
    app_env: str = "dev"
    operations_export_dir: str = "dist/static-report"
    #: Default path for curated equine law corpus JSON (relative to cwd when not absolute).
    equine_corpus_config_path: str = "examples/corpus_equine_law.json"
    source_registry_path: str = "/tmp/law-proposition-extractor/source-registry.json"
    source_cache_dir: str = "/tmp/law-proposition-extractor/source-snapshots"
    derived_cache_dir: str = "/tmp/law-proposition-extractor/derived-artifacts"

    @property
    def cors_allowed_origins(self) -> list[str]:
        raw = self.cors_allowed_origins_csv
        if raw is None or not raw.strip():
            return list(_DEFAULT_CORS_ALLOWED_ORIGINS)
        parsed = [part.strip() for part in raw.split(",") if part.strip()]
        return parsed if parsed else list(_DEFAULT_CORS_ALLOWED_ORIGINS)


settings = ApiSettings()
