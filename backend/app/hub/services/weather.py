"""Weather service: current conditions from Open-Meteo (no API key) with a short in-memory cache.

The service never raises: when weather is disabled, the home has no coordinates, or the request
fails, it returns ``WeatherOut(available=False)`` so the app's home header degrades gracefully.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx

from app.hub.adapters.base import AdapterContext
from app.hub.schemas import WeatherOut

logger = logging.getLogger("safer.hub.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
CACHE_TTL = 60.0  # seconds a successful lookup stays fresh
FAILURE_TTL = 15.0  # seconds before retrying after a failed lookup
_MAX_CACHE_ENTRIES = 256

# WMO 4677 weather interpretation codes (as used by Open-Meteo) -> (condition, Material icon)
WMO_CONDITIONS: Dict[int, Tuple[str, str]] = {
    0: ("clear", "wb_sunny"),
    1: ("mainly_clear", "wb_sunny"),
    2: ("partly_cloudy", "wb_cloudy"),
    3: ("cloudy", "cloud"),
    45: ("fog", "foggy"),
    48: ("fog", "foggy"),
    51: ("drizzle", "grain"),
    53: ("drizzle", "grain"),
    55: ("drizzle", "grain"),
    56: ("freezing_drizzle", "severe_cold"),
    57: ("freezing_drizzle", "severe_cold"),
    61: ("rain", "water_drop"),
    63: ("rain", "water_drop"),
    65: ("rain", "water_drop"),
    66: ("freezing_rain", "severe_cold"),
    67: ("freezing_rain", "severe_cold"),
    71: ("snow", "ac_unit"),
    73: ("snow", "ac_unit"),
    75: ("snow", "ac_unit"),
    77: ("snow_grains", "ac_unit"),
    80: ("rain_showers", "umbrella"),
    81: ("rain_showers", "umbrella"),
    82: ("rain_showers", "umbrella"),
    85: ("snow_showers", "cloudy_snowing"),
    86: ("snow_showers", "cloudy_snowing"),
    95: ("thunderstorm", "thunderstorm"),
    96: ("thunderstorm_hail", "thunderstorm"),
    99: ("thunderstorm_hail", "thunderstorm"),
}
UNKNOWN_CONDITION: Tuple[str, str] = ("unknown", "cloud")

# (rounded lat, rounded lon) -> (monotonic expiry, result)
_cache: Dict[Tuple[float, float], Tuple[float, WeatherOut]] = {}


def cache_key(lat: float, lon: float) -> Tuple[float, float]:
    """Cache key: coordinates rounded to ~1 km so nearby homes share a lookup."""
    return (round(float(lat), 2), round(float(lon), 2))


def clear_cache() -> None:
    """Drop every cached lookup (tests / settings changes)."""
    _cache.clear()


def describe_code(code: Any) -> Tuple[str, str]:
    """Map a WMO weather code to ``(condition, material_icon)``; unknown codes -> ``("unknown", "cloud")``."""
    try:
        return WMO_CONDITIONS.get(int(code), UNKNOWN_CONDITION)
    except (TypeError, ValueError):
        return UNKNOWN_CONDITION


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime:
    """Open-Meteo returns ``YYYY-MM-DDTHH:MM`` in the requested timezone (GMT by default)."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.utcnow()


def parse_current(data: Dict[str, Any]) -> WeatherOut:
    """Build a ``WeatherOut`` from an Open-Meteo ``/v1/forecast`` body (raises ``ValueError`` when malformed)."""
    if not isinstance(data, dict):
        raise ValueError("weather payload is not an object")
    if data.get("error"):
        raise ValueError(str(data.get("reason") or "Open-Meteo returned an error"))
    current = data.get("current")
    if not isinstance(current, dict):
        raise ValueError("weather payload has no 'current' block")
    condition, icon = describe_code(current.get("weather_code"))
    return WeatherOut(
        temperature=_float(current.get("temperature_2m")),
        humidity=_float(current.get("relative_humidity_2m")),
        condition=condition,
        icon=icon,
        wind_kmh=_float(current.get("wind_speed_10m")),
        updated_at=_parse_time(current.get("time")),
        available=True,
    )


def _weather_enabled(ctx: AdapterContext) -> bool:
    settings = getattr(ctx, "settings", None)
    return bool(getattr(settings, "HUB_WEATHER_ENABLED", True))


def _remember(key: Tuple[float, float], result: WeatherOut, now: float) -> None:
    if len(_cache) >= _MAX_CACHE_ENTRIES:
        for stale in [k for k, (expiry, _) in _cache.items() if expiry <= now]:
            _cache.pop(stale, None)
        if len(_cache) >= _MAX_CACHE_ENTRIES:
            _cache.clear()
    _cache[key] = (now + (CACHE_TTL if result.available else FAILURE_TTL), result)


async def get_weather(lat: Optional[float], lon: Optional[float], ctx: AdapterContext) -> WeatherOut:
    """Current weather for a location. Never raises; ``available`` tells whether data is real.

    Uses ``ctx.http()`` so tests inject an ``httpx.MockTransport`` and honours
    ``ctx.settings.HUB_WEATHER_ENABLED``. Results are cached 60 s per rounded lat/lon.
    """
    if not _weather_enabled(ctx):
        return WeatherOut(available=False)
    if lat is None or lon is None:
        return WeatherOut(available=False)
    try:
        key = cache_key(lat, lon)
    except (TypeError, ValueError):
        return WeatherOut(available=False)

    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1].model_copy()

    params = {"latitude": round(float(lat), 4), "longitude": round(float(lon), 4), "current": CURRENT_FIELDS}
    result = WeatherOut(available=False)
    try:
        async with ctx.http() as client:
            response = await client.get(OPEN_METEO_URL, params=params)
        if response.status_code == 200:
            result = parse_current(response.json())
        else:
            logger.warning("Open-Meteo responded %s for %s: %s", response.status_code, key, response.text[:200])
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Weather lookup failed for %s: %s", key, exc)
    _remember(key, result, now)
    return result.model_copy()
