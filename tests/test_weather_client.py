"""Weather provider fallback resilience tests."""

from app.weather import client


def test_invalid_openweather_json_falls_back_to_wttr(monkeypatch):
    class InvalidJsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("HTML error page")

    class WttrResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "current_condition": [
                    {
                        "weatherCode": "113",
                        "temp_C": "20",
                        "FeelsLikeC": "19",
                        "weatherDesc": [{"value": "Sunny"}],
                        "humidity": "50",
                        "windspeedKmph": "8",
                    }
                ]
            }

    monkeypatch.setattr(client.settings, "weather_api_key", "test-key")
    monkeypatch.setattr(client.requests, "get", lambda *_args, **_kwargs: next(responses))
    responses = iter([InvalidJsonResponse(), WttrResponse()])

    result = client.get_weather("Beijing")

    assert "Beijing" in result
    assert "20°C" in result
