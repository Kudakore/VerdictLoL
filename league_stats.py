import requests
import json
import sys

from verdict_config import ensure_config; ensure_config()
from config import API_KEY, REGION, PLATFORM, MY_GAME_NAME, MY_TAG_LINE
GAME_NAME = MY_GAME_NAME
TAG_LINE  = MY_TAG_LINE

HEADERS = {"X-Riot-Token": API_KEY}

QUEUE_TYPES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Draft Pick",
    900: "ARURF",
    480: "Swiftplay",
    450: "ARAM",
    0:   "Custom",
}

QUEUE_FILTERS = {
    "solo":     [420],
    "flex":     [440],
    "unranked": [400, 480],
    "all":      [420, 440, 400, 480],
}

def get_puuid():
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{GAME_NAME}/{TAG_LINE}"
    return requests.get(url, headers=HEADERS).json()["puuid"]

def get_match_history(puuid, queue_ids, count=20):
    all_matches = []
    for qid in queue_ids:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={qid}&count=50"
        result = requests.get(url, headers=HEADERS).json()
        if isinstance(result, list):
            all_matches.extend(result)
    all_matches = sorted(list(dict.fromkeys(all_matches)), reverse=True)
    return all_matches[:count]

def get_match_details(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return requests.get(url, headers=HEADERS).json()

def get_my_stats(match_data, puuid):
    for p in match_data["info"]["participants"]:
        if p["puuid"] == puuid:
            return p
    return None

def get_build_order(match_id, puuid):
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
                purchases.append({
                    "item_id": event["itemId"],
                    "timestamp": event["timestamp"]
                })

    return purchases

def format_duration(seconds):
    return f"{seconds // 60}m {seconds % 60}s"

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

def run(filter_key, count=10, show_items=False):
    print(f"Fetching account data...")
    puuid = get_puuid()
    queue_ids = QUEUE_FILTERS.get(filter_key, QUEUE_FILTERS["all"])
    print(f"Fetching last {count} [{filter_key.upper()}] games...\n")
    matches = get_match_history(puuid, queue_ids, count=count)

    item_names = None
    item_components = None
    if show_items:
        print("Fetching item data...")
        item_names, item_components = get_item_data()

    results = []
    for match_id in matches[:count]:
        match = get_match_details(match_id)
        stats = get_my_stats(match, puuid)
        if not stats:
            continue
        queue_id = match["info"]["queueId"]
        my_role = stats["teamPosition"]
        my_team = stats["teamId"]

        enemy = None
        if my_role:
            for p in match["info"]["participants"]:
                if (p["teamId"] != my_team and
                    p["teamPosition"] == my_role and
                    p["puuid"] != puuid):
                    enemy = p
                    break

        items_built = [stats.get(f"item{i}", 0) for i in range(6)]
        items_built = [i for i in items_built if i != 0]

        build_order = []
        if show_items and item_components:
            purchases = get_build_order(match_id, puuid)
            build_order = [p["item_id"] for p in purchases
                          if p["item_id"] not in item_components
                          and p["item_id"] in items_built]
            seen = set()
            build_order = [x for x in build_order if not (x in seen or seen.add(x))]

        results.append({
            "champion": stats["championName"],
            "kda": f"{stats['kills']}/{stats['deaths']}/{stats['assists']}",
            "win": "WIN" if stats["win"] else "LOSS",
            "role": my_role or "N/A",
            "cs": stats["totalMinionsKilled"] + stats["neutralMinionsKilled"],
            "damage": stats["totalDamageDealtToChampions"],
            "duration": format_duration(match["info"]["gameDuration"]),
            "vision": stats["visionScore"],
            "queue": QUEUE_TYPES.get(queue_id, f"Queue {queue_id}"),
            "items": items_built,
            "build_order": build_order,
            "enemy": {
                "champion": enemy["championName"],
                "kda": f"{enemy['kills']}/{enemy['deaths']}/{enemy['assists']}",
                "cs": enemy["totalMinionsKilled"] + enemy["neutralMinionsKilled"],
                "damage": enemy["totalDamageDealtToChampions"],
                "win": "WIN" if enemy["win"] else "LOSS",
            } if enemy else None,
        })

    if not results:
        print("No games found.")
        return

    wins = sum(1 for r in results if r["win"] == "WIN")
    losses = len(results) - wins

    print(f"Record: {wins}W {losses}L | Winrate: {round(wins/len(results)*100)}%\n")

    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['queue']} — {r['duration']}")
        print(f"  {'You':<8} {r['champion']:<15} {r['kda']:<12} {r['win']:<6} {r['role']:<10} CS: {r['cs']:<6} Vision: {r['vision']:<6} Dmg: {r['damage']}")

        if r["win"] == "LOSS" and r.get("enemy"):
            e = r["enemy"]
            print(f"  {'Enemy':<8} {e['champion']:<15} {e['kda']:<12} {e['win']:<6} {r['role']:<10} CS: {e['cs']:<6}              Dmg: {e['damage']}")

        if show_items and item_names and r["items"]:
            display_items = r.get("build_order") if r.get("build_order") else r["items"]
            names = [item_names.get(iid, str(iid)) for iid in display_items]
            print(f"  {'Build':<8} {' → '.join(names)}")

        print()

