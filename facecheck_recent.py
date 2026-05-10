"""
FaceCheck Recent — Quick match history display
Shows last 20 games with role and duration (like league scout)
"""

import requests
import json
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
sys.path.insert(0, "C:\\Facecheck")

from facecheck_analysis import winrate

# Config
import facecheck_data as fd
from config import MY_GAME_NAME, MY_TAG_LINE

API_KEY = fd.API_KEY
REGION = fd.REGION
PLATFORM = fd.PLATFORM

HEADERS = {"X-Riot-Token": API_KEY}
QUEUE_FILTERS = fd.QUEUE_FILTERS + [400, 480]  # Add Draft/Swiftplay to base list
QUEUE_NAMES = {
    420: "Solo",
    440: "Flex",
    400: "Draft",
    480: "Swift",
    450: "ARAM",
    900: "URF",
}

# Role display mapping
POSITIONS = fd.POSITIONS

_last_call = 0

def rl_get(url, delay=0.1):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_call = time.time()
    return requests.get(url, headers=HEADERS, timeout=10)

def get_match_details(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    r = rl_get(url)
    if r.status_code == 200:
        return r.json()
    return None

def format_duration(seconds):
    """Format seconds to Xm Ys."""
    m = seconds // 60
    s = seconds % 60
    return f"{m}m{s}s"

def get_cached_games(count=20, queue_filter=None):
    """Get games from local cache."""
    from facecheck_data import load_cache
    cache = load_cache()
    games = cache.get("games", [])

    # Sort by timestamp (newest first) - use match_id as proxy (chronological)
    games = sorted(games, key=lambda g: g.get("match_id", ""), reverse=True)

    # Apply queue filter if specified
    if queue_filter:
        games = [g for g in games if g.get("queue_id") in queue_filter]

    # Transform to standard format
    result = []
    for g in games[:count]:
        duration_min = g.get("duration_min", 0)
        result.append({
            "match_id": g.get("match_id"),
            "champion": g.get("champion"),
            "role": g.get("role", "N/A"),
            "kills": g.get("kills", 0),
            "deaths": g.get("deaths", 0),
            "assists": g.get("assists", 0),
            "cs": g.get("cs_final", 0),
            "damage": g.get("damage", 0),
            "gold": g.get("gold", 0),
            "win": g.get("win", False),
            "duration_str": f"{int(duration_min)}m{int((duration_min % 1) * 60)}s",
            "queue_id": g.get("queue_id"),
            "queue": QUEUE_NAMES.get(g.get("queue_id"), f"Q{g.get('queue_id', 0)}"),
        })

    return result

def get_puuid_by_riot_id(game_name, tag_line):
    """Look up PUUID by Riot ID (Name#TAG)."""
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    r = rl_get(url)
    if r.status_code == 200:
        return r.json().get("puuid")
    return None

def fetch_recent_games(count=20, game_name=None, tag_line=None):
    """Fetch recent games from API (if not in cache or need more)."""
    # Use provided player or default to config
    target_game = game_name or MY_GAME_NAME
    target_tag = tag_line or MY_TAG_LINE

    # First try cache only if it's the config player
    if not game_name:
        cached = get_cached_games(count=count)
        if len(cached) >= count:
            return cached, f"{target_game}#{target_tag}"

    # Need to fetch from API
    print(f"Fetching from API...")

    # Get PUUID
    if game_name:
        puuid = get_puuid_by_riot_id(game_name, tag_line)
    else:
        from facecheck_data import get_puuid
        puuid = get_puuid(MY_GAME_NAME, MY_TAG_LINE)

    if not puuid:
        return [], f"{target_game}#{target_tag}"

    # Fetch recent matches
    match_ids = []
    for qid in QUEUE_FILTERS:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={qid}&count={count}"
        r = rl_get(url)
        if r.status_code == 200:
            match_ids.extend(r.json())

    match_ids = sorted(list(dict.fromkeys(match_ids)), reverse=True)[:count]

    games = []
    for mid in match_ids:
        match = get_match_details(mid)
        if not match:
            continue

        info = match["info"]
        my_stats = next((p for p in info["participants"] if p["puuid"] == puuid), None)
        if not my_stats:
            continue

        duration_sec = info.get("gameDuration", 0)

        games.append({
            "match_id": match["metadata"]["matchId"],
            "champion": my_stats["championName"],
            "role": POSITIONS.get(my_stats.get("teamPosition", ""), my_stats.get("teamPosition", "N/A")),
            "kills": my_stats["kills"],
            "deaths": my_stats["deaths"],
            "assists": my_stats["assists"],
            "cs": my_stats["totalMinionsKilled"] + my_stats["neutralMinionsKilled"],
            "damage": my_stats["totalDamageDealtToChampions"],
            "gold": my_stats["goldEarned"],
            "win": my_stats["win"],
            "duration_str": format_duration(duration_sec),
            "queue_id": info["queueId"],
            "queue": QUEUE_NAMES.get(info["queueId"], f"Q{info['queueId']}"),
        })

    return games, f"{target_game}#{target_tag}"

def print_recent_games(games, player_name):
    """Print formatted game list."""
    wins = sum(1 for g in games if g["win"])
    losses = len(games) - wins
    wr = round(wins / len(games) * 100, 1) if games else 0

    print(f"\n  {'='*95}")
    print(f"  {player_name} — Last {len(games)} Games")
    print(f"  {wins}W {losses}L | {wr}% WR")
    print(f"  {'='*95}")
    print()
    print(f"  {'#':<4} {'Champion':<14} {'Result':<6} {'KDA':<10} {'Role':<8} {'CS':<5} {'Damage':<9} {'Gold':<8} {'Duration':<9} {'Queue'}")
    print(f"  {'-'*88}")

    for i, g in enumerate(games, 1):
        kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
        result = "WIN" if g["win"] else "LOSS"
        role = g['role'][:7]  # Truncate long role names
        dmg = f"{g['damage']:,}"[:8]
        gold = f"{g['gold']:,}"[:7]

        print(f"  {i:<4} {g['champion']:<14} {result:<6} {kda:<10} {role:<8} {g['cs']:<5} {dmg:<9} {gold:<8} {g['duration_str']:<9} {g['queue']}")

    print(f"  {'-'*95}\n")

def run_recent(count=20, riot_id=None):
    """Main entry point."""
    game_name = None
    tag_line = None
    display_name = f"{MY_GAME_NAME}#{MY_TAG_LINE}"

    if riot_id:
        if "#" not in riot_id:
            print(f"  Invalid format. Use: Name#TAG  (e.g. Kuda#MIST)")
            sys.exit(1)
        game_name, tag_line = riot_id.split("#", 1)
        display_name = riot_id

    print(f"\n  Loading recent games for {display_name}...")

    # Try cache first (only for config player)
    if not game_name:
        games = get_cached_games(count=count)
    else:
        games = []

    if len(games) < count:
        # Fetch from API
        games, fetched_name = fetch_recent_games(count=count, game_name=game_name, tag_line=tag_line)
        display_name = fetched_name

    if not games:
        print("  No games found.")
        sys.exit(1)

    print_recent_games(games, display_name)

if __name__ == "__main__":
    count = 20
    riot_id = None

    # Parse arguments: can be [count] or [Name#TAG] or [Name#TAG] [count]
    # Note: PowerShell splits on #, so Name#TAG may come as Name#TAG or Name#TAG#count
    if len(sys.argv) > 1:
        if "#" in sys.argv[1]:
            # First arg contains # - could be Name#TAG or Name#TAG#count
            parts = sys.argv[1].split("#")
            if len(parts) >= 3 and parts[-1].isdigit():
                # Format: Name#TAG#count (PowerShell joined count into the name)
                riot_id = "#".join(parts[:-1])
                count = int(parts[-1])
            else:
                # Format: Name#TAG
                riot_id = sys.argv[1]
                if len(sys.argv) > 2 and sys.argv[2].isdigit():
                    count = int(sys.argv[2])
        elif sys.argv[1].isdigit():
            # First arg is just a count
            count = int(sys.argv[1])

    run_recent(count=count, riot_id=riot_id)
