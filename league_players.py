import requests
import sys

import sys as _sys; _sys.path.insert(0, "C:\\Facecheck")
from config import API_KEY, REGION, PLATFORM, MY_GAME_NAME, MY_TAG_LINE

HEADERS = {"X-Riot-Token": API_KEY}

QUEUE_TYPES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Draft Pick",
    480: "Swiftplay",
    450: "ARAM",
    900: "ARURF",
    0:   "Custom",
}

QUEUE_FILTERS = [420, 440, 400, 480]  # Ranked Solo, Flex, Draft, Swiftplay

POSITIONS = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "BOT",
    "UTILITY": "SUPPORT",
    "": "N/A",
}

def get_puuid(game_name, tag_line):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    return requests.get(url, headers=HEADERS).json()["puuid"]

def get_summoner_id(puuid):
    url = f"https://{PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    return requests.get(url, headers=HEADERS).json().get("id")

def get_match_history(puuid, count=10):
    all_matches = []
    for qid in QUEUE_FILTERS:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={qid}&count=50"
        result = requests.get(url, headers=HEADERS).json()
        if isinstance(result, list):
            all_matches.extend(result)
    all_matches = sorted(list(dict.fromkeys(all_matches)), reverse=True)
    return all_matches[:count]

def get_match_details(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return requests.get(url, headers=HEADERS).json()

def get_riot_id(puuid):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
    data = requests.get(url, headers=HEADERS).json()
    return f"{data.get('gameName', 'Unknown')}#{data.get('tagLine', '???')}"

def format_duration(seconds):
    return f"{seconds // 60}m {seconds % 60}s"

def league_champs(count=10):
    print(f"Fetching account data...")
    my_puuid = get_puuid(MY_GAME_NAME, MY_TAG_LINE)
    matches = get_match_history(my_puuid, count=count)
    print(f"Pulling last {len(matches)} games...\n")

    for i, match_id in enumerate(matches, 1):
        match = get_match_details(match_id)
        info = match["info"]
        queue = QUEUE_TYPES.get(info["queueId"], f"Queue {info['queueId']}")
        duration = format_duration(info["gameDuration"])

        my_team = None
        for p in info["participants"]:
            if p["puuid"] == my_puuid:
                my_team = p["teamId"]
                break

        allies = [p for p in info["participants"] if p["teamId"] == my_team]
        enemies = [p for p in info["participants"] if p["teamId"] != my_team]
        my_result = "WIN" if allies[0]["win"] else "LOSS"

        print(f"  {'='*85}")
        print(f"  [{i}] {queue} — {duration} — {my_result}")
        print(f"  {'='*85}")
        print(f"  {'Side':<8} {'Player':<25} {'Champion':<15} {'KDA':<12} {'CS':<6} {'Dmg':<10} {'Role'}")
        print(f"  {'-'*85}")

        for p in allies:
            riot_id = f"{p.get('riotIdGameName', 'Unknown')}#{p.get('riotIdTagline', '???')}"
            kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
            cs = p["totalMinionsKilled"] + p["neutralMinionsKilled"]
            role = POSITIONS.get(p["teamPosition"], p["teamPosition"])
            print(f"  {'ALLY':<8} {riot_id:<25} {p['championName']:<15} {kda:<12} {cs:<6} {p['totalDamageDealtToChampions']:<10} {role}")

        print(f"  {'-'*85}")

        for p in enemies:
            riot_id = f"{p.get('riotIdGameName', 'Unknown')}#{p.get('riotIdTagline', '???')}"
            kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
            cs = p["totalMinionsKilled"] + p["neutralMinionsKilled"]
            role = POSITIONS.get(p["teamPosition"], p["teamPosition"])
            print(f"  {'ENEMY':<8} {riot_id:<25} {p['championName']:<15} {kda:<12} {cs:<6} {p['totalDamageDealtToChampions']:<10} {role}")

        print()

def get_build_order_for_puuid(match_id, puuid, item_names_map, components):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    timeline = requests.get(url, headers=HEADERS).json()

    participant_id = None
    for p in timeline["info"]["participants"]:
        if p["puuid"] == puuid:
            participant_id = p["participantId"]
            break

    if not participant_id:
        return []

    purchases = []
    for frame in timeline["info"]["frames"]:
        for event in frame["events"]:
            if (event["type"] == "ITEM_PURCHASED" and
                event["participantId"] == participant_id):
                purchases.append(event["itemId"])

    # Filter to finished items only, preserve order, deduplicate
    seen = set()
    result = []
    for iid in purchases:
        if iid not in components and iid not in seen:
            seen.add(iid)
            result.append(item_names_map.get(iid, str(iid)))

    return result

def league_enemies(count=10):
    print(f"Fetching account data...")
    my_puuid = get_puuid(MY_GAME_NAME, MY_TAG_LINE)
    matches = get_match_history(my_puuid, count=count)

    # Fetch item names once
    version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]
    item_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
    item_data = requests.get(item_url).json()["data"]
    item_names_map = {int(k): v["name"] for k, v in item_data.items()}

    components = set()
    for v in item_data.values():
        for comp_id in v.get("from", []):
            components.add(int(comp_id))

    print(f"Pulling enemy same-position for last {len(matches)} games...\n")

    for i, match_id in enumerate(matches, 1):
        match = get_match_details(match_id)
        info = match["info"]
        queue = QUEUE_TYPES.get(info["queueId"], f"Queue {info['queueId']}")
        duration = format_duration(info["gameDuration"])

        my_stats = None
        for p in info["participants"]:
            if p["puuid"] == my_puuid:
                my_stats = p
                break

        if not my_stats:
            continue

        my_role = my_stats["teamPosition"]
        my_team = my_stats["teamId"]
        my_result = "WIN" if my_stats["win"] else "LOSS"

        enemy = None
        for p in info["participants"]:
            if p["teamId"] != my_team and p["teamPosition"] == my_role:
                enemy = p
                break

        if not enemy:
            continue

        enemy_riot_id = f"{enemy.get('riotIdGameName', 'Unknown')}#{enemy.get('riotIdTagline', '???')}"
        enemy_kda = f"{enemy['kills']}/{enemy['deaths']}/{enemy['assists']}"
        enemy_cs = enemy["totalMinionsKilled"] + enemy["neutralMinionsKilled"]
        my_kda = f"{my_stats['kills']}/{my_stats['deaths']}/{my_stats['assists']}"
        my_cs = my_stats["totalMinionsKilled"] + my_stats["neutralMinionsKilled"]

        build_order = get_build_order_for_puuid(match_id, enemy["puuid"], item_names_map, components)

        print(f"  {'='*70}")
        print(f"  [{i}] {queue} — {duration}")
        print(f"  {'='*70}")
        print(f"  {'':8} {'Champion':<15} {'KDA':<12} {'CS':<6} {'Damage':<10} {'Result'}")
        print(f"  {'-'*65}")
        print(f"  {'You':<8} {my_stats['championName']:<15} {my_kda:<12} {my_cs:<6} {my_stats['totalDamageDealtToChampions']:<10} {my_result}")
        print(f"  {'Enemy':<8} {enemy['championName']:<15} {enemy_kda:<12} {enemy_cs:<6} {enemy['totalDamageDealtToChampions']:<10} {'WIN' if enemy['win'] else 'LOSS'}")
        print(f"  Tag:   {enemy_riot_id}")
        if build_order:
            print(f"  Build: {' → '.join(build_order)}")
        print()

