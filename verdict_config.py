"""
Config auto-setup — ensures config.py exists before any module tries to import it.

Priority for config values:
1. Environment variables (VERDICT_API_KEY, VERDICT_REGION, etc.)
2. .env file in DATA_DIR
3. config.py (auto-created from config_template.py if missing)

Called from verdict_data.py and standalone league scripts.
"""
import os
import sys
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

def ensure_config():
    """Create config.py from template if missing; validate it has real values.

    Returns True if config is valid, False if placeholder values remain.
    Does NOT call sys.exit — callers decide how to handle invalid config.
    """
    _load_dotenv()

    # If env vars provide everything, config.py is optional
    env_api_key = os.environ.get("VERDICT_API_KEY", "")
    env_region = os.environ.get("VERDICT_REGION", "")
    env_platform = os.environ.get("VERDICT_PLATFORM", "")
    env_name = os.environ.get("VERDICT_GAME_NAME", "")
    env_tag = os.environ.get("VERDICT_TAG_LINE", "")

    # Create config.py from template if it doesn't exist
    if not os.path.exists(_CONFIG):
        if os.path.exists(_TEMPLATE):
            shutil.copy2(_TEMPLATE, _CONFIG)
            print("  Created config.py from template.")
            print(f"  Edit {_CONFIG} with your Riot API key and summoner name.")
            print("  Get your key at: https://developer.riotgames.com/")
            print()

    # Check if config.py still has placeholder values
    config_valid = True
    if os.path.exists(_CONFIG):
        with open(_CONFIG, encoding="utf-8") as f:
            content = f.read()
        if "YOUR_RIOT_API_KEY_HERE" in content:
            config_valid = False

    # Config is valid if either env vars or config.py provide real values
    has_env_config = bool(env_api_key and env_name and env_tag)
    has_file_config = config_valid

    if has_env_config or has_file_config:
        return True

    # Neither source has valid config
    print("  Verdict needs your Riot API key and summoner name.")
    print("  Set environment variables:")
    print("    VERDICT_API_KEY, VERDICT_REGION, VERDICT_PLATFORM, VERDICT_GAME_NAME, VERDICT_TAG_LINE")
    print("  Or create a .env file in the project directory.")
    print(f"  Or edit {_CONFIG} directly.")
    print("  Get your API key at: https://developer.riotgames.com/")
    sys.exit(1)