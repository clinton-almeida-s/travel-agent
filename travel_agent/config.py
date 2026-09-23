"""Configuration: loads .env (stdlib-only parser) and exposes typed settings.

All secrets come from the environment; nothing is hardcoded. Use
``is_configured(service)`` to check whether a given capability has the
credentials it needs before calling it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — no third-party dependency required."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


_load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """All runtime settings, read once from the environment."""

    # LLM backend
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Flights: Duffel (free test mode, no card) — https://duffel.com
    duffel_api_key: str = os.getenv("DUFFEL_API_KEY", "")

    # Hotels: LiteAPI (free sandbox key, no card) — https://dashboard.liteapi.travel
    liteapi_api_key: str = os.getenv("LITEAPI_API_KEY", "")

    # Weather / activities
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    opentripmap_api_key: str = os.getenv("OPENTRIPMAP_API_KEY", "")

    # Safety: live ticketing is OFF unless explicitly enabled.
    enable_live_booking: bool = os.getenv("ENABLE_LIVE_BOOKING", "false").lower() == "true"

    max_tool_iterations: int = _env_int("MAX_TOOL_ITERATIONS", 12)


settings = Settings()


def is_configured(service: str) -> bool:
    """Return True if ``service`` has everything it needs to run.

    Services: "llm", "flights", "hotels", "weather", "activities", "geocode".
    """
    s = settings
    if service == "llm":
        if s.llm_provider == "gemini":
            return bool(s.gemini_api_key)
        if s.llm_provider == "groq":
            return bool(s.groq_api_key)
        return False
    if service == "flights":
        return bool(s.duffel_api_key)
    if service == "hotels":
        return bool(s.liteapi_api_key)
    if service == "weather":
        return bool(s.openweather_api_key)
    if service in ("activities", "geocode"):
        return True  # Wikipedia + Nominatim need no keys
    return False


def missing_services() -> list[str]:
    """Services the user probably wants but hasn't configured."""
    return [s for s in ("llm", "flights", "hotels", "weather") if not is_configured(s)]
