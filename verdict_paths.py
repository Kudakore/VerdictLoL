"""
Verdict Paths — centralized path configuration.

All paths are derived from DATA_DIR, which defaults to the directory
containing this file. Set VERDICT_DATA_DIR environment variable to
override (or create a .env file in the project root).
"""

import os

# DATA_DIR: root directory for all Verdict data files
# Priority: VERDICT_DATA_DIR env var > .env file > script directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("VERDICT_DATA_DIR", _SCRIPT_DIR)

# Core data files
CACHE_PATH = os.path.join(DATA_DIR, "verdict_cache.json")
BRAIN_PATH = os.path.join(DATA_DIR, "verdict_brain.json")

# Subdirectories (created on demand)
SCOUT_DIR = os.path.join(DATA_DIR, "scout_cache")
ENGINE_CACHE_DIR = os.path.join(DATA_DIR, "engine_cache")

# LeagueVault (champion data)
VAULT_PATH = os.path.join(DATA_DIR, "LeagueVault", "Champions")
VAULT_ROOT = os.path.join(DATA_DIR, "LeagueVault")