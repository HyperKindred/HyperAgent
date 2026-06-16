"""OpenWeatherMap API client — no extra dependencies beyond `requests`."""

import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 10

_WEATHER_ICONS: dict[str, str] = {
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


def _icon(weather_code: str) -> str:
    return _WEATHER_ICONS.get(weather_code, "🌡️")


def _format_weather(data: dict[str, Any]) -> str:
    """Format OpenWeatherMap API response into a human-readable string."""
    city = data.get("name", "未知城市")
    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})

    temp = main.get("temp", 0)
    feels_like = main.get("feels_like", 0)
    humidity = main.get("humidity", 0)
    desc = weather.get("description", "")
    icon_code = weather.get("icon", "")
    wind_speed = wind.get("speed", 0)

    return (
        f"{_icon(icon_code)} **{city}** 当前天气\n"
        f"   🌡 温度：{temp:.0f}°C（体感 {feels_like:.0f}°C）\n"
        f"   ☁️ 天气：{desc}\n"
        f"   💧 湿度：{humidity}%\n"
        f"   💨 风速：{wind_speed:.1f}m/s"
    )


def get_weather(city: str) -> str:
    """Query current weather for *city* and return a formatted string.

    Returns an error message if the API key is not configured or the request
    fails, so callers don't need to handle exceptions.
    """
    if not settings.weather_api_key:
        return (
            "❌ 未配置天气 API。请在 .env 中设置 WEATHER_API_KEY。\n"
            "   👉 免费注册 OpenWeatherMap: https://home.openweathermap.org/users/sign_up\n"
            "   👉 获取 API Key: https://home.openweathermap.org/api_keys"
        )

    url = f"{settings.weather_base_url}/weather"
    params: dict[str, str] = {
        "q": city,
        "appid": settings.weather_api_key,
        "units": "metric",
        "lang": "zh_cn",
    }

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return _format_weather(data)
    except requests.RequestException as e:
        logger.warning("Weather API request failed for %s: %s", city, e)
        return f"❌ 查询 {city} 天气失败：{e}"
