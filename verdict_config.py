"""
Config — single source of truth for all Verdict configuration.

Priority for config values:
1. Environment variables (VERDICT_API_KEY, VERDICT_REGION, etc.)
2. .env file in DATA_DIR
3. config.py in DATA_DIR (auto-created from config_template.py if missing)

All modules should import config values from here:
    from verdict_config import API_KEY, REGION, PLATFORM, MY_GAME_NAME, MY_TAG_LINE

No module should import from `config` directly.
"""
import os
import shutil

from verdict_paths import DATA_DIR

_CONFIG = os.path.join(DATA_DIR, "config.py")
_TEMPLATE = os.path.join(DATA_DIR, "config_template.py")
_ENV_FILE = os.path.join(DATA_DIR, ".env")


def _load_dotenv():
    """Load .env file if it exists. Simple parser — no external dependency."""
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def _load_from_config_py():
    """Fallback: load values from config.py if env vars are empty."""
    api_key = os.environ.get("VERDICT_API_KEY", "")
    game_name = os.environ.get("VERDICT_GAME_NAME", "")
    tag_line = os.environ.get("VERDICT_TAG_LINE", "")

    if api_key and game_name and tag_line:
        return  # env vars cover everything, no need for config.py

    if not os.path.exists(_CONFIG):
        return

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_config", _CONFIG)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not api_key:
                os.environ.setdefault("VERDICT_API_KEY", getattr(mod, "API_KEY", ""))
            if not game_name:
                os.environ.setdefault("VERDICT_GAME_NAME", getattr(mod, "MY_GAME_NAME", ""))
            if not tag_line:
                os.environ.setdefault("VERDICT_TAG_LINE", getattr(mod, "MY_TAG_LINE", ""))
    except Exception:
        pass


# --- Load config on import ---
_load_dotenv()
_load_from_config_py()

# Exported config values (env vars > .env > config.py)
API_KEY = os.environ.get("VERDICT_API_KEY", "")
REGION = os.environ.get("VERDICT_REGION", "americas")
PLATFORM = os.environ.get("VERDICT_PLATFORM", "na1")
MY_GAME_NAME = os.environ.get("VERDICT_GAME_NAME", "")
MY_TAG_LINE = os.environ.get("VERDICT_TAG_LINE", "")


def ensure_config():
    """Validate that required config values are present.

    Returns True if config is valid, False if missing.
    Does NOT call sys.exit — callers decide how to handle invalid config.
    """
    # Auto-create config.py from template if it doesn't exist (for manual setup)
    if not os.path.exists(_CONFIG):
        if os.path.exists(_TEMPLATE):
            shutil.copy2(_TEMPLATE, _CONFIG)
            print("  Created config.py from template.")
            print(f"  Edit {_CONFIG} with your Riot API key and summoner name.")
            print("  Get your key at: https://developer.riotgames.com/")
            print()

    # Check if config has real values
    has_api_key = bool(API_KEY) and API_KEY != "YOUR_RIOT_API_KEY_HERE"
    has_identity = bool(MY_GAME_NAME) and bool(MY_TAG_LINE)

    if has_api_key and has_identity:
        return True

    # Missing config — print guidance
    print("  Verdict needs your Riot API key and summoner name.")
    print("  Set environment variables:")
    print("    VERDICT_API_KEY, VERDICT_REGION, VERDICT_PLATFORM, VERDICT_GAME_NAME, VERDICT_TAG_LINE")
    print("  Or create a .env file in the project directory.")
    print(f"  Or edit {_CONFIG} directly.")
    print("  Get your API key at: https://developer.riotgames.com/")
    return False