import requests
import sys
import re

# Fix encoding for Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

ITEMS_URL = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/items.json"

def fetch_items():
    """Fetch item data from CommunityDragon."""
    try:
        resp = requests.get(ITEMS_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching item data: {e}")
        sys.exit(1)

def find_item(items, query):
    """Find item by name match."""
    query = query.lower().strip()

    # Exact match first
    exact = [i for i in items if i["name"].lower() == query and i.get("inStore", True)]
    if exact:
        return exact[0]

    # Word-boundary contains for 3+ chars
    if len(query) >= 2:
        contains = [i for i in items if query in i["name"].lower() and i.get("inStore", True)]
        if contains:
            return contains[0]

    return None

def get_item_by_id(items, item_id):
    """Get item dict by ID."""
    for i in items:
        if i["id"] == item_id:
            return i
    return None

def parse_description(description):
    """Parse HTML-like description to extract stats and passives."""
    stats = []
    passives = []
    actives = []

    if not description:
        return stats, passives, actives

    # Extract stats section: <stats>...</stats>
    stats_match = re.search(r'<stats>(.*?)</stats>', description, re.DOTALL | re.IGNORECASE)
    if stats_match:
        stats_text = stats_match.group(1)
        # Parse individual stat lines: <attention>value</attention> Stat Name<br>
        stat_lines = re.findall(r'<attention>(.*?)</attention>\s*([^<]+)', stats_text, re.IGNORECASE)
        for value, name in stat_lines:
            stats.append(f"+{value.strip()} {name.strip().replace('<br>', '').strip()}")
        # Also handle simple text stats
        if not stat_lines:
            clean_stats = re.sub(r'<[^>]+>', '', stats_text).strip()
            if clean_stats:
                for line in clean_stats.split('<br>'):
                    line = line.strip()
                    if line:
                        stats.append(line)

    # Extract passives: <passive>Name</passive><br>Description<br><br>
    passive_matches = re.findall(
        r'<passive>(.*?)</passive>\s*(?:<br>\s*)?(.*?)(?=(?:<passive>|<active>|</mainText>|\Z))',
        description, re.DOTALL | re.IGNORECASE
    )
    for name, desc in passive_matches:
        clean_name = re.sub(r'<[^>]+>', '', name).strip()
        clean_desc = re.sub(r'<[^>]+>', ' ', desc).strip()
        clean_desc = re.sub(r'\s+', ' ', clean_desc)
        if clean_desc:
            passives.append((clean_name, clean_desc))

    # Extract actives: <active>Name</active><br>Description<br><br>
    active_matches = re.findall(
        r'<active>(.*?)</active>\s*(?:<br>\s*)?(.*?)(?=(?:<passive>|<active>|</mainText>|\Z))',
        description, re.DOTALL | re.IGNORECASE
    )
    for name, desc in active_matches:
        clean_name = re.sub(r'<[^>]+>', '', name).strip()
        clean_desc = re.sub(r'<[^>]+>', ' ', desc).strip()
        clean_desc = re.sub(r'\s+', ' ', clean_desc)
        if clean_desc:
            actives.append((clean_name, clean_desc))

    return stats, passives, actives

def print_item_details(items, item):
    """Print full item details with stats and build path."""
    name = item.get("name", "Unknown")
    price_total = item.get("priceTotal", item.get("price", 0))
    price_base = item.get("price", 0)
    categories = item.get("categories", [])
    description = item.get("description", "")
    required_champion = item.get("requiredChampion", "")
    max_stacks = item.get("maxStacks", 1)
    is_enchantment = item.get("isEnchantment", False)

    # Parse description for stats and effects
    stats, passives, actives = parse_description(description)

    # Header
    print(f"\n{'='*60}")
    print(f"  {name}")

    # Cost line
    if price_base < price_total:
        print(f"  Total: {price_total}g | Combine: {price_base}g")
    else:
        print(f"  Cost: {price_total}g")

    print(f"{'='*60}")

    # Categories
    if categories:
        print(f"\n  Type: {', '.join(categories)}")

    # Required champion
    if required_champion:
        print(f"  Champion Locked: {required_champion}")

    # Max stacks (if > 1 or enchantment)
    if max_stacks > 1:
        print(f"  Max Stacks: {max_stacks}")

    if is_enchantment:
        print(f"  Enchantment: Yes")

    # Stats section
    if stats:
        print(f"\n  Stats:")
        for stat in stats:
            print(f"    {stat}")

    # Actives section
    if actives:
        print(f"\n  Active Effects:")
        for name, desc in actives:
            if name and desc:
                print(f"    [{name}]: {desc}")
            elif desc:
                print(f"    {desc}")

    # Passives section
    if passives:
        print(f"\n  Passive Effects:")
        for name, desc in passives:
            if name and desc:
                print(f"    [{name}]: {desc}")
            elif desc:
                print(f"    {desc}")

    # Build path
    builds_from = item.get("from", [])
    builds_into = item.get("to", [])

    if builds_from:
        print(f"\n  Builds From:")
        for comp_id in builds_from:
            comp = get_item_by_id(items, comp_id)
            if comp:
                comp_name = comp.get("name", "Unknown")
                comp_price = comp.get("priceTotal", comp.get("price", 0))
                print(f"    - {comp_name} ({comp_price}g)")

                # Show sub-components (one level deep)
                sub_from = comp.get("from", [])
                if sub_from:
                    for sub_id in sub_from:
                        sub = get_item_by_id(items, sub_id)
                        if sub:
                            sub_name = sub.get("name", "Unknown")
                            sub_price = sub.get("priceTotal", sub.get("price", 0))
                            print(f"      -> {sub_name} ({sub_price}g)")

    if builds_into:
        print(f"\n  Builds Into:")
        for upgrade_id in builds_into:
            upgrade = get_item_by_id(items, upgrade_id)
            if upgrade:
                up_name = upgrade.get("name", "Unknown")
                up_price = upgrade.get("priceTotal", upgrade.get("price", 0))
                print(f"    - {up_name} ({up_price}g)")

    print(f"{'='*60}\n")

def show_item(query):
    """Main entry: fetch and display item."""
    if not query or len(query) < 2:
        print("Usage: face item 'item name'")
        print("Example: face item collector")
        return

    items = fetch_items()
    item = find_item(items, query)

    if not item:
        print(f"No item found matching '{query}'")
        print("Try the full name or a longer partial match.")
        return

    print_item_details(items, item)

def show_components(query):
    """Show full component tree with gold breakdown."""
    if not query or len(query) < 2:
        print("Usage: face components 'item name'")
        return

    items = fetch_items()
    item = find_item(items, query)

    if not item:
        print(f"No item found matching '{query}'")
        return

    name = item.get("name", "Unknown")
    total = item.get("priceTotal", item.get("price", 0))
    builds_from = item.get("from", [])

    print(f"\n{name} — Full Component Tree")
    print(f"Total Cost: {total}g")
    print(f"{'='*50}")

    if not builds_from:
        print("  Base item (no components)")
    else:
        total_component_cost = 0

        def print_component_tree(item_id, depth=0, is_last=True):
            nonlocal total_component_cost
            component = get_item_by_id(items, item_id)
            if not component:
                return

            indent = "  " * depth
            prefix = "-> "
            comp_name = component.get("name", "Unknown")
            comp_price = component.get("price", component.get("priceTotal", 0))

            # Base components have no "from"
            sub_from = component.get("from", [])

            if not sub_from:
                total_component_cost += comp_price
                print(f"{indent}{prefix}{comp_name} — {comp_price}g")
            else:
                print(f"{indent}{prefix}{comp_name}")
                for i, sub_id in enumerate(sub_from):
                    print_component_tree(sub_id, depth + 1, i == len(sub_from) - 1)

        for i, comp_id in enumerate(builds_from):
            print_component_tree(comp_id, 0, i == len(builds_from) - 1)

        combine_cost = item.get("price", total)
        print(f"\n  Component Cost: {total_component_cost}g")
        print(f"  Combine Cost:   {combine_cost}g")
        print(f"  Total:          {total}g")

    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("FaceCheck Item Lookup")
        print("="*30)
        print("Usage:")
        print("  python facecheck_item.py 'item name'")
        print("  python facecheck_item.py components 'item name'")
        print()
        print("Examples:")
        print("  face item collector")
        print("  face item 'trinity force'")
        print("  face components collector")
        sys.exit(0)

    # Handle char-split from PowerShell ("collector" -> ["c", "o", "l", ...])
    raw_args = sys.argv[1:]
    if len(raw_args) > 1 and all(len(a) == 1 for a in raw_args):
        query = "".join(raw_args)
    elif raw_args[0].lower() == "components" and len(raw_args) > 1:
        # Handle: components item_name
        query_parts = raw_args[1:]
        if all(len(a) == 1 for a in query_parts):
            query = "".join(query_parts)
        else:
            query = " ".join(query_parts)
        show_components(query)
        sys.exit(0)
    elif raw_args[0].lower() == "components":
        print("Usage: face components 'item name'")
        sys.exit(1)
    else:
        query = " ".join(raw_args)

    show_item(query)
