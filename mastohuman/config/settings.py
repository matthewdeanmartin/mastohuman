import importlib.resources
from pathlib import Path
from typing import Literal, Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_templates_path() -> Path:
    """
    Tries to find templates via importlib (installed package),
    falls back to relative path (local dev).
    """
    # 1. Try importlib.resources (The standard way)
    try:
        # This gets a Traversable object for 'mastohuman/templates'
        # We explicitly look up the 'mastohuman' package
        ref = importlib.resources.files("mastohuman").joinpath("templates")

        # Convert to strict Path.
        # Note: If this is inside a zip file (zipped release),
        # this path might not be usable by standard file IO (see note below).
        path = Path(ref)

        if path.exists() and path.is_dir():
            print("Found template folder by resource")
            return path
    except (ImportError, TypeError, ValueError, ModuleNotFoundError):
        pass

    # 2. Fallback: Path hacking (The local dev way)
    # This anchors to: mastohuman/config/settings.py -> up to mastohuman/ -> templates/
    local_path = Path(__file__).resolve().parent.parent / "templates"
    if local_path.exists():
        print("Found template folder by path hack")
        return local_path

    # 3. Last Resort: Return relative (user must run from root)
    print("Can't find anything, hoping to use some thing")
    return Path("mastohuman/templates")


class Settings(BaseSettings):
    # output_dir setup...

    # Dynamically resolve the path
    templates_dir: Path = get_templates_path()


class Settings(BaseSettings):
    # Mastodon
    mastodon_base_url: (
        str  # Kept as str to avoid Pydantic URL trailing slash complexities in API
    )
    mastodon_access_token: SecretStr
    mastodon_timeout_s: float = 30.0
    mastodon_user_agent: str = "MastoHuman/0.1.0"

    # Fetch limits
    since_hours: int = 24
    max_profile_statuses: int = 500
    max_profile_age_days: int = 92
    page_size: int = 40

    # Database
    db_path: Path = Path("mastohuman.db")
    db_echo: bool = False

    # LLM
    llm_provider: Literal["openai", "openrouter", "ollama", "none"] = "openai"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1000
    llm_api_key: Optional[SecretStr] = None
    llm_base_url: Optional[str] = None

    # Rendering
    site_title: str = "My Mastodon Reader"
    output_dir: Path = Path("output_dir")
    archive_dir: Optional[Path] = None
    base_url: Optional[str] = None

    templates_dir: Path = get_templates_path()

    # Cache Policy
    rebuild_on_template_change: bool = True

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Singleton instance
settings = Settings()


def get_db_url() -> str:
    return f"sqlite:///{settings.db_path}"
