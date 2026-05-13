"""
Engine Output Cache - FaceCheck Engine Architecture

Saves and loads MultiEngineOutput JSON, keyed on player_id + games hash.
Auto-invalidates when game data changes or after 24 hours.
"""

import json
import hashlib
import os
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from facecheck_engine_base import EngineOutput
from facecheck_synthesis import MultiEngineOutput


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine_cache")
MAX_CACHE_AGE_HOURS = 24


def _games_hash(games: List[Dict]) -> str:
    """Hash game IDs for cache invalidation. New games = new hash = cache miss."""
    match_ids = sorted(g.get("match_id", "") for g in games)
    raw = "|".join(match_ids)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_path(player_id: str) -> str:
    """File path for a given player's engine cache."""
    safe_id = player_id.replace("#", "_").replace(" ", "_")
    return os.path.join(CACHE_DIR, f"{safe_id}_engines.json")


def save_engine_outputs(
    player_id: str,
    games: List[Dict],
    engines: MultiEngineOutput,
    cache_dir: str = None
) -> str:
    """Save engine outputs to JSON cache. Returns the path written."""
    if cache_dir is None:
        cache_dir = CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    ghash = _games_hash(games)
    path = _cache_path(player_id) if cache_dir == CACHE_DIR else os.path.join(
        cache_dir, f"{player_id.replace('#', '_').replace(' ', '_')}_engines.json"
    )

    data = {
        "player_id": player_id,
        "games_hash": ghash,
        "saved_at": datetime.now().isoformat(),
        "engines": engines.to_dict(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=None, separators=(",", ":"))

    return path


def load_engine_outputs(
    player_id: str,
    games: List[Dict],
    cache_dir: str = None
) -> Optional[MultiEngineOutput]:
    """Load engine outputs from cache if valid. Returns None on miss."""
    if cache_dir is None:
        cache_dir = CACHE_DIR

    path = _cache_path(player_id) if cache_dir == CACHE_DIR else os.path.join(
        cache_dir, f"{player_id.replace('#', '_').replace(' ', '_')}_engines.json"
    )

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Validate: game data must match
    current_hash = _games_hash(games)
    if data.get("games_hash") != current_hash:
        return None

    # Validate: cache must not be stale
    try:
        saved_at = datetime.fromisoformat(data["saved_at"])
        if datetime.now() - saved_at > timedelta(hours=MAX_CACHE_AGE_HOURS):
            return None
    except (ValueError, KeyError):
        return None

    # Validate: player_id must match
    if data.get("player_id") != player_id:
        return None

    try:
        return MultiEngineOutput.from_dict(data["engines"])
    except (KeyError, TypeError):
        return None


def clear_engine_cache(player_id: str = None) -> int:
    """Clear engine cache. If player_id given, clear only that player. Returns files removed."""
    if not os.path.exists(CACHE_DIR):
        return 0

    removed = 0
    if player_id:
        path = _cache_path(player_id)
        if os.path.exists(path):
            os.remove(path)
            removed = 1
    else:
        for f in os.listdir(CACHE_DIR):
            if f.endswith("_engines.json"):
                os.remove(os.path.join(CACHE_DIR, f))
                removed += 1
    return removed