def league_enemy_live():
    print(f"Fetching account data...")
    my_puuid = get_puuid(MY_GAME_NAME, MY_TAG_LINE)
    summoner_id = get_summoner_id(my_puuid)

    print(f"Checking for live game...")
    url = f"https://{PLATFORM}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code == 404:
        print("No live game found. You are not currently in a game.")
        return

    game = resp.json()
    participants = game["participants"]

    my_team = None
    my_position = None
    for p in participants:
        if p["puuid"] == my_puuid:
            my_team = p["teamId"]
            # individualPosition is set in ranked/draft; teamPosition is fallback
            my_position = (p.get("individualPosition") or p.get("teamPosition") or "").strip()
            break

    if not my_team:
        print("Could not find you in the live game.")
        return

    enemies = [p for p in participants if p["teamId"] != my_team]
    queue_id = game.get("gameQueueConfigId", 0)
    queue_name = QUEUE_TYPES.get(queue_id, f"Queue {queue_id}")

    print(f"\nLive {queue_name} detected. Scouting enemy team...\n")
    print(f"  {'Champion':<15} {'Summoner':<25} {'Position'}")
    print(f"  {'-'*60}")
    for p in enemies:
        riot_id = get_riot_id(p["puuid"])
        position = POSITIONS.get(p.get("individualPosition") or p.get("teamPosition", ""), "N/A")
        print(f"  {p['championName']:<15} {riot_id:<25} {position}")

    print(f"\nPulling enemy same-position history...")
    enemy_target = None
    if my_position:
        for p in enemies:
            pos = (p.get("individualPosition") or p.get("teamPosition") or "").strip()
            if pos == my_position:
                enemy_target = p
                break

    if not enemy_target:
        # Fallback: just scout the first enemy
        print("Position data unavailable — scouting first enemy in list.")
        enemy_target = enemies[0] if enemies else None

    if not enemy_target:
        print("No enemies found.")
        return

    enemy_riot_id = get_riot_id(enemy_target["puuid"])
    print(f"\nScouting {enemy_riot_id} ({enemy_target['championName']})...\n")

    enemy_puuid = enemy_target["puuid"]
    enemy_matches = get_match_history(enemy_puuid, count=10)

    results = []
    for match_id in enemy_matches:
        match = get_match_details(match_id)
        stats = None
        for p in match["info"]["participants"]:
            if p["puuid"] == enemy_puuid:
                stats = p
                break
        if not stats:
            continue
        queue_id = match["info"]["queueId"]
        results.append({
            "champion": stats["championName"],
            "kda": f"{stats['kills']}/{stats['deaths']}/{stats['assists']}",
            "win": "WIN" if stats["win"] else "LOSS",
            "role": POSITIONS.get(stats["teamPosition"], stats["teamPosition"]),
            "cs": stats["totalMinionsKilled"] + stats["neutralMinionsKilled"],
            "damage": stats["totalDamageDealtToChampions"],
            "duration": format_duration(match["info"]["gameDuration"]),
            "queue": QUEUE_TYPES.get(queue_id, f"Queue {queue_id}"),
        })

    if not results:
        print("No recent games found.")
        return

    wins = sum(1 for r in results if r["win"] == "WIN")
    losses = len(results) - wins

    print(f"  {enemy_riot_id} — Last {len(results)} Games — {wins}W {losses}L ({round(wins/len(results)*100)}% WR)\n")
    print(f"  {'#':<3} {'Champion':<15} {'KDA':<12} {'Result':<6} {'Role':<10} {'CS':<6} {'Damage':<10} {'Duration':<12} {'Queue'}")
    print(f"  {'-'*100}")
    for i, r in enumerate(results, 1):
        print(f"  {i:<3} {r['champion']:<15} {r['kda']:<12} {r['win']:<6} {r['role']:<10} {r['cs']:<6} {r['damage']:<10} {r['duration']:<12} {r['queue']}")

    print()

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    if mode == "champs":
        league_champs(count)
    elif mode == "enemies":
        league_enemies(count)
    elif mode == "live":
        league_enemy_live()
    else:
        print("Usage:")
        print("  league-champs 10     — all players from last N games")
        print("  league-enemies 10    — enemy same-position from last N games")
        print("  league-enemy         — scout enemy in current live game")