import requests
import json
import os
import re
import time
import sys

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

from verdict_paths import VAULT_ROOT as VAULT

STYLE_ARCHETYPES = {
    1:  "Hypercarry Skirmisher",
    2:  "Scaling Carry",
    3:  "Scaling Fighter / Marksman",
    4:  "Gank Heavy Fighter",
    5:  "Hybrid / Early Pressure",
    6:  "Early Skirmisher / Bruiser",
    7:  "Engage Assassin / Diver",
    8:  "Teamfight Controller",
    9:  "CC Heavy Engage",
    10: "Mage / Poke",
}

DAMAGE_LABELS = {
    "kPhysical": "Physical",
    "kMagic":    "Magic",
    "kMixed":    "Mixed",
    "kTrue":     "True",
}

RATING_LABELS = {
    1: "Low",
    2: "Medium",
    3: "High",
}

# ─────────────────────────────────────────────
# RATE LIMITER
# Data Dragon: no official rate limit — safe at 0.2s between calls
# Community Dragon: CDN-served — safe at 0.1s between calls
# ─────────────────────────────────────────────

_last_call = 0

def rate_limited_get(url, delay=0.2, retries=3):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_call = time.time()

    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r
            elif r.status_code == 429:
                wait = 2 ** attempt
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    HTTP {r.status_code} for {url}")
                return None
        except requests.exceptions.Timeout:
            print(f"    Timeout on attempt {attempt + 1} for {url}")
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            print(f"    Request error: {e}")
            time.sleep(1)
    return None

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def clean_name(raw):
    name = re.sub(r'<[^>]+>', ' ', raw)
    name = re.sub(r'-?\s*rarity\w*\s*-?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'-?\s*subtitle\w*\s*-?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\d+\s*Silver\s*Serpents', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-').strip()

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def rating_bar(value, max_val=3):
    """Visual bar for 1-3 ratings."""
    if value is None:
        return "N/A"
    filled = int(value)
    empty = max_val - filled
    return "█" * filled + "░" * empty + f"  {RATING_LABELS.get(value, str(value))}"

def is_doom_bot(name):
    return name.lower().startswith("doom bot") or name.lower().startswith("doom_bot")

# ─────────────────────────────────────────────
# DATA SOURCES
# ─────────────────────────────────────────────

def get_version():
    r = rate_limited_get("https://ddragon.leagueoflegends.com/api/versions.json")
    if r:
        return r.json()[0]
    raise RuntimeError("Could not fetch patch version from Data Dragon.")

def get_dd_champion_list(version):
    """Data Dragon champion list — names, IDs, tags, base stats."""
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    r = rate_limited_get(url)
    if r:
        return r.json()["data"]
    raise RuntimeError("Could not fetch champion list from Data Dragon.")

def get_dd_champion_detail(version, champ_id):
    """Data Dragon individual champion file — full stats, spells, passive."""
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{champ_id}.json"
    r = rate_limited_get(url, delay=0.15)
    if r:
        data = r.json()["data"]
        # Key is the champion ID
        return list(data.values())[0]
    return None

def get_cd_champion_summary():
    """Community Dragon champion summary — IDs, roles, internal names."""
    url = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json"
    r = rate_limited_get(url)
    if r:
        return r.json()
    raise RuntimeError("Could not fetch champion summary from Community Dragon.")

def get_cd_champion_detail(champ_id):
    """Community Dragon champion detail — tacticalInfo, playstyleInfo, shortBio."""
    url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/{champ_id}.json"
    r = rate_limited_get(url, delay=0.1)
    if r:
        return r.json()
    return None

