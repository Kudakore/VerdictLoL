"""Tests 5-6: Config loading from .env and ensure_config failure path."""

import os


class TestConfigLoading:
    """Test 5: verdict_config exports are non-empty after loading .env."""

    def test_api_key_loaded(self):
        from verdict_config import API_KEY
        assert API_KEY, "API_KEY should be loaded from .env"
        assert API_KEY != "YOUR_RIOT_API_KEY_HERE", "API_KEY should not be placeholder"

    def test_region_loaded(self):
        from verdict_config import REGION
        assert REGION == "americas"

    def test_platform_loaded(self):
        from verdict_config import PLATFORM
        assert PLATFORM == "na1"

    def test_game_name_loaded(self):
        from verdict_config import MY_GAME_NAME
        assert MY_GAME_NAME, "MY_GAME_NAME should be loaded from .env"

    def test_tag_line_loaded(self):
        from verdict_config import MY_TAG_LINE
        assert MY_TAG_LINE, "MY_TAG_LINE should be loaded from .env"

    def test_ensure_config_returns_true(self):
        from verdict_config import ensure_config
        assert ensure_config() is True, "ensure_config() should return True with valid config"


class TestConfigFailure:
    """Test 6: ensure_config returns False when config is missing."""

    def test_ensure_config_returns_false_without_identity(self, monkeypatch):
        """With empty game name and tag line, ensure_config should return False."""
        monkeypatch.setattr("verdict_config.MY_GAME_NAME", "")
        monkeypatch.setattr("verdict_config.MY_TAG_LINE", "")
        # Need to re-evaluate the validity check since ensure_config uses module-level vars
        import verdict_config
        monkeypatch.setattr(verdict_config, "MY_GAME_NAME", "")
        monkeypatch.setattr(verdict_config, "MY_TAG_LINE", "")

        result = verdict_config.ensure_config()
        assert result is False, "ensure_config() should return False with empty identity"

    def test_ensure_config_returns_false_with_placeholder_key(self, monkeypatch):
        """With placeholder API key, ensure_config should return False."""
        import verdict_config
        monkeypatch.setattr(verdict_config, "API_KEY", "YOUR_RIOT_API_KEY_HERE")

        result = verdict_config.ensure_config()
        assert result is False, "ensure_config() should return False with placeholder key"