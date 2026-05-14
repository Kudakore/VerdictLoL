import requests
import json
import os
import sys
import time
from datetime import datetime

from config import API_KEY, REGION, PLATFORM, MY_GAME_NAME, MY_TAG_LINE
GAME_NAME = MY_GAME_NAME
TAG_LINE  = MY_TAG_LINE
CACHE_PATH = "C:\\Facecheck\\facecheck_cache.json"

HEADERS = {"X-Riot-Token": API_KEY}
QUEUE_FILTERS = [420, 440]
QUEUE_NAMES = {420: "Ranked Solo/Duo", 440: "Ranked Flex"}

POSITIONS = {
    "TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MID",
    "BOTTOM": "BOT", "UTILITY": "SUPPORT", "": "N/A"
}

_last_request_time = 0

def rate_limited_get(url):
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)
    _last_request_time = time.time()
    return requests.get(url, headers=HEADERS)

def get_puuid():
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{GAME_NAME}/{TAG_LINE}"
    return rate_limited_get(url).json()["puuid"]

def get_summoner_id(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    return rate_limited_get(url).json().get("id")

def get_match_ids(puuid, count=50):
    all_matches = []
    for qid in QUEUE_FILTERS:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={qid}&count={count}"
        result = rate_limited_get(url).json()
        if isinstance(result, list):
            all_matches.extend(result)
    return sorted(list(dict.fromkeys(all_matches)), reverse=True)

def get_match(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return rate_limited_get(url).json()

def get_timeline(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    return rate_limited_get(url).json()

def get_rank_snapshot(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    entries = rate_limited_get(url).json()
    if not isinstance(entries, list):
        return None
    snapshot = {"timestamp": datetime.now().isoformat(), "date": datetime.now().strftime("%Y-%m-%d"), "queues": {}}
    queue_map = {"RANKED_SOLO_5x5": "Solo/Duo", "RANKED_FLEX_SR": "Flex"}
    for entry in entries:
        qt = entry.get("queueType")
        if qt not in queue_map:
            continue
        name = queue_map[qt]
        snapshot["queues"][name] = {
            "tier": entry.get("tier", "UNRANKED"),
            "rank": entry.get("rank", ""),
            "lp": entry.get("leaguePoints", 0),
            "wins": entry.get("wins", 0),
            "losses": entry.get("losses", 0),
            "hot_streak": entry.get("hotStreak", False),
            "veteran": entry.get("veteran", False),
            "fresh_blood": entry.get("freshBlood", False),
        }
    return snapshot


def get_current_game(puuid=None):
    """Check if player is in an active game. Returns game dict or None."""
    if puuid is None:
        puuid = get_puuid()
    summoner_id = get_summoner_id(puuid)
    if not summoner_id:
        return None
    url = f"https://{PLATFORM}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


def resolve_puuid_to_riot_id(puuid):
    """Convert PUUID to Riot ID (Name#Tag). Returns None on failure."""
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None
    data = resp.json()
    game_name = data.get("gameName")
    tag_line = data.get("tagLine")
    if not game_name or not tag_line:
        return None
    return f"{game_name}#{tag_line}"


def get_item_data():
    version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
    data = requests.get(url).json()["data"]
    names = {int(k): v["name"] for k, v in data.items()}
    components = set()
    for v in data.values():
        for comp_id in v.get("from", []):
            components.add(int(comp_id))
    return names, components

# ─────────────────────────────────────────────
# TIMELINE PARSING
# ─────────────────────────────────────────────

def extract_build_order(timeline, puuid, item_names, components):
    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break
    if not participant_id:
        return [], None
    purchases = []
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if event["type"] == "ITEM_PURCHASED" and event["participantId"] == participant_id:
                purchases.append({"item_id": event["itemId"], "timestamp_ms": event["timestamp"]})
    seen = set()
    build_order = []
    first_item = None
    for p in purchases:
        iid = p["item_id"]
        if iid not in components and iid not in seen:
            seen.add(iid)
            name = item_names.get(iid, str(iid))
            build_order.append(name)
            if first_item is None:
                first_item = name
    return build_order, first_item

def extract_build_order_for_pid(timeline, participant_id, item_names, components):
    """Build order for any participant by ID."""
    purchases = []
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if event["type"] == "ITEM_PURCHASED" and event["participantId"] == participant_id:
                purchases.append(event["itemId"])
    seen = set()
    build_order = []
    for iid in purchases:
        if iid not in components and iid not in seen:
            seen.add(iid)
            build_order.append(item_names.get(iid, str(iid)))
    return build_order

def extract_cs_snapshots(timeline, puuid):
    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break
    if not participant_id:
        return None, None
    cs_10 = cs_15 = None
    for frame in timeline["info"]["frames"]:
        ts_min = frame["timestamp"] / 60000
        pf = frame.get("participantFrames", {}).get(str(participant_id), {})
        minions = pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0)
        if ts_min >= 10 and cs_10 is None:
            cs_10 = minions
        if ts_min >= 15 and cs_15 is None:
            cs_15 = minions
            break
    return cs_10, cs_15

def extract_jungle_pathing(timeline, puuid):
    """
    Extract CS progression at 5-min intervals for jungle pathing analysis.
    Returns: dict with cs_at_5, cs_at_10, cs_at_15, first_clear_complete_min
    """
    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break
    if not participant_id:
        return None

    cs_snapshots = {}
    first_clear_min = None

    for frame in timeline["info"]["frames"]:
        ts_min = int(frame["timestamp"] / 60000)
        pf = frame.get("participantFrames", {}).get(str(participant_id), {})
        minions = pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0)

        # Track CS at each minute
        if ts_min not in cs_snapshots:
            cs_snapshots[ts_min] = minions

        # First clear = ~28 CS (6 camps) or ~20 CS (4 camps + scuttle)
        # Most junglers hit this around 3:00-3:30
        if first_clear_min is None and minions >= 20:
            first_clear_min = ts_min

    return {
        "cs_by_minute": cs_snapshots,
        "cs_at_5": cs_snapshots.get(5, 0),
        "cs_at_10": cs_snapshots.get(10, 0),
        "cs_at_15": cs_snapshots.get(15, 0),
        "first_clear_min": first_clear_min,
    }

def extract_early_deaths(timeline, puuid):
    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break
    if not participant_id:
        return 0
    early_deaths = 0
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if (event["type"] == "CHAMPION_KILL" and
                event.get("victimId") == participant_id and
                event["timestamp"] < 900000):
                early_deaths += 1
    return early_deaths

def extract_death_minutes(timeline, puuid):
    """Extract all death timestamps as minute markers for heatmap analysis."""
    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break
    if not participant_id:
        return []
    death_minutes = []
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if (event["type"] == "CHAMPION_KILL" and
                event.get("victimId") == participant_id):
                minute = int(event["timestamp"] / 60000)
                death_minutes.append(minute)
    return death_minutes

def extract_gold_at_15(timeline, participant_id):
    gold_15 = None
    for frame in timeline["info"]["frames"]:
        ts_min = frame["timestamp"] / 60000
        if ts_min >= 15 and gold_15 is None:
            pf = frame.get("participantFrames", {}).get(str(participant_id), {})
            gold_15 = pf.get("totalGold", None)
            break
    return gold_15

def extract_killed_by_enemy_jungler(timeline, my_pid, enemy_jungler_pid):
    count = 0
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if (event["type"] == "CHAMPION_KILL" and
                event.get("victimId") == my_pid and
                event.get("killerId") == enemy_jungler_pid):
                count += 1
    return count

# ─────────────────────────────────────────────
# PLAYER STAT EXTRACTOR
# ─────────────────────────────────────────────

def extract_player_stats(p, item_names, components, timeline_pid_map, timeline, duration_min):
    """Full stat extraction for any participant."""
    cs = p["totalMinionsKilled"] + p["neutralMinionsKilled"]
    pid = timeline_pid_map.get(p["puuid"])

    # Build order from timeline
    build_order = []
    if pid:
        build_order = extract_build_order_for_pid(timeline, pid, item_names, components)

    # Final items (finished only)
    final_items = [p.get(f"item{i}", 0) for i in range(6)]
    final_items = [iid for iid in final_items if iid != 0 and iid not in components]
    final_item_names = [item_names.get(iid, str(iid)) for iid in final_items]

    return {
        "champion": p["championName"],
        "role": POSITIONS.get(p.get("teamPosition", ""), p.get("teamPosition", "N/A")),
        "kills": p["kills"],
        "deaths": p["deaths"],
        "assists": p["assists"],
        "cs": cs,
        "cs_per_min": round(cs / duration_min, 1) if duration_min > 0 else 0,
        "damage": p["totalDamageDealtToChampions"],
        "damage_per_min": round(p["totalDamageDealtToChampions"] / duration_min, 0) if duration_min > 0 else 0,
        "gold": p["goldEarned"],
        "gold_per_min": round(p["goldEarned"] / duration_min, 0) if duration_min > 0 else 0,
        "vision": p["visionScore"],
        "vision_per_min": round(p["visionScore"] / duration_min, 2) if duration_min > 0 else 0,
        "wards_placed": p.get("wardsPlaced", 0),
        "wards_killed": p.get("wardsKilled", 0),
        "control_wards": p.get("detectorWardsPlaced", 0),
        "first_blood_kill": p.get("firstBloodKill", False),
        "first_blood_assist": p.get("firstBloodAssist", False),
        "turret_kills": p.get("turretKills", 0),
        "inhibitor_kills": p.get("inhibitorKills", 0),
        "total_heal": p.get("totalHeal", 0),
        "damage_mitigated": p.get("damageSelfMitigated", 0),
        "cc_time": p.get("timeCCingOthers", 0),
        "longest_living": p.get("longestTimeSpentLiving", 0),
        "largest_killing_spree": p.get("largestKillingSpree", 0),
        "time_spent_dead": p.get("timeSpentDead", 0),
        "heals_on_teammates": p.get("totalHealsOnTeammates", 0),
        "damage_shielded": p.get("totalDamageShieldedOnTeammates", 0),
        "total_damage_taken": p.get("totalDamageTaken", 0),
        "physical_damage_taken": p.get("physicalDamageTaken", 0),
        "magic_damage_taken": p.get("magicalDamageTaken", 0),
        "objectives_stolen": p.get("objectivesStolen", 0),
        "bounty_level": p.get("bountyLevel", 0),
        "spell1_casts": p.get("spell1Casts", 0),
        "spell2_casts": p.get("spell2Casts", 0),
        "spell3_casts": p.get("spell3Casts", 0),
        "spell4_casts": p.get("spell4Casts", 0),
        "double_kills": p.get("doubleKills", 0),
        "triple_kills": p.get("tripleKills", 0),
        "quadra_kills": p.get("quadraKills", 0),
        "penta_kills": p.get("pentaKills", 0),
        "build_order": build_order,
        "final_items": final_item_names,
        "win": p["win"],
        "puuid": p["puuid"],
    }

# ─────────────────────────────────────────────
# MATCH RECORD BUILDER
# ─────────────────────────────────────────────

def build_match_record(match_id, match, timeline, puuid, item_names, components):
    info = match["info"]

    my_stats = None
    for p in info["participants"]:
        if p["puuid"] == puuid:
            my_stats = p
            break
    if not my_stats:
        return None

    my_team_id = my_stats["teamId"]
    side = "blue" if my_team_id == 100 else "red"
    my_role = my_stats["teamPosition"]

    # Pick order — participantId encodes draft order (1-5 blue, 6-10 red)
    my_pid = my_stats.get("participantId", 0)
    my_pick_order = my_pid if my_pid <= 5 else my_pid - 5
    enemy_pick_order = None
    for p in info["participants"]:
        if p["teamId"] != my_team_id and p.get("teamPosition") == my_role:
            ep = p.get("participantId", 0)
            enemy_pick_order = ep if ep <= 5 else ep - 5
            break
    duration_min = info["gameDuration"] / 60

    # Build timeline pid map (puuid -> participantId)
    timeline_pid_map = {tp["puuid"]: tp["participantId"] for tp in timeline["info"]["participants"]}
    my_pid = timeline_pid_map.get(puuid)

    # Find enemy jungler
    enemy_stats = None
    enemy_jungler_pid = None
    for p in info["participants"]:
        if p["teamId"] != my_team_id and p["teamPosition"] == my_role:
            enemy_stats = p
            enemy_jungler_pid = timeline_pid_map.get(p["puuid"])
            break

    # My build
    build_order, first_item = extract_build_order(timeline, puuid, item_names, components)
    cs_10, cs_15 = extract_cs_snapshots(timeline, puuid)
    early_deaths = extract_early_deaths(timeline, puuid)
    death_minutes = extract_death_minutes(timeline, puuid)
    jungle_pathing = extract_jungle_pathing(timeline, puuid) if my_role == "JUNGLE" else None

    # Gold at 15
    gold_15 = extract_gold_at_15(timeline, my_pid) if my_pid else None
    enemy_gold_15 = extract_gold_at_15(timeline, enemy_jungler_pid) if enemy_jungler_pid else None
    gold_lead_15 = (gold_15 - enemy_gold_15) if gold_15 and enemy_gold_15 else None

    # Killed by enemy jungler
    killed_by_enemy_jungler = 0
    if my_pid and enemy_jungler_pid:
        killed_by_enemy_jungler = extract_killed_by_enemy_jungler(timeline, my_pid, enemy_jungler_pid)

    final_cs = my_stats["totalMinionsKilled"] + my_stats["neutralMinionsKilled"]

    # Final items (finished only)
    my_final_items = [my_stats.get(f"item{i}", 0) for i in range(6)]
    my_final_items = [iid for iid in my_final_items if iid != 0 and iid not in components]
    my_final_item_names = [item_names.get(iid, str(iid)) for iid in my_final_items]

    # All 10 players full stats
    all_players = []
    for p in info["participants"]:
        player_data = extract_player_stats(p, item_names, components, timeline_pid_map, timeline, duration_min)
        player_data["team"] = "ally" if p["teamId"] == my_team_id else "enemy"
        player_data["is_me"] = p["puuid"] == puuid
        all_players.append(player_data)

    # Team objectives
    my_team_obj = {}
    enemy_team_obj = {}
    for team in info.get("teams", []):
        obj = team.get("objectives", {})
        target = my_team_obj if team["teamId"] == my_team_id else enemy_team_obj
        target["dragon_kills"] = obj.get("dragon", {}).get("kills", 0)
        target["baron_kills"] = obj.get("baron", {}).get("kills", 0)
        target["tower_kills"] = obj.get("tower", {}).get("kills", 0)
        target["rift_herald_kills"] = obj.get("riftHerald", {}).get("kills", 0)
        target["first_blood"] = obj.get("champion", {}).get("first", False)
        target["first_tower"] = obj.get("tower", {}).get("first", False)
        target["first_dragon"] = obj.get("dragon", {}).get("first", False)
        target["first_baron"] = obj.get("baron", {}).get("first", False)

    # Team KDA totals
    my_team_kills = sum(p["kills"] for p in info["participants"] if p["teamId"] == my_team_id)
    my_team_deaths = sum(p["deaths"] for p in info["participants"] if p["teamId"] == my_team_id)
    enemy_team_kills = sum(p["kills"] for p in info["participants"] if p["teamId"] != my_team_id)
    enemy_team_deaths = sum(p["deaths"] for p in info["participants"] if p["teamId"] != my_team_id)

    record = {
        "match_id": match_id,
        "queue": QUEUE_NAMES.get(info["queueId"], f"Queue {info['queueId']}"),
        "queue_id": info["queueId"],
        "side": side,
        "win": my_stats["win"],
        "champion": my_stats["championName"],
        "role": my_role,
        "duration_min": round(duration_min, 1),

        # Personal stats
        "kills": my_stats["kills"],
        "deaths": my_stats["deaths"],
        "assists": my_stats["assists"],
        "cs_final": final_cs,
        "cs_10": cs_10,
        "cs_15": cs_15,
        "cs_per_min": round(final_cs / duration_min, 1) if duration_min > 0 else 0,
        "early_deaths": early_deaths,
        "death_minutes": death_minutes,
        "jungle_pathing": jungle_pathing,
        "killed_by_enemy_jungler": killed_by_enemy_jungler,
        "damage": my_stats["totalDamageDealtToChampions"],
        "damage_per_min": round(my_stats["totalDamageDealtToChampions"] / duration_min, 0) if duration_min > 0 else 0,
        "vision": my_stats["visionScore"],
        "vision_per_min": round(my_stats["visionScore"] / duration_min, 2) if duration_min > 0 else 0,
        "gold": my_stats["goldEarned"],
        "gold_per_min": round(my_stats["goldEarned"] / duration_min, 0) if duration_min > 0 else 0,
        "gold_15": gold_15,
        "gold_lead_15": gold_lead_15,

        # Extended personal stats
        "wards_placed": my_stats.get("wardsPlaced", 0),
        "wards_killed": my_stats.get("wardsKilled", 0),
        "control_wards": my_stats.get("detectorWardsPlaced", 0),
        "first_blood_kill": my_stats.get("firstBloodKill", False),
        "first_blood_assist": my_stats.get("firstBloodAssist", False),
        "turret_kills": my_stats.get("turretKills", 0),
        "inhibitor_kills": my_stats.get("inhibitorKills", 0),
        "total_heal": my_stats.get("totalHeal", 0),
        "damage_mitigated": my_stats.get("damageSelfMitigated", 0),
        "cc_time": my_stats.get("timeCCingOthers", 0),
        "longest_living": my_stats.get("longestTimeSpentLiving", 0),
        "largest_killing_spree": my_stats.get("largestKillingSpree", 0),
        "time_spent_dead": my_stats.get("timeSpentDead", 0),
        "heals_on_teammates": my_stats.get("totalHealsOnTeammates", 0),
        "damage_shielded": my_stats.get("totalDamageShieldedOnTeammates", 0),
        "total_damage_taken": my_stats.get("totalDamageTaken", 0),
        "physical_damage_taken": my_stats.get("physicalDamageTaken", 0),
        "magic_damage_taken": my_stats.get("magicalDamageTaken", 0),
        "objectives_stolen": my_stats.get("objectivesStolen", 0),
        "bounty_level": my_stats.get("bountyLevel", 0),
        "spell1_casts": my_stats.get("spell1Casts", 0),
        "spell2_casts": my_stats.get("spell2Casts", 0),
        "spell3_casts": my_stats.get("spell3Casts", 0),
        "spell4_casts": my_stats.get("spell4Casts", 0),
        "double_kills": my_stats.get("doubleKills", 0),
        "triple_kills": my_stats.get("tripleKills", 0),
        "quadra_kills": my_stats.get("quadraKills", 0),
        "penta_kills": my_stats.get("pentaKills", 0),
        "final_items": my_final_item_names,

        # Build
        "build_order": build_order,
        "first_item": first_item,
        "pick_order": my_pick_order,
        "enemy_pick_order": enemy_pick_order,

        # Enemy same-position
        "enemy": {
            "champion": enemy_stats["championName"],
            "kills": enemy_stats["kills"],
            "deaths": enemy_stats["deaths"],
            "assists": enemy_stats["assists"],
            "cs": enemy_stats["totalMinionsKilled"] + enemy_stats["neutralMinionsKilled"],
            "damage": enemy_stats["totalDamageDealtToChampions"],
            "win": enemy_stats["win"],
            "gold": enemy_stats["goldEarned"],
            "gold_15": enemy_gold_15,
            "vision": enemy_stats["visionScore"],
            "wards_placed": enemy_stats.get("wardsPlaced", 0),
            "control_wards": enemy_stats.get("detectorWardsPlaced", 0),
            "first_blood_kill": enemy_stats.get("firstBloodKill", False),
            "turret_kills": enemy_stats.get("turretKills", 0),
        } if enemy_stats else None,

        # All 10 players
        "all_players": all_players,

        # Team context
        "my_team": {
            "kills": my_team_kills,
            "deaths": my_team_deaths,
            **my_team_obj,
        },
        "enemy_team": {
            "kills": enemy_team_kills,
            "deaths": enemy_team_deaths,
            **enemy_team_obj,
        },
    }

    return record

# ─────────────────────────────────────────────
# CACHE MANAGEMENT
# ─────────────────────────────────────────────

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"puuid": None, "games": [], "cached_ids": [], "rank_history": [], "last_updated": None}

def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

# ─────────────────────────────────────────────
# RANK HELPERS
# ─────────────────────────────────────────────

def get_current_rank_string(cache_or_entries):
    """Extract most recent Solo/Duo rank string from cache or rank entries list."""
    if isinstance(cache_or_entries, dict):
        entries = cache_or_entries.get("rank_history", [])
    else:
        entries = cache_or_entries
    if not entries:
        return None
    latest = max(entries, key=lambda e: e.get("timestamp", ""))
    q = latest.get("queues", {})
    solo = q.get("Solo/Duo")
    if not solo:
        return None
    tier = solo.get("tier", "UNRANKED").capitalize()
    rank = solo.get("rank", "")
    lp = solo.get("lp", 0)
    return f"{tier} {rank} — {lp} LP" if rank else f"{tier} — {lp} LP"

def get_ranked_games(cache, champion=None, count=None):
    """Return ranked games only, optionally filtered by champion and count."""
    games = [g for g in cache.get("games", []) if g.get("queue_id") in (420, 440)]
    if champion:
        games = [g for g in games if g["champion"].lower() == champion.lower()]
    if count:
        games = games[:count]
    return games


def resolve_riot_id(riot_id):
    """Resolve a Riot ID (Name#Tag) to (puuid, player_id) tuple. Returns (None, None) on failure."""
    if "#" not in riot_id:
        return None, None
    game_name, tag_line = riot_id.split("#", 1)
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = rate_limited_get(url).json()
    if "puuid" not in resp:
        return None, None
    puuid = resp["puuid"]
    player_id = f"{game_name}#{tag_line}"
    return puuid, player_id


def fetch_player_games(riot_id, count=20):
    """
    Fetch any player's ranked games with full timeline data.
    Returns (games, player_id) tuple, or (None, None) on failure.
    Caches per-player in scout_cache/{safe_id}_cache.json.
    """
    puuid, player_id = resolve_riot_id(riot_id)
    if not puuid:
        print(f"Player not found: {riot_id}")
        return None, None

    # Per-player scout cache
    safe_id = player_id.replace("#", "_").replace(" ", "_")
    scout_dir = "C:\\Facecheck\\scout_cache"
    os.makedirs(scout_dir, exist_ok=True)
    scout_path = os.path.join(scout_dir, f"{safe_id}_cache.json")

    # Load existing scout cache
    if os.path.exists(scout_path):
        with open(scout_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {"puuid": puuid, "player_id": player_id, "games": [], "cached_ids": [], "last_updated": None}

    print(f"Scouting {player_id}...")

    print("Fetching rank data...")
    snapshot = get_rank_snapshot(puuid)
    if snapshot:
        for queue_name, data in snapshot["queues"].items():
            tier = data["tier"].capitalize()
            rank = data["rank"]
            lp = data["lp"]
            wins = data["wins"]
            losses = data["losses"]
            streak = " 🔥" if data.get("hot_streak") else ""
            print(f"  {queue_name}: {tier} {rank} — {lp} LP — {wins}W {losses}L{streak}")

    print("Fetching item data...")
    item_names, components = get_item_data()

    print(f"Fetching match IDs (up to {count})...")
    match_ids = get_match_ids(puuid, count=count)

    cached_ids = set(cache.get("cached_ids", []))
    new_ids = [m for m in match_ids if m not in cached_ids]

    if not new_ids:
        print(f"Cache up to date. {len(cache['games'])} games loaded.")
        return cache["games"][:count], player_id

    print(f"Fetching {len(new_ids)} new games (rate limited ~1.5s/call)...")
    estimated = len(new_ids) * 2 * 1.5
    print(f"Estimated time: ~{round(estimated / 60, 1)} minutes\n")

    new_records = []
    for i, match_id in enumerate(new_ids, 1):
        print(f"  [{i}/{len(new_ids)}] {match_id}...")
        try:
            match = get_match(match_id)
            timeline = get_timeline(match_id)
            record = build_match_record(match_id, match, timeline, puuid, item_names, components)
            if record:
                new_records.append(record)
                cached_ids.add(match_id)
        except Exception as e:
            print(f"  Error on {match_id}: {e}")
            continue

    cache["games"] = new_records + cache.get("games", [])
    cache["cached_ids"] = list(cached_ids)
    cache["last_updated"] = datetime.now().isoformat()

    with open(scout_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

    print(f"\nCache updated. {len(cache['games'])} total games for {player_id}.")
    return cache["games"][:count], player_id


# ─────────────────────────────────────────────
# MAIN FETCH
# ─────────────────────────────────────────────

def fetch_and_cache(count=50, force=False):
    cache = load_cache()

    print("Fetching account data...")
    puuid = get_puuid()
    cache["puuid"] = puuid

    print("Fetching rank data...")
    snapshot = get_rank_snapshot(puuid)
    if snapshot:
        if "rank_history" not in cache:
            cache["rank_history"] = []
        cache["rank_history"].append(snapshot)
        for queue_name, data in snapshot["queues"].items():
            tier = data["tier"].capitalize()
            rank = data["rank"]
            lp = data["lp"]
            wins = data["wins"]
            losses = data["losses"]
            streak = " 🔥" if data["hot_streak"] else ""
            print(f"  {queue_name}: {tier} {rank} — {lp} LP — {wins}W {losses}L{streak}")

    print("Fetching item data...")
    item_names, components = get_item_data()

    print("Fetching match IDs...")
    match_ids = get_match_ids(puuid, count=count)

    cached_ids = set(cache.get("cached_ids", []))
    new_ids = [m for m in match_ids if m not in cached_ids] if not force else match_ids

    if not new_ids:
        print(f"Cache up to date. {len(cache['games'])} games loaded.")
        save_cache(cache)
        return cache

    print(f"Fetching {len(new_ids)} new games (rate limited ~1.5s/call)...")
    estimated = len(new_ids) * 2 * 1.5
    print(f"Estimated time: ~{round(estimated / 60, 1)} minutes\n")

    new_records = []
    for i, match_id in enumerate(new_ids, 1):
        print(f"  [{i}/{len(new_ids)}] {match_id}...")
        try:
            match = get_match(match_id)
            timeline = get_timeline(match_id)
            record = build_match_record(match_id, match, timeline, puuid, item_names, components)
            if record:
                new_records.append(record)
                cached_ids.add(match_id)
        except Exception as e:
            print(f"  Error on {match_id}: {e}")
            continue

    cache["games"] = new_records + cache.get("games", [])
    cache["cached_ids"] = list(cached_ids)
    cache["last_updated"] = datetime.now().isoformat()
    save_cache(cache)

    print(f"\nCache updated. {len(cache['games'])} total games.")
    return cache

if __name__ == "__main__":
    force = "--force" in sys.argv
    count = 50
    for arg in sys.argv[1:]:
        if arg.isdigit():
            count = int(arg)
    fetch_and_cache(count=count, force=force)
