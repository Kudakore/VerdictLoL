"""
Config auto-setup — ensures config.py exists before any module tries to import it.

If config.py is missing, copies from config_template.py.
If config.py has placeholder values, prints instructions and exits.
Called from facecheck_data.py and standalone league scripts.
"""
import os
import sys
import shutil

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG = os.path.join(_DIR, "config.py")
_TEMPLATE = os.path.join(_DIR, "config_template.py")

def ensure_config():
    """Create config.py from template if missing; validate it has real values."""
    if not os.path.exists(_CONFIG):
        if os.path.exists(_TEMPLATE):
            shutil.copy2(_TEMPLATE, _CONFIG)
            print("  Created config.py from template.")
            print("  Edit C:\\Facecheck\\config.py with your Riot API key and summoner name.")
            print("  Get your key at: https://developer.riotgames.com/")
            print()

    if os.path.exists(_CONFIG):
        with open(_CONFIG, encoding="utf-8") as f:
            content = f.read()
        if "YOUR_RIOT_API_KEY_HERE" in content:
            print("  config.py still has placeholder values.")
            print("  Edit C:\\Facecheck\\config.py with your Riot API key and summoner name.")
            print("  Get your key at: https://developer.riotgames.com/")
            sys.exit(1)