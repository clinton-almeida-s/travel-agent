"""Weather via OpenWeather 5-day forecast (free tier).

Dates further than ~5 days out return an error — the agent must then treat
weather as unknown rather than inventing a forecast.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from ..config import settings

_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _parse_range(date_range: str) -> tuple[datetime, datetime] | None:
    parts = [p.strip() for p in date_range.replace("–", "-").split("to")]
    try:
        start = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(parts[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return start, end
    except (ValueError, IndexError):
        return None


def get_weather(location: str, date_range: str) -> dict:
    """Forecast for a location over a date range."""
    if not settings.openweather_api_key:
        return {
            "error": "Weather unavailable: OPENWEATHER_API_KEY not set.",
            "hint": "Get a free key at https://openweathermap.org/api and add it to .env.",
        }
    parsed = _parse_range(date_range)
    if parsed is None:
        return {
            "error": f"Could not parse date_range '{date_range}'.",
            "hint": "Use 'YYYY-MM-DD to YYYY-MM-DD'.",
        }
    start, end = parsed
    if end < start:
        start, end = end, start
    try:
        resp = requests.get(
            _FORECAST_URL,
            params={"q": location, "appid": settings.openweather_api_key, "units": "metric"},
            timeout=15,
        )
        if resp.status_code == 401:
            return {"error": "OpenWeather rejected the API key.", "hint": "Check OPENWEATHER_API_KEY."}
        if resp.status_code == 404:
            return {"error": f"Location '{location}' not found.", "hint": "Try 'City, Country'."}
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"error": f"Weather lookup failed: {exc}", "hint": "Retry shortly."}

    days: dict[str, dict] = {}
    for entry in data.get("list", []):
        dt = datetime.fromtimestamp(entry["dt"], tz=timezone.utc)
        if not (start.date() <= dt.date() <= end.date()):
            continue
        key = dt.date().isoformat()
        day = days.setdefault(
            key, {"temps": [], "descriptions": [], "rain_mm": 0.0}
        )
        day["temps"].append(entry["main"]["temp"])
        day["descriptions"].append(entry["weather"][0]["description"])
        day["rain_mm"] += entry.get("rain", {}).get("3h", 0.0)

    forecast = []
    for day_key in sorted(days):
        d = days[day_key]
        forecast.append(
            {
                "date": day_key,
                "temp_min_c": round(min(d["temps"]), 1),
                "temp_max_c": round(max(d["temps"]), 1),
                "conditions": max(set(d["descriptions"]), key=d["descriptions"].count),
                "rain_mm": round(d["rain_mm"], 1),
            }
        )
    out: dict = {"location": data.get("city", {}).get("name", location), "forecast": forecast}
    horizon = datetime.now(timezone.utc).date() + timedelta(days=5)
    if end.date() > horizon:
        out["warning"] = (
            "Free-tier forecast only covers ~5 days ahead; dates beyond that have no "
            "forecast data. Treat later dates as unknown weather."
        )
    if not forecast:
        out["note"] = "No forecast entries fall inside the requested range."
    return out
