import pytest

from app import config


def test_get_api_key_rejects_placeholder(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "여기에_API_키를_붙여넣기")
    with pytest.raises(RuntimeError):
        config.get_api_key()


def test_get_api_key_rejects_missing(monkeypatch):
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        config.get_api_key()


def test_get_api_key_returns_env_value(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "dummy-test-value")
    assert config.get_api_key() == "dummy-test-value"


def test_prices_cover_both_models():
    assert set(config.PRICES) == {"claude-haiku-5-5", "claude-sonnet-5-5"}
    assert config.PRICES["claude-haiku-5-5"]["input"] == 0.10
    for p in config.PRICES.values():
        assert set(p) == {"input", "output", "cache_write", "cache_read"}
