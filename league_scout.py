import requests
import sys

import sys, os; sys.path.insert(0, "C:\\Scripts")
from config import API_KEY, REGION, PLATFORM

HEADERS = {"X-Riot-Token": API_KEY}

QUEUE_TYPES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Draft Pick",
    430: "Blind Pick",
    900: "ARURF",
    480: "Swiftplay",
    450: "ARAM",
    0:   "Custom",
}

POSITIONS = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "BOT",
    "UTILITY": "SUPPORT",
    "": "N/A",
}

def get_puuid_by_riot_id(game_name, tag_line):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = requests.get(url, headers=HEADERS).json()
    if "puuid" not in resp:
        print(f"Player not found: {game_name}#{tag_line}")
        return None
    return resp["puuid"]

def get_match_history(puuid, count=10):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count={count}"
    return requests.get(url, headers=HEADERS).json()

def get_match_details(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return requests.get(url, headers=HEADERS).json()

def get_stats_for_puuid(match_data, puuid):
    for p in match_data["info"]["participants"]:
        if p["puuid"] == puuid:
            return p
    return None

def format_duration(seconds):
    return f"{seconds // 60}m {seconds % 60}s"

def scout(riot_id, count=10):
    if "#" not in riot_id:
        print("Usage: league scout Name#TAG  (e.g. face scout Faker#T1)")
        return

    game_name, tag_line = riot_id.split("#", 1)
    print(f"Scouting {game_name}#{tag_line}...")
    puuid = get_puuid_by_riot_id(game_name, tag_line)
    if not puuid:
        return

    matches = get_match_history(puuid, count=count)
    if not matches:
        print("No recent games found.")
        return

    results = []
    for match_id in matches:
        match = get_match_details(match_id)
        stats = get_stats_for_puuid(match, puuid)
        if not stats:
            continue
        queue_id = match["info"]["queueId"]
        results.append({
            "champion": stats["championName"],
            "kda": f"{stats['kills']}/{stats['deaths']}/{stats['assists']}",
            "win": "WIN" if stats["win"] else "LOSS",
            "role": POSITIONS.get(stats["teamPosition"], stats["teamPosition"] or "N/A"),
            "cs": stats["totalMinionsKilled"] + stats["neutralMinionsKilled"],
            "damage": stats["totalDamageDealtToChampions"],
            "duration": format_duration(match["info"]["gameDuration"]),
            "queue": QUEUE_TYPES.get(queue_id, f"Queue {queue_id}"),
        })

    if not results:
        print("No games found.")
        return

    wins = sum(1 for r in results if r["win"] == "WIN")
    losses = len(results) - wins

    print(f"\n{game_name}#{tag_line} — Last {len(results)} Games")
    print(f"{'#':<3} {'Champion':<15} {'KDA':<12} {'Result':<6} {'Role':<10} {'CS':<6} {'Damage':<10} {'Duration':<12} {'Queue'}")
    print("-" * 100)
    for i, r in enumerate(results, 1):
        print(f"{i:<3} {r['champion']:<15} {r['kda']:<12} {r['win']:<6} {r['role']:<10} {r['cs']:<6} {r['damage']:<10} {r['duration']:<12} {r['queue']}")

    print(f"\nRecord: {wins}W {losses}L | Winrate: {round(wins/len(results)*100)}%")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: league scout Name#TAG")
        sys.exit(1)

    # Rejoin args — handles PowerShell passing string as individual chars
    count = 10
    digit_args = [a for a in args if a.isdigit()]
    str_args   = [a for a in args if not a.isdigit()]
    if digit_args:
        count = int(digit_args[0])
    if str_args:
        if all(len(a) == 1 for a in str_args):
            riot_id = "".join(str_args)
        else:
            riot_id = str_args[0]
    else:
        print("Usage: league scout Name#TAG")
        sys.exit(1)

    scout(riot_id, count)
