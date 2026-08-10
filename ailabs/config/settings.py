from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PACKAGE_ROOT.parent


class AgentOverride(BaseModel):
    """Override per-agent dari agent_config.yaml (opsional)."""

    role: str | None = None
    model: str | None = None
    enabled: bool = True


class AgentConfig(BaseModel):
    company_name: str = "AI Labs"
    ceo_name: str = "Mark"
    agents: dict[str, AgentOverride] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "gemini"  # gemini | deepseek | openai_compat | mock
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    # OpenAI-compatible proxy (mis. 9router/kuroko) — base URL mencakup /v1
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = "kr/auto"
    default_model: str = "gemini-2.5-flash"

    # Supabase (postgrest client)
    # Key baru Supabase (2025+): PUBLISHABLE = pengganti anon (RLS aktif),
    # SECRET = pengganti service_role (bypass RLS). ANON_KEY masih didukung (legacy).
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_anon_key: str = ""
    supabase_schema: str = "ailabs"

    # Perilaku orkestrasi
    reviewer_enabled: bool = True
    max_exec_retries: int = 2
    max_review_rounds: int = 2
    embed_model: str = "multilingual-e5-base"

    # Delegasi task koding ke agent opencode (CLI). Mati saat mock/test supaya
    # test tidak menjalankan opencode asli.
    enable_opencode: bool = False

    # Batas iterasi skill agentic_loop (loop otonom pikir -> tool -> amati).
    agentic_max_iterations: int = 8

    # Obsidian (opsional)
    obsidian_vault_path: str = ""

    # Workspace lokal untuk hasil file agent (default: <project>/workspace)
    local_workspace_path: str = ""

    # Jalur file config agent
    agent_config_path: Path = PROJECT_ROOT / "ailabs" / "config" / "agent_config.yaml"

    def agent_config(self) -> AgentConfig:
        path = self.agent_config_path
        if not path.exists():
            return AgentConfig()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return AgentConfig.model_validate(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()
