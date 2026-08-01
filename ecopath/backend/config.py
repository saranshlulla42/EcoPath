"""
EcoPath Backend — Configuration
Loads and validates all environment variables using pydantic-settings.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Gemini AI
    gemini_api_key: str
    gemini_pro_model: str = "gemini-2.5-flash"
    gemini_flash_model: str = "gemini-2.5-flash"

    # Local report model (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_report_model: str = "ecopath-extinction-risk"
    ollama_timeout_seconds: int = 120

    # Optional external evidence/search sources
    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    iucn_base_url: str = "https://apiv3.iucnredlist.org/api/v3"
    iucn_api_token: str = ""

    # GBIF
    gbif_base_url: str = "https://api.gbif.org/v1"
    gbif_aves_taxon_key: int = 212
    gbif_country_code: str = ""  # Default empty = no country filter (global)

    # Open-Meteo
    openmeteo_base_url: str = "https://archive-api.open-meteo.com/v1/archive"

    # xeno-canto (v3 requires API key — get yours at https://xeno-canto.org/account)
    xenocanto_base_url: str = "https://xeno-canto.org/api/3/recordings"
    xenocanto_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    log_level: str = "info"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