def get_dd_items(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
    r = rate_limited_get(url)
    if r:
        return r.json()["data"]
    raise RuntimeError("Could not fetch items.")

def get_dd_runes(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/runesReforged.json"
    r = rate_limited_get(url)
    if r:
        return r.json()
    raise RuntimeError("Could not fetch runes.")

def get_dd_summoner_spells(version):
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/summoner.json"
    r = rate_limited_get(url)
    if r:
        return r.json()["data"]
    raise RuntimeError("Could not fetch summoner spells.")

# ─────────────────────────────────────────────
# CHAMPION FILE BUILDER
# ─────────────────────────────────────────────

def build_champion_file(dd_basic, dd_detail, cd_summary_entry, cd_detail):
    """
    Merge all data sources into one comprehensive champion markdown file.
    dd_basic:           Data Dragon champion list entry (tags, basic stats)
    dd_detail:          Data Dragon individual champion (full stats, spells, passive)
    cd_summary_entry:   Community Dragon summary entry (id, roles)
    cd_detail:          Community Dragon detail (tacticalInfo, playstyleInfo, shortBio)
    """
    name = dd_basic.get("name", "Unknown")
    title = dd_basic.get("title", "")
    tags = dd_basic.get("tags", [])
    stats = dd_detail.get("stats", dd_basic.get("stats", {})) if dd_detail else dd_basic.get("stats", {})
    spells = dd_detail.get("spells", []) if dd_detail else []
    passive = dd_detail.get("passive", {}) if dd_detail else {}
    lore = dd_detail.get("lore", "") if dd_detail else ""

    # Community Dragon data
    roles = cd_summary_entry.get("roles", []) if cd_summary_entry else []
    tactical = cd_detail.get("tacticalInfo", {}) if cd_detail else {}
    playstyle = cd_detail.get("playstyleInfo", {}) if cd_detail else {}
    short_bio = cd_detail.get("shortBio", "") if cd_detail else ""

    style_num = tactical.get("style")
    difficulty = tactical.get("difficulty")
    damage_type = tactical.get("damageType", "")
    attack_type = tactical.get("attackType", "")

    archetype = STYLE_ARCHETYPES.get(style_num, "Unknown")
    damage_label = DAMAGE_LABELS.get(damage_type, damage_type)

    lines = []

    # ── HEADER ────────────────────────────────────────────────────
    lines.append(f"# {name}")
    lines.append(f"")
    lines.append(f"**Title:** {title.title()}")
    lines.append(f"**Tags:** {', '.join(tags)}")
    lines.append(f"**Roles:** {', '.join(r.capitalize() for r in roles)}")
    lines.append(f"")

    # ── CHAMPION IDENTITY ─────────────────────────────────────────
    lines.append(f"## Champion Identity")
    lines.append(f"")
    if style_num:
        lines.append(f"**Archetype:** {archetype}  (Style {style_num})")
    lines.append(f"**Damage Type:** {damage_label}")
    lines.append(f"**Attack Type:** {attack_type.capitalize() if attack_type else 'N/A'}")
    if difficulty:
        diff_map = {1: "Low", 2: "Medium", 3: "High"}
        lines.append(f"**Difficulty:** {diff_map.get(difficulty, str(difficulty))}")
    lines.append(f"")

    # ── PLAYSTYLE RATINGS ─────────────────────────────────────────
    if playstyle:
        lines.append(f"## Playstyle Ratings")
        lines.append(f"")
        for key, label in [
            ("damage",       "Damage"),
            ("durability",   "Durability"),
            ("crowdControl", "Crowd Control"),
            ("mobility",     "Mobility"),
            ("utility",      "Utility"),
        ]:
            val = playstyle.get(key)
            if val is not None:
                lines.append(f"**{label}:** {rating_bar(val)}")
        lines.append(f"")

    # ── BASE STATS ────────────────────────────────────────────────
    lines.append(f"## Base Stats")
    lines.append(f"")
    stat_map = [
        ("hp",                  "HP"),
        ("hpperlevel",          "HP per Level"),
        ("mp",                  "Mana"),
        ("mpperlevel",          "Mana per Level"),
        ("movespeed",           "Move Speed"),
        ("armor",               "Armor"),
        ("armorperlevel",       "Armor per Level"),
        ("spellblock",          "Magic Resist"),
        ("spellblockperlevel",  "MR per Level"),
        ("attackrange",         "Attack Range"),
        ("attackdamage",        "Base AD"),
        ("attackdamageperlevel","AD per Level"),
        ("attackspeed",         "Attack Speed"),
        ("attackspeedperlevel", "AS per Level"),
        ("hpregen",             "HP Regen"),
        ("hpregenperlevel",     "HP Regen per Level"),
    ]
    for key, label in stat_map:
        val = stats.get(key)
        if val is not None:
            lines.append(f"- **{label}:** {val}")
    lines.append(f"")

    # ── PASSIVE ───────────────────────────────────────────────────
    if passive:
        lines.append(f"## Passive — {passive.get('name', 'Passive')}")
        lines.append(f"")
        desc = clean_html(passive.get("description", ""))
        if desc:
            lines.append(desc)
        lines.append(f"")

    # ── ABILITIES ─────────────────────────────────────────────────
    if spells:
        lines.append(f"## Abilities")
        lines.append(f"")
        spell_labels = ["Q", "W", "E", "R"]
        for i, spell in enumerate(spells):
            label = spell_labels[i] if i < len(spell_labels) else f"Spell {i+1}"
            spell_name = spell.get("name", f"Spell {i+1}")
            lines.append(f"### {label} — {spell_name}")
            lines.append(f"")
            desc = clean_html(spell.get("description", ""))
            if desc:
                lines.append(desc)
            lines.append(f"")
            cooldown = spell.get("cooldownBurn", "")
            cost = spell.get("costBurn", "")
            rng = spell.get("rangeBurn", "")
            meta = []
            if cooldown and cooldown != "0":
                meta.append(f"**Cooldown:** {cooldown}s")
            if cost and cost != "0":
                meta.append(f"**Cost:** {cost}")
            if rng and rng != "0":
                meta.append(f"**Range:** {rng}")
            if meta:
                lines.append("  ".join(meta))
                lines.append(f"")

    # ── LORE ──────────────────────────────────────────────────────
    bio = short_bio if short_bio else lore
    if bio:
        lines.append(f"## Lore")
        lines.append(f"")
        lines.append(clean_html(bio))
        lines.append(f"")

    return "\n".join(lines)

# ─────────────────────────────────────────────
# INDIVIDUAL SECTION SAVERS
# ─────────────────────────────────────────────

def save_items(version):
    print("  Fetching items...")
    items = get_dd_items(version)
    saved = skipped = 0
    for item_id, item in items.items():
        name = clean_name(item["name"])
        if not name:
            skipped += 1
            continue
        content = f"# {item['name']}\n\n"
        content += f"**Cost:** {item.get('gold', {}).get('total', 'N/A')} gold\n\n"
        content += f"**Description:** {item.get('plaintext', 'N/A')}\n\n"
        if item.get("stats"):
            content += "**Stats:**\n"
            for stat, value in item["stats"].items():
                content += f"- {stat}: {value}\n"
        content += f"\n**Tags:** {', '.join(item.get('tags', []))}\n"
        path = os.path.join(VAULT, "Items", f"{name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        saved += 1
    print(f"  Items: {saved} saved, {skipped} skipped.")

def save_runes(version):
    print("  Fetching runes...")
    data = get_dd_runes(version)
    for tree in data:
        tree_name = clean_name(tree["name"])
        if not tree_name:
            continue
        content = f"# {tree['name']}\n\n"
        for slot in tree.get("slots", []):
            for rune in slot.get("runes", []):
                content += f"## {rune['name']}\n\n"
                desc = re.sub(r'<[^>]+>', '', rune.get('longDesc', rune.get('shortDesc', '')))
                content += f"{desc}\n\n"
        path = os.path.join(VAULT, "Runes", f"{tree_name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"  Runes: {len(data)} trees saved.")

def save_summoner_spells(version):
    print("  Fetching summoner spells...")
    spells = get_dd_summoner_spells(version)
    saved = 0
    for spell_id, spell in spells.items():
        name = clean_name(spell["name"])
        if not name:
            continue
        content = f"# {spell['name']}\n\n"
        desc = re.sub(r'<[^>]+>', '', spell.get('description', ''))
        content += f"**Description:** {desc}\n\n"
        content += f"**Cooldown:** {spell.get('cooldown', ['N/A'])[0]} seconds\n"
        path = os.path.join(VAULT, "SummonerSpells", f"{name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        saved += 1
    print(f"  Summoner spells: {saved} saved.")

def save_champions(version):
    print("  Fetching Data Dragon champion list...")
    dd_list = get_dd_champion_list(version)

    print("  Fetching Community Dragon champion summary...")
    cd_summary = get_cd_champion_summary()

    # Build CD lookup: display_name -> summary entry
    # Also need: display_name -> CD numeric ID for detail calls
    cd_by_name = {}
    cd_by_alias = {}
    for entry in cd_summary:
        cname = entry.get("name", "")
        calias = entry.get("alias", "")
        if cname:
            cd_by_name[cname.lower()] = entry
        if calias:
            cd_by_alias[calias.lower()] = entry

    total = len(dd_list)
    saved = errors = 0

    print(f"  Fetching full data for {total} champions...")

    for i, (champ_id, dd_basic) in enumerate(sorted(dd_list.items()), 1):
        champ_name = dd_basic.get("name", champ_id)

        # Skip Doom Bot entries
        if is_doom_bot(champ_name):
            continue

        sys.stdout.write(f"\r  [{i}/{total}] {champ_name:<30}")
        sys.stdout.flush()

        # Data Dragon detail (spells, passive, full stats, lore)
        dd_detail = get_dd_champion_detail(version, champ_id)

        # Community Dragon match — try name first, then alias (internal ID like "MonkeyKing")
        cd_entry = (
            cd_by_name.get(champ_name.lower()) or
            cd_by_alias.get(champ_id.lower()) or
            cd_by_name.get(champ_id.lower())
        )

        # Community Dragon detail (tacticalInfo, playstyleInfo)
        cd_detail = None
        if cd_entry:
            cd_id = cd_entry.get("id")
            if cd_id and cd_id > 0:
                cd_detail = get_cd_champion_detail(cd_id)

        # Build the file
        try:
            content = build_champion_file(dd_basic, dd_detail, cd_entry, cd_detail)
            file_name = clean_name(champ_name) + ".md"
            path = os.path.join(VAULT, "Champions", file_name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            saved += 1
        except Exception as e:
            print(f"\n  Error building {champ_name}: {e}")
            errors += 1

    print(f"\n  Champions: {saved} saved, {errors} errors.")

# ─────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────

def cleanup_bad_files():
    for folder in ["Items", "Champions", "Runes", "SummonerSpells"]:
        path = os.path.join(VAULT, folder)
        if not os.path.exists(path):
            continue
        removed = 0
        for f in os.listdir(path):
            if (f.startswith("-rarity") or f == ".md" or
                f.startswith(".") or f.startswith("Doom Bot")):
                try:
                    os.remove(os.path.join(path, f))
                    removed += 1
                except:
                    pass
        if removed:
            print(f"  Cleaned {removed} bad files from {folder}/")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("  League Vault Update")
    print("="*60)

    # Ensure directories exist
    for folder in ["Champions", "Items", "Runes", "SummonerSpells", "PatchNotes"]:
        os.makedirs(os.path.join(VAULT, folder), exist_ok=True)

    print("\nCleaning up stale files...")
    cleanup_bad_files()

    print("\nFetching current patch version...")
    version = get_version()
    print(f"  Patch: {version}")

    print("\nUpdating champions (enriched with ability data)...")
    save_champions(version)

    print("\nUpdating items...")
    save_items(version)

    print("\nUpdating runes...")
    save_runes(version)

    print("\nUpdating summoner spells...")
    save_summoner_spells(version)

    print(f"\n{'='*60}")
    print(f"  Vault updated to patch {version}")
    print(f"{'='*60}")
