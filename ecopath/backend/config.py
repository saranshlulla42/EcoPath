"""
EcoPath Backend — Configuration
Loads and validates all environment variables using pydantic-settings.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ollama_comparison_base_model: str = "qwen2.5:7b-instruct"
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

    # Groq (chat agent)
    groq_api_key: str

    # Agent Settings
    agent_model: str = "openai/gpt-oss-120b"
    agent_temperature: float = 0.3
    # Each extra round resends the whole prefix plus everything accumulated so
    # far, so cost climbs steeply with rounds. Three covers resolve -> query ->
    # refine, and a round may fire several tools in parallel, so this is not one
    # tool call per round. Past three the model is generally retrying a failing
    # tool rather than making progress; the loop says so instead of grinding on.
    agent_max_tool_rounds: int = 3
    # Research session lifetime. Lower it (e.g. 0.17 ≈ 10s) to exercise expiry handling.
    agent_session_ttl_minutes: float = 30.0

    # Fine-tuned PEFT model (lazy-loaded at first inference, not at startup).
    # Set peft_base_model to the HuggingFace repo id of the base model and
    # peft_adapter_path to the local directory containing the LoRA adapter.
    # Leave either unset to skip local-model inference entirely.
    peft_base_model: Optional[str] = None
    peft_adapter_path: Optional[str] = None

    # GBIF
    gbif_base_url: str = "https://api.gbif.org/v1"
    gbif_aves_taxon_key: int = 212
    gbif_country_code: str = ""  # Default empty = no country filter (global)

    # eBird — server-side only. Previously exposed to the browser as
    # NEXT_PUBLIC_EBIRD_API_KEY, which shipped the key in the client bundle.
    ebird_api_key: str = ""
    ebird_base_url: str = "https://api.ebird.org/v2"

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
