import requests
import json
import sys
import os

ITEMS_URL = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/items.json"
CHAMPS_URL = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json"

def fetch_items():
    return requests.get(ITEMS_URL).json()

def fetch_champions():
    return requests.get(CHAMPS_URL).json()

def find_item(items, query):
    query = query.lower()
    # Exact match first
    exact = [i for i in items if i["name"].lower() == query and i["inStore"]]
    if exact:
        return exact
    # Word-boundary contains — whole word match to avoid "c" matching "Faerie Charm"
    # Only match if query is a meaningful substring (3+ chars)
    if len(query) >= 3:
        return [i for i in items if query in i["name"].lower() and i["inStore"]]
    return []

def get_item_by_id(items, item_id):
    for i in items:
        if i["id"] == item_id:
            return i
    return None

def show_build_path(items, item):
    print(f"\n{'='*50}")
    print(f"  {item['name']}")
    print(f"  Total Cost: {item['priceTotal']} gold | Base Cost: {item['price']} gold")
    print(f"  Categories: {', '.join(item.get('categories', []))}")
    print(f"{'='*50}")

    if item["from"]:
        print(f"\n  Builds from:")
        for comp_id in item["from"]:
            comp = get_item_by_id(items, comp_id)
            if comp:
                print(f"    - {comp['name']} ({comp['priceTotal']}g)")
                if comp["from"]:
                    for sub_id in comp["from"]:
                        sub = get_item_by_id(items, sub_id)
                        if sub:
                            print(f"      \u2514\u2500 {sub['name']} ({sub['priceTotal']}g)")

    if item["to"]:
        print(f"\n  Builds into:")
        for upgrade_id in item["to"]:
            upgrade = get_item_by_id(items, upgrade_id)
            if upgrade:
                print(f"    - {upgrade['name']} ({upgrade['priceTotal']}g)")

def show_item(query):
    # Handle char-split from PowerShell
    if len(query) == 1:
        print(f"Query too short: '{query}'. Type the full item name.")
        return
    print(f"Fetching item data...")
    items = fetch_items()
    results = find_item(items, query)
    if not results:
        print(f"No items found matching '{query}'")
        return
    show_build_path(items, results[0])

STAT_LABELS = {
    "hp": "Base HP",
    "hpperlevel": "HP per Level",
    "mp": "Base Mana",
    "mpperlevel": "Mana per Level",
    "movespeed": "Move Speed",
    "armor": "Base Armor",
    "armorperlevel": "Armor per Level",
    "spellblock": "Magic Resist",
    "spellblockperlevel": "MR per Level",
    "attackrange": "Attack Range",
    "hpregen": "HP Regen",
    "hpregenperlevel": "HP Regen per Level",
    "mpregen": "Mana Regen",
    "mpregenperlevel": "Mana Regen per Level",
    "attackdamage": "Base AD",
    "attackdamageperlevel": "AD per Level",
    "attackspeedperlevel": "AS per Level",
    "attackspeed": "Base AS",
    "crit": "Crit Chance",
    "critperlevel": "Crit per Level",
}

def show_champion(query):
    # Handle char-split — rejoin if all single chars
    if len(query) <= 1:
        print(f"Query too short. Type the champion name.")
        return

    query_lower = query.lower()
    vault_path = "C:\\Facecheck\\LeagueVault\\Champions"

    # Exact filename match first, then startswith, then contains
    files = os.listdir(vault_path)
    exact   = [f for f in files if f.lower() == f"{query_lower}.md"]
    starts  = [f for f in files if f.lower().startswith(query_lower)]
    contains = [f for f in files if query_lower in f.lower() and len(query_lower) >= 4]

    matches = exact or starts or contains
    if not matches:
        print(f"No champion found matching '{query}'")
        return

    champ_file = os.path.join(vault_path, matches[0])
    with open(champ_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    name = ""
    title = ""
    tags = ""
    stats = {}

    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            name = line[2:]
        elif line.startswith("**Title:**"):
            title = line.replace("**Title:**", "").strip()
        elif line.startswith("**Tags:**"):
            tags = line.replace("**Tags:**", "").strip()
        elif line.startswith("- **") and ":**" in line:
            # Parse "- **Label:** value" format from enriched vault
            inner = line[4:]
            if ":**" in inner:
                label, val = inner.split(":**", 1)
                stats[label.strip().lower().replace(" ", "")] = val.strip()

    print(f"\n  {'='*45}")
    print(f"  {name} — {title}")
    print(f"  Tags: {tags}")
    print(f"  {'='*45}")
    for key, label in STAT_LABELS.items():
        val = stats.get(key) or stats.get(key.replace("perlevel","perlevel"))
        if val:
            print(f"  {label:<22} {val}")
    print()

def show_components(query):
    if len(query) <= 1:
        print(f"Query too short. Type the full item name.")
        return
    print(f"Fetching item data...")
    items = fetch_items()
    results = find_item(items, query)
    if not results:
        print(f"No items found matching '{query}'")
        return
    item = results[0]
    total = item["priceTotal"]
    print(f"\n{item['name']} — Full Shopping List")
    print(f"{'='*40}")

    def get_all_components(item_id, depth=0):
        item = get_item_by_id(items, item_id)
        if not item:
            return
        if not item["from"]:
            print(f"  {'  '*depth}\u2514\u2500 {item['name']} — {item['price']}g")
        else:
            print(f"  {'  '*depth}\u2514\u2500 {item['name']}")
            for comp_id in item["from"]:
                get_all_components(comp_id, depth+1)

    for comp_id in item["from"]:
        get_all_components(comp_id)
    print(f"\n  Total: {total}g")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python league_build.py item 'item name'       — show build path")
        print("  python league_build.py components 'item name' — show full shopping list")
        print("  python league_build.py champ 'champion name'  — show champion stats")
        sys.exit(1)

    command = sys.argv[1]

    # Rejoin remaining args — handles PowerShell char-split
    raw_args = sys.argv[2:]
    if all(len(a) == 1 for a in raw_args if not a.startswith("--")):
        query = "".join(a for a in raw_args if not a.startswith("--"))
    else:
        query = " ".join(a for a in raw_args if not a.startswith("--"))

    if command == "item":
        show_item(query)
    elif command == "components":
        show_components(query)
    elif command == "champ":
        show_champion(query)
    else:
        print(f"Unknown command: {command}")
