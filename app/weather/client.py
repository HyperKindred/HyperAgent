"""Weather API client with provider fallback.

Try sequence:
1. **OpenWeatherMap** — if API key is configured in `.env`
2. **wttr.in** — free, no API key needed, works worldwide

Only fails if both providers are unreachable.
"""

import json
import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 10

_OWM_ICONS: dict[str, str] = {
    "01d": "☀️", "01n": "🌙",
    "02d": "⛅", "02n": "☁️",
    "03d": "☁️", "03n": "☁️",
    "04d": "☁️", "04n": "☁️",
    "09d": "🌧️", "09n": "🌧️",
    "10d": "🌦️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️",
    "13d": "🌨️", "13n": "🌨️",
    "50d": "🌫️", "50n": "🌫️",
}

_WTTR_COND: dict[str, str] = {
    "113": "☀️", "116": "⛅", "119": "☁️", "122": "☁️",
    "143": "🌫️", "176": "🌦️", "179": "🌨️", "182": "🌨️",
    "185": "🌧️", "200": "⛈️", "227": "🌨️", "230": "🌨️",
    "248": "🌫️", "260": "🌫️", "263": "🌦️", "266": "🌧️",
    "281": "🌧️", "284": "🌧️", "293": "🌦️", "296": "🌧️",
    "299": "🌦️", "302": "🌧️", "305": "🌧️", "308": "🌧️",
    "311": "🌧️", "314": "🌧️", "317": "🌧️", "320": "🌨️",
    "323": "🌨️", "326": "🌨️", "329": "🌨️", "332": "🌨️",
    "335": "🌨️", "338": "🌨️", "350": "🌧️", "353": "🌦️",
    "356": "🌧️", "359": "🌧️", "362": "🌧️", "365": "🌧️",
    "368": "🌨️", "371": "🌨️", "374": "🌧️", "377": "🌧️",
    "386": "⛈️", "389": "⛈️", "392": "⛈️", "395": "🌨️",
}


def _format_owm(data: dict[str, Any]) -> str:
    """Format OpenWeatherMap API response."""
    city = data.get("name", "未知城市")
    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})
    icon = _OWM_ICONS.get(weather.get("icon", ""), "🌡️")

    return (
        f"{icon} **{city}** 当前天气\n"
        f"   🌡 温度：{main.get('temp', 0):.0f}°C（体感 {main.get('feels_like', 0):.0f}°C）\n"
        f"   ☁️ 天气：{weather.get('description', '')}\n"
        f"   💧 湿度：{main.get('humidity', 0)}%\n"
        f"   💨 风速：{wind.get('speed', 0):.1f}m/s"
    )


def _format_wttr(data: dict[str, Any], city: str) -> str:
    """Format wttr.in API response."""
    cc = data.get("current_condition", [{}])[0]
    icon = _WTTR_COND.get(cc.get("weatherCode", ""), "🌡️")

    return (
        f"{icon} **{city}** 当前天气\n"
        f"   🌡 温度：{cc.get('temp_C', '?')}°C（体感 {cc.get('FeelsLikeC', '?')}°C）\n"
        f"   ☁️ 天气：{cc.get('weatherDesc', [{}])[0].get('value', '')}\n"
        f"   💧 湿度：{cc.get('humidity', '?')}%\n"
        f"   💨 风速：{cc.get('windspeedKmph', '?')}km/h"
    )


def _try_openweathermap(city: str) -> str | None:
    """Try OpenWeatherMap. Returns None on any failure."""
    if not settings.weather_api_key:
        return None
    try:
        resp = requests.get(
            f"{settings.weather_base_url}/weather",
            params={"q": city, "appid": settings.weather_api_key, "units": "metric", "lang": "zh_cn"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return _format_owm(resp.json())
    except requests.RequestException as e:
        logger.warning("OpenWeatherMap failed for %s: %s", city, e)
        return None


def _try_wttrin(city: str) -> str | None:
    """Try wttr.in (free, no API key). Returns None on failure."""
    try:
        resp = requests.get(
            f"https://wttr.in/{city}?format=j1",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return _format_wttr(resp.json(), city)
    except requests.RequestException as e:
        logger.warning("wttr.in failed for %s: %s", city, e)
        return None


def get_weather(city: str) -> str:
    """Query current weather for *city* and return a formatted string.

    Tries OpenWeatherMap first (if API key is configured), then
    falls back to wttr.in (free, no key needed).
    """
    # Try OpenWeatherMap (requires API key)
    result = _try_openweathermap(city)
    if result:
        return result

    # Try wttr.in (free fallback)
    result = _try_wttrin(city)
    if result:
        return result

    # Both failed
    return (
        f"❌ 查询 {city} 天气失败。\n"
        "请确保网络连接正常，或在 .env 中配置有效的 OpenWeatherMap API Key。\n"
        "   👉 免费注册: https://home.openweathermap.org/users/sign_up\n"
        "   👉 获取 API Key: https://home.openweathermap.org/api_keys"
    )
