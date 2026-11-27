"""Per-city weather cache (4.8): one OpenWeatherMap call per city per 10 minutes."""
from __future__ import annotations

import threading
import time

from tools import weather_tool
from tools.weather_tool import WeatherContext

TTL_SECONDS = 600
MAX_CITIES = 256
_cache: dict[str, tuple[float, WeatherContext]] = {}
_lock = threading.Lock()


def cached_weather(city: str) -> WeatherContext:
    key = " ".join(city.lower().split())
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < TTL_SECONDS:
            return hit[1]
    result = weather_tool.get_weather(city)  # errors are not cached
    with _lock:
        if len(_cache) >= MAX_CITIES:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[key] = (now, result)
    return result


def clear() -> None:
    with _lock:
        _cache.clear()