def get_champ_builds(puuid, champion_name, count=30):
    print(f"Fetching item data...")
    item_names, item_components = get_item_data()

    print(f"Fetching {champion_name} games...")
    matches = get_match_history(puuid, QUEUE_FILTERS["solo"], count=count)

    item_wins = {}
    item_games = {}
    games_found = 0

    for match_id in matches:
        match = get_match_details(match_id)
        stats = get_my_stats(match, puuid)
        if not stats:
            continue
        if stats["championName"].lower() != champion_name.lower():
            continue

        games_found += 1
        won = stats["win"]
        items = [stats.get(f"item{i}", 0) for i in range(6)]
        items = [i for i in items if i != 0]
        items = [i for i in items if i not in item_components]

        for item_id in items:
            item_wins[item_id] = item_wins.get(item_id, 0) + (1 if won else 0)
            item_games[item_id] = item_games.get(item_id, 0) + 1

    if games_found == 0:
        print(f"No solo/duo games found on {champion_name}.")
        return

    print(f"\n{champion_name} — Item Stats ({games_found} games, finished items only)")
    print(f"{'Item':<30} {'Games':<8} {'Wins':<8} {'Winrate'}")
    print("-" * 60)

    results = []
    for item_id, games in item_games.items():
        if games < 2:
            continue
        wins = item_wins.get(item_id, 0)
        winrate = round(wins / games * 100)
        name = item_names.get(item_id, f"Item {item_id}")
        results.append((name, games, wins, winrate))

    results.sort(key=lambda x: x[1], reverse=True)
    for name, games, wins, winrate in results:
        print(f"{name:<30} {games:<8} {wins:<8} {winrate}%")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    raw = sys.argv[2:]  # everything after the mode

    if mode == "builds":
        # Rejoin char-split champion name
        digit_args = [a for a in raw if a.isdigit()]
        str_args   = [a for a in raw if not a.isdigit()]
        count = int(digit_args[0]) if digit_args else 30
        if str_args:
            champion = "".join(str_args) if all(len(a) == 1 for a in str_args) else " ".join(str_args)
        else:
            champion = "Viego"
        puuid = get_puuid()
        get_champ_builds(puuid, champion, count)
    elif mode == "items":
        filter_key = raw[0] if raw and not raw[0].isdigit() else "solo"
        digit_args = [a for a in raw if a.isdigit()]
        count = int(digit_args[0]) if digit_args else 10
        run(filter_key, count, show_items=True)
    else:
        digit_args = [a for a in raw if a.isdigit()]
        count = int(digit_args[0]) if digit_args else 10
        run(mode, count)
