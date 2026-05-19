"""
Verdict Champion Intelligence Layer
Reads LeagueVault champion files and provides structured intel
for matchup context, threat signals, and counter recommendations.
"""

import sys
import os
import re
import json
from collections import defaultdict

from verdict_game_model import Game

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

from verdict_paths import VAULT_PATH

CHAMPION_ALIASES = {
    "MonkeyKing":  "Wukong",
    "FiddleSticks": "Fiddlesticks",
    "DrMundo":     "Dr. Mundo",
    "JarvanIV":    "Jarvan IV",
    "AurelionSol": "Aurelion Sol",
    "TwistedFate": "Twisted Fate",
    "XinZhao":     "Xin Zhao",
    "MissFortune": "Miss Fortune",
    "RekSai":      "Rek'Sai",
    "Belveth":     "Bel'Veth",
    "Kogmaw":      "Kog'Maw",
    "KSante":      "K'Sante",
    "Chogath":     "Cho'Gath",
    "KhaZix":      "Kha'Zix",
    "LeeSin":      "Lee Sin",
    "MasterYi":    "Master Yi",
    "TahmKench":   "Tahm Kench",
    "NunuWillump": "Nunu & Willump",
    "RenataGlasc": "Renata Glasc",
}

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

# Archetypes that are inherently early-game threats in the jungle
EARLY_THREAT_ARCHETYPES = {4, 5, 6, 7}

# Archetypes that scale and are less threatening early
SCALING_ARCHETYPES = {1, 2, 3}

# Archetypes that are primarily teamfight/objective
TEAMFIGHT_ARCHETYPES = {8, 9, 10}

# CC keywords in ability descriptions that indicate hard CC
HARD_CC_KEYWORDS = [
    "suppresses", "suppression", "stuns", "stun", "knocks up", "knock up",
    "knockup", "airborne", "pulls", "displaces", "displacement",
    "immobilizes", "immobilize", "root", "roots", "fears", "fear",
    "charm", "charms", "taunts", "taunt", "sleep", "sleeps",
]

SOFT_CC_KEYWORDS = [
    "slows", "slow", "blinds", "blind", "silences", "silence",
    "grounds", "ground", "disarms", "disarm", "reduces move speed",
]

HEAL_KEYWORDS = [
    "heal", "heals", "healing", "restores health", "gains health",
    "life steal", "omnivamp",
]

INVADE_KEYWORDS = [
    "gains move speed", "movement speed", "dashes", "dash", "leaps",
    "leap", "charges", "charge", "lunges", "lunge", "blinks",
]

# ─────────────────────────────────────────────
# VAULT PARSER
# ─────────────────────────────────────────────

def parse_vault_file(file_path):
    """
    Parse a champion vault markdown file into a structured dict.
    Returns None if file cannot be parsed.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    data = {
        "name": "",
        "title": "",
        "tags": [],
        "roles": [],
        "archetype": "",
        "style_num": None,
        "damage_type": "",
        "attack_type": "",
        "difficulty": "",
        "ratings": {},
        "stats": {},
        "passive": {"name": "", "description": ""},
        "abilities": [],
        "lore": "",
        "raw": content,
    }

    lines = content.split("\n")

    # Name from first line
    for line in lines:
        if line.startswith("# "):
            data["name"] = line[2:].strip()
            break

    # Title
    m = re.search(r'\*\*Title:\*\*\s*(.+)', content)
    if m:
        data["title"] = m.group(1).strip()

    # Tags
    m = re.search(r'\*\*Tags:\*\*\s*(.+)', content)
    if m:
        data["tags"] = [t.strip() for t in m.group(1).split(",")]

    # Roles
    m = re.search(r'\*\*Roles:\*\*\s*(.+)', content)
    if m:
        data["roles"] = [r.strip().lower() for r in m.group(1).split(",")]

    # Archetype and style number
    m = re.search(r'\*\*Archetype:\*\*\s*(.+?)\s*\(Style (\d+)\)', content)
    if m:
        data["archetype"] = m.group(1).strip()
        data["style_num"] = int(m.group(2))

    # Damage type
    m = re.search(r'\*\*Damage Type:\*\*\s*(.+)', content)
    if m:
        data["damage_type"] = m.group(1).strip()

    # Attack type
    m = re.search(r'\*\*Attack Type:\*\*\s*(.+)', content)
    if m:
        data["attack_type"] = m.group(1).strip().lower()

    # Difficulty
    m = re.search(r'\*\*Difficulty:\*\*\s*(.+)', content)
    if m:
        data["difficulty"] = m.group(1).strip()

    # Playstyle ratings
    for key, label in [
        ("damage",       "Damage"),
        ("durability",   "Durability"),
        ("cc",           "Crowd Control"),
        ("mobility",     "Mobility"),
        ("utility",      "Utility"),
    ]:
        m = re.search(rf'\*\*{label}:\*\*\s*(█+)(░*)', content)
        if m:
            filled = len(m.group(1))
            data["ratings"][key] = filled

    # Base stats
    stat_patterns = {
        "hp":         r'\*\*HP:\*\*\s*([\d.]+)',
        "move_speed": r'\*\*Move Speed:\*\*\s*([\d.]+)',
        "attack_range": r'\*\*Attack Range:\*\*\s*([\d.]+)',
        "base_ad":    r'\*\*Base AD:\*\*\s*([\d.]+)',
        "armor":      r'\*\*Armor:\*\*\s*([\d.]+)',
    }
    for key, pattern in stat_patterns.items():
        m = re.search(pattern, content)
        if m:
            try:
                data["stats"][key] = float(m.group(1))
            except ValueError:
                pass

    # Passive
    m = re.search(r'## Passive — (.+?)\n\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
    if m:
        data["passive"]["name"] = m.group(1).strip()
        data["passive"]["description"] = m.group(2).strip()

    # Abilities (Q, W, E, R)
    ability_pattern = re.compile(
        r'### ([QWER]) — (.+?)\n\n(.*?)(?=\n###|\n## |\Z)',
        re.DOTALL
    )
    for match in ability_pattern.finditer(content):
        slot = match.group(1)
        name = match.group(2).strip()
        body = match.group(3).strip()

        # Extract description (first paragraph before the stat line)
        parts = body.split("\n\n")
        description = parts[0].strip() if parts else ""

        # Extract cooldown and range
        cooldown = ""
        ability_range = ""
        cd_m = re.search(r'\*\*Cooldown:\*\*\s*([^\s*]+)', body)
        if cd_m:
            cooldown = cd_m.group(1).replace("s", "")
        range_m = re.search(r'\*\*Range:\*\*\s*([^\s*\n]+)', body)
        if range_m:
            ability_range = range_m.group(1)

        data["abilities"].append({
            "slot": slot,
            "name": name,
            "description": description,
            "cooldown": cooldown,
            "range": ability_range,
        })

    # Lore
    m = re.search(r'## Lore\n\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
    if m:
        data["lore"] = m.group(1).strip()

    return data

# ─────────────────────────────────────────────
# SIGNAL DERIVATION
# ─────────────────────────────────────────────

def derive_signals(champ_data):
    """
    Derive threat signals and behavioral patterns from parsed champion data.
    Returns a signals dict used for matchup context and counter reasoning.
    """
    signals = {
        "hard_cc": [],           # List of CC types found
        "soft_cc": [],
        "has_suppression": False,
        "has_healing": False,
        "has_invade_tool": False,
        "resourceless": False,
        "ranged": False,
        "early_threat": False,
        "scaling_threat": False,
        "teamfight_threat": False,
        "invade_threat_level": "LOW",
        "threat_window": "",
        "key_mechanic": "",
        "jungle_path_risk": "",
        "anti_healing_sensitive": False,
    }

    style = champ_data.get("style_num")
    ratings = champ_data.get("ratings", {})
    stats = champ_data.get("stats", {})
    attack_type = champ_data.get("attack_type", "")
    damage_type = champ_data.get("damage_type", "")

    # Ranged check
    attack_range = stats.get("attack_range", 0)
    if attack_range > 300 or attack_type == "ranged":
        signals["ranged"] = True

    # Resourceless check (mana shown as 10000 in vault = no resource)
    # We check roles/tags instead since mana not in parsed stats above
    passive_desc = champ_data.get("passive", {}).get("description", "").lower()
    name_lower = champ_data.get("name", "").lower()
    # Known resourceless junglers
    resourceless_champs = {"viego", "garen", "katarina", "riven", "nidalee",
                           "renekton", "rengar", "aatrox", "gwen"}
    if name_lower in resourceless_champs:
        signals["resourceless"] = True

    # Early/scaling/teamfight threat from style
    if style in EARLY_THREAT_ARCHETYPES:
        signals["early_threat"] = True
        signals["threat_window"] = "Levels 2-6 and first item"
    elif style in SCALING_ARCHETYPES:
        signals["scaling_threat"] = True
        signals["threat_window"] = "Post second item (20+ minutes)"
    elif style in TEAMFIGHT_ARCHETYPES:
        signals["teamfight_threat"] = True
        signals["threat_window"] = "Mid-game teamfights and objectives"

    # Invade threat level from mobility rating + early threat
    mobility = ratings.get("mobility", 1)
    if signals["early_threat"] and mobility >= 2:
        signals["invade_threat_level"] = "HIGH"
        signals["jungle_path_risk"] = "second_buff"
    elif signals["early_threat"] and mobility == 1:
        signals["invade_threat_level"] = "MEDIUM"
        signals["jungle_path_risk"] = "river_ward"
    elif signals["scaling_threat"]:
        signals["invade_threat_level"] = "LOW"
        signals["jungle_path_risk"] = "none"
    else:
        signals["invade_threat_level"] = "MEDIUM"
        signals["jungle_path_risk"] = "dragon_river"

    # Scan all ability text for CC, healing, invade tools
    all_ability_text = " ".join([
        champ_data.get("passive", {}).get("description", ""),
        *[a.get("description", "") for a in champ_data.get("abilities", [])]
    ]).lower()

    for keyword in HARD_CC_KEYWORDS:
        if keyword in all_ability_text and keyword not in signals["hard_cc"]:
            signals["hard_cc"].append(keyword)

    for keyword in SOFT_CC_KEYWORDS:
        if keyword in all_ability_text and keyword not in signals["soft_cc"]:
            signals["soft_cc"].append(keyword)

    if "suppress" in all_ability_text:
        signals["has_suppression"] = True

    for keyword in HEAL_KEYWORDS:
        if keyword in all_ability_text:
            signals["has_healing"] = True
            break

    if signals["has_healing"]:
        signals["anti_healing_sensitive"] = True

    for keyword in INVADE_KEYWORDS:
        if keyword in all_ability_text:
            signals["has_invade_tool"] = True
            break

    # Key mechanic — most important thing about this champion in one sentence
    name = champ_data.get("name", "")
    archetype = champ_data.get("archetype", "")
    r_ability = next((a for a in champ_data.get("abilities", []) if a["slot"] == "R"), None)
    r_desc = r_ability.get("description", "").lower() if r_ability else ""

    if signals["has_suppression"]:
        signals["key_mechanic"] = f"{name}'s ultimate suppresses — flash cannot escape it once it lands."
    elif "execute" in all_ability_text or "kills instantly" in all_ability_text:
        signals["key_mechanic"] = f"{name} has an execute — they become more dangerous as targets get low."
    elif "control the dead" in all_ability_text or "possess" in all_ability_text or "seizes control" in all_ability_text:
        signals["key_mechanic"] = f"{name} can possess dead enemies and inherit their kit — resets are their win condition."
    elif signals["has_healing"] and ratings.get("durability", 1) >= 2:
        signals["key_mechanic"] = f"{name} has built-in sustain — anti-healing reduces their effectiveness significantly."
    elif "invisible" in all_ability_text or "camouflage" in all_ability_text or "stealth" in all_ability_text:
        signals["key_mechanic"] = f"{name} uses stealth as a core mechanic — pink wards and control wards deny their approach."
    elif "clone" in all_ability_text:
        signals["key_mechanic"] = f"{name} creates clones to deceive — targeting the real one is the challenge."
    elif mobility >= 3 and signals["early_threat"]:
        signals["key_mechanic"] = f"{name} is extremely mobile early — they will be in your jungle before you expect it."
    elif style in SCALING_ARCHETYPES:
        signals["key_mechanic"] = f"{name} is a scaling champion — they are manageable early but become a serious threat post-items."
    else:
        signals["key_mechanic"] = f"{name} is a {archetype.lower()} — their strength window is {signals['threat_window'].lower()}."

    return signals

# ─────────────────────────────────────────────
# CHAMPION INTEL DATABASE
# ─────────────────────────────────────────────

_intel_cache = {}

def load_champion_intel(champion_name):
    """
    Load and parse champion intel from vault.
    Cached in memory after first load.
    Returns None if champion not found.
    """
    resolved = CHAMPION_ALIASES.get(champion_name, champion_name)
    cache_key = champion_name
    if cache_key in _intel_cache:
        return _intel_cache[cache_key]
    champion_name = resolved

    file_path = os.path.join(VAULT_PATH, f"{champion_name}.md")
    if not os.path.exists(file_path):
        # Try case-insensitive search
        try:
            files = os.listdir(VAULT_PATH)
            match = next(
                (f for f in files if f.lower() == f"{champion_name.lower()}.md"),
                None
            )
            if match:
                file_path = os.path.join(VAULT_PATH, match)
            else:
                return None
        except Exception:
            return None

    data = parse_vault_file(file_path)
    if not data:
        return None

    data["signals"] = derive_signals(data)
    _intel_cache[cache_key] = data
    _intel_cache[champion_name] = data
    return data

def load_all_intel():
    """Load intel for all champions in the vault."""
    if len(_intel_cache) > 100:
        return _intel_cache

    try:
        files = os.listdir(VAULT_PATH)
        for f in files:
            if f.endswith(".md"):
                champ_name = f[:-3]  # strip .md
                load_champion_intel(champ_name)
    except Exception as e:
        print(f"Warning: Could not load all champion intel: {e}")

    return _intel_cache

# ─────────────────────────────────────────────
# MATCHUP CONTEXT GENERATOR
# ─────────────────────────────────────────────

def get_matchup_context(my_champion, enemy_champion, game_data=None):
    """
    Generate matchup context between your champion and the enemy.
    Returns a structured context dict for use in output formatting.
    """
    my_intel = load_champion_intel(my_champion)
    enemy_intel = load_champion_intel(enemy_champion)

    context = {
        "my_champion": my_champion,
        "enemy_champion": enemy_champion,
        "my_intel": my_intel,
        "enemy_intel": enemy_intel,
        "threat_assessment": "",
        "threat_window": "",
        "key_mechanic": "",
        "invade_risk": "",
        "your_win_condition": "",
        "notes": [],
        "confidence": "programmatic",
    }

    if not enemy_intel:
        context["threat_assessment"] = f"No intel profile found for {enemy_champion}."
        # Pick order context
    if game_data:
        my_pick = game_data.pick_order
        en_pick = game_data.enemy_pick_order
        if my_pick and en_pick:
            if en_pick < my_pick:
                context["pick_context"] = f"{enemy_champion} was picked before you (pick {en_pick} vs your pick {my_pick}). You had information and chose this matchup."
            elif my_pick < en_pick:
                context["pick_context"] = f"You picked first (pick {my_pick} vs their pick {en_pick}). This was a blind pick."
            else:
                context["pick_context"] = "Simultaneous pick. No draft advantage either way."
        else:
            context["pick_context"] = ""
    else:
        context["pick_context"] = ""

    if not enemy_intel:
        return context

    signals = enemy_intel.get("signals", {})
    enemy_style = enemy_intel.get("style_num")
    enemy_ratings = enemy_intel.get("ratings", {})
    enemy_archetype = enemy_intel.get("archetype", "")

    # Threat window
    context["threat_window"] = signals.get("threat_window", "Unknown")
    context["key_mechanic"] = signals.get("key_mechanic", "")
    invade_level = signals.get("invade_threat_level", "LOW")
    jungle_risk = signals.get("jungle_path_risk", "")

    # Invade risk assessment
    if invade_level == "HIGH":
        risk_map = {
            "second_buff": f"{enemy_champion} is a HIGH invasion threat. They will path to your second buff at level 2. Ward the entrance before your first clear completes.",
            "river_ward": f"{enemy_champion} is a HIGH invasion threat. Ward river entrances before committing to camps.",
            "dragon_river": f"{enemy_champion} is a HIGH threat near dragon side. Ward river at 3:30.",
        }
        context["invade_risk"] = risk_map.get(jungle_risk, f"{enemy_champion} is a HIGH early invasion threat.")
    elif invade_level == "MEDIUM":
        context["invade_risk"] = f"{enemy_champion} has moderate early pressure. Standard ward coverage is sufficient."
    else:
        context["invade_risk"] = f"{enemy_champion} is not a significant early invasion threat. Focus on farm."

    # Your win condition based on matchup archetype vs archetype
    my_style = my_intel.get("style_num") if my_intel else None
    my_signals = my_intel.get("signals", {}) if my_intel else {}

    if enemy_style in SCALING_ARCHETYPES and my_style in EARLY_THREAT_ARCHETYPES:
        context["your_win_condition"] = f"You have the early game advantage. {enemy_champion} is a scaling champion — pressure them before their items come online. Do not let this go late."
    elif enemy_style in EARLY_THREAT_ARCHETYPES and my_style in SCALING_ARCHETYPES:
        context["your_win_condition"] = f"{enemy_champion} is stronger early. Survive the first 15 minutes, avoid their threat window, and take over when your items hit."
    elif enemy_style in TEAMFIGHT_ARCHETYPES:
        context["your_win_condition"] = f"{enemy_champion} is a teamfight champion. Win through farm and individual duels — avoid fighting on their terms in grouped settings."
    else:
        context["your_win_condition"] = f"Even archetype matchup. Farm, vision, and execution determine the outcome."

    # Notable signals to surface
    if signals.get("has_suppression"):
        context["notes"].append(f"SUPPRESSION on {enemy_champion}'s R — flash cannot escape it once the cast starts. Do not flash reactively.")
    if signals.get("has_healing") and signals.get("anti_healing_sensitive"):
        context["notes"].append(f"{enemy_champion} has built-in healing. Grievous Wounds reduces their sustain by 40%. Time your anti-healing purchase.")
    if signals.get("has_invade_tool") and invade_level in ("HIGH", "MEDIUM"):
        context["notes"].append(f"{enemy_champion} has mobility tools designed for early aggression. Treat uncleared wards as an active threat.")
    if enemy_ratings.get("cc", 0) >= 3:
        context["notes"].append(f"HIGH crowd control from {enemy_champion}. Tenacity items are worth considering.")
    if signals.get("resourceless"):
        context["notes"].append(f"{enemy_champion} has no resource cost — they can sustain pressure without running out of mana.")

    return context

# ─────────────────────────────────────────────
# COUNTER RECOMMENDATION ENGINE
# ─────────────────────────────────────────────

def get_counter_recommendations(enemy_champion, my_game_history=None):
    """
    Given an enemy champion, recommend picks based on:
    1. Enemy weaknesses from their intel profile
    2. Your personal performance data (if game_history provided)

    Returns structured recommendations.
    """
    enemy_intel = load_champion_intel(enemy_champion)
    if not enemy_intel:
        return {"error": f"No intel profile found for {enemy_champion}."}

    signals = enemy_intel.get("signals", {})
    enemy_style = enemy_intel.get("style_num")
    enemy_ratings = enemy_intel.get("ratings", {})

    # Derive what beats this champion from their profile
    weaknesses = []
    strengths = []

    if signals.get("has_healing"):
        weaknesses.append("Anti-healing items (Grievous Wounds) significantly reduce their sustain")
    if signals.get("has_suppression"):
        strengths.append("Suppression — cannot be escaped once cast begins")
    if enemy_style in SCALING_ARCHETYPES:
        weaknesses.append("Early pressure — they are weak before items")
        weaknesses.append("Invading their jungle before level 6")
    if enemy_style in EARLY_THREAT_ARCHETYPES:
        strengths.append(f"Strong levels 2-6 threat window")
        weaknesses.append("Falls off if they cannot convert early pressure into leads")
    if enemy_ratings.get("mobility", 0) <= 1:
        weaknesses.append("Low mobility — kiting and range are effective")
    if enemy_ratings.get("durability", 0) <= 1:
        weaknesses.append("Low durability — burst damage windows are available")
    if signals.get("ranged") is False:
        weaknesses.append("Melee — ranged champions can poke and disengage safely")

    # Personal history counter picks
    personal_recs = []
    if my_game_history:
        from collections import defaultdict
        champ_vs_enemy = defaultdict(lambda: {"wins": 0, "losses": 0})
        for g in my_game_history:
            if g.enemy and g.enemy.champion == enemy_champion:
                my_champ = g.champion
                if g.win:
                    champ_vs_enemy[my_champ]["wins"] += 1
                else:
                    champ_vs_enemy[my_champ]["losses"] += 1

        for champ, record in champ_vs_enemy.items():
            total = record["wins"] + record["losses"]
            if total >= 2:
                wr = round(record["wins"] / total * 100, 1)
                personal_recs.append({
                    "champion": champ,
                    "wins": record["wins"],
                    "losses": record["losses"],
                    "winrate": wr,
                    "games": total,
                })
        personal_recs.sort(key=lambda x: x["winrate"], reverse=True)

    return {
        "enemy": enemy_champion,
        "archetype": enemy_intel.get("archetype", ""),
        "key_mechanic": signals.get("key_mechanic", ""),
        "threat_window": signals.get("threat_window", ""),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "personal_recs": personal_recs,
        "invade_risk": signals.get("invade_threat_level", "UNKNOWN"),
    }

# ─────────────────────────────────────────────
# OUTPUT FORMATTERS
# ─────────────────────────────────────────────

def render_matchup_context(context):
    """Return structured matchup context data for display."""
    enemy = context["enemy_champion"]
    enemy_intel = context.get("enemy_intel")
    if not enemy_intel:
        return {"enemy_champion": enemy, "has_intel": False}

    signals = enemy_intel.get("signals", {})
    ratings = enemy_intel.get("ratings", {})

    cc_types = []
    if signals.get("hard_cc"):
        if signals.get("has_suppression"):
            cc_types.append("Suppression (R)")
        elif any(k in " ".join(signals["hard_cc"]) for k in ("stun", "stuns")):
            cc_types.append("Stun")
        elif any(k in " ".join(signals["hard_cc"]) for k in ("knock up", "knocks up")):
            cc_types.append("Knockup")
        elif "fear" in " ".join(signals["hard_cc"]):
            cc_types.append("Fear")
        elif "pull" in " ".join(signals["hard_cc"]):
            cc_types.append("Pull")
        else:
            cc_types.append("Hard CC")
    if signals.get("soft_cc"):
        cc_types.append("Slow")

    return {
        "enemy_champion": enemy,
        "has_intel": True,
        "archetype": enemy_intel.get("archetype", ""),
        "threat_window": context["threat_window"],
        "invade_risk": signals.get("invade_threat_level", "UNKNOWN"),
        "cc_types": cc_types,
        "key_mechanic": context["key_mechanic"],
        "win_condition": context["your_win_condition"],
        "invade_assessment": context["invade_risk"],
        "pick_context": context.get("pick_context", ""),
        "notes": context.get("notes", []),
    }


def print_matchup_context(context, indent="  "):
    data = render_matchup_context(context)
    enemy = data["enemy_champion"]

    if not data["has_intel"]:
        print(f"{indent}No champion intel available for {enemy}.")
        return

    print(f"{indent}── MATCHUP CONTEXT — {enemy} {'─'*35}")
    print()
    print(f"{indent}Archetype:     {data['archetype']}")
    print(f"{indent}Threat Window: {data['threat_window']}")
    print(f"{indent}Invade Risk:   {data['invade_risk']}")

    if data["cc_types"]:
        print(f"{indent}CC Types:      {', '.join(data['cc_types'])}")

    print()
    print(f"{indent}{data['key_mechanic']}")
    print()
    print(f"{indent}Your win condition: {data['win_condition']}")
    print()
    print(f"{indent}Invade assessment: {data['invade_assessment']}")

    if data["pick_context"]:
        print(f"{indent}Draft:     {data['pick_context']}")

    if data["notes"]:
        print()
        for note in data["notes"]:
            print(f"{indent}⚠  {note}")

    print()


def analyze_counter_command(enemy_champion, game_history=None):
    """Analyze counter recommendations. Returns structured dict with all counter data."""
    rec = get_counter_recommendations(enemy_champion, my_game_history=game_history)
    if "error" in rec:
        return {"error": rec["error"]}

    # Item recommendations (computed from intel)
    item_recs = []
    intel = load_champion_intel(enemy_champion)
    if intel:
        sig = intel.get("signals", {})
        tags = intel.get("tags", [])
        archetype = intel.get("archetype", "")
        damage_type = intel.get("damage_type", "")
        threat_window = sig.get("threat_window", "")
        if sig.get("has_healing"):
            item_recs.append("Grievous Wounds (Thornmail / Mortal Reminder / Chempunk Chainsword) — cuts their healing by 40%")
        if "Tank" in tags or intel.get("ratings", {}).get("durability", 0) >= 3:
            item_recs.append("Armor penetration (Lord Dominik's Regards / Serylda's Grudge) — bypasses their mitigation")
        if damage_type in ("Magic", "Mixed"):
            item_recs.append("Magic penetration (Void Staff / Shadowflame) — essential if they stack MR")
        if sig.get("has_suppression") or len(sig.get("hard_cc", [])) >= 2:
            item_recs.append("Tenacity (Mercury's Treads / Sterak's Gage) — reduces hard CC duration")
        archetype_lower = archetype.lower()
        if any(k in archetype_lower for k in ("assassin", "diver", "skirmisher")):
            item_recs.append("Armor (Randuin's Omen / Frozen Heart) — reduces burst from physical threats")
        if sig.get("early_threat") or (threat_window and "level" in threat_window.lower()):
            item_recs.append("Early survivability — avoid fighting them levels 3-5. Clear safely and scale.")

    return {**rec, "item_recommendations": item_recs}


def print_counter_command(enemy_champion, game_history=None):
    result = analyze_counter_command(enemy_champion, game_history=game_history)

    if "error" in result:
        print(f"\n  {result['error']}")
        return

    print(f"\n  {'='*62}")
    print(f"  VERDICT COUNTER — {enemy_champion}")
    print(f"  {'='*62}")
    print(f"  Archetype: {result['archetype']}")
    print(f"  Threat Window: {result['threat_window']}")
    print(f"  Invade Risk: {result['invade_risk']}")
    print()

    print(f"  ── KEY MECHANIC {'─'*47}")
    print(f"  {result['key_mechanic']}")
    print()

    if result["strengths"]:
        print(f"  ── WHAT THEY HAVE {'─'*44}")
        for s in result["strengths"]:
            print(f"  + {s}")
        print()

    if result["weaknesses"]:
        print(f"  ── HOW TO BEAT THEM {'─'*42}")
        for w in result["weaknesses"]:
            print(f"  → {w}")
        print()

    print(f"  ── RECOMMENDED ITEMS {'─'*41}")
    if result["item_recommendations"]:
        for r in result["item_recommendations"]:
            print(f"  → {r}")
    else:
        print(f"  No specific item counters identified. Standard build applies.")
    print()

    if result["personal_recs"]:
        print(f"  ── YOUR PERSONAL DATA vs {enemy_champion} {'─'*28}")
        for p in result["personal_recs"]:
            bar = "✓" if p["winrate"] >= 50 else "✗"
            print(f"  {bar} {p['champion']:<18} {p['wins']}W {p['losses']}L  ({p['winrate']}% WR across {p['games']} games)")
        print()
    else:
        print(f"  ── PERSONAL DATA {'─'*45}")
        print(f"  No games vs {enemy_champion} in cache yet.")
        print()

    print(f"  {'='*62}")
    print()


def analyze_intel_profile(champion_name):
    """Analyze champion intel profile. Returns structured dict with all profile data."""
    intel = load_champion_intel(champion_name)
    if not intel:
        return {"found": False, "champion_name": champion_name}

    signals = intel.get("signals", {})
    ratings = intel.get("ratings", {})

    # Derive countered_by and counters
    countered_by = []
    counters = []

    if signals.get("has_healing"):
        countered_by.append("Anti-heal champions — neutralizes sustain (Grievous Wounds counters their kit)")
    if signals.get("scaling_threat"):
        countered_by.append("Early pressure champions — punish them before items come online")
    if not signals.get("ranged"):
        countered_by.append("Ranged kiting — maintain distance and poke safely")
    if signals.get("invade_threat_level") in ("HIGH", "MEDIUM") and signals.get("early_threat"):
        countered_by.append("Ward coverage — early vision denies their invasion windows")
    if intel.get("ratings", {}).get("durability", 0) <= 1:
        countered_by.append("Burst damage champions — they are fragile and can be one-shot in skirmishes")

    if signals.get("has_suppression"):
        counters.append("Flash-reliant champions — suppression prevents the escape")
    if signals.get("early_threat"):
        counters.append("Champions with no escape — easy to run down in the early game")
    if not signals.get("scaling_threat") and not signals.get("teamfight_threat"):
        counters.append("Scaling compositions — must end early or lose the game")
    if intel.get("ratings", {}).get("durability", 0) >= 3:
        counters.append("Low-burst champions — their durability makes them hard to kill without sustained damage")
    if signals.get("has_healing"):
        counters.append("Squishy carries without sustain — outlasts them through healing")

    # Format abilities for display
    abilities = []
    passive = intel.get("passive", {})
    if passive.get("name"):
        abilities.append({
            "slot": "P", "name": passive["name"],
            "description": passive.get("description", ""),
            "cooldown": "", "range": "",
        })
    for ab in intel.get("abilities", []):
        abilities.append({
            "slot": ab["slot"], "name": ab["name"],
            "description": ab.get("description", ""),
            "cooldown": ab.get("cooldown", ""), "range": ab.get("range", ""),
        })

    return {
        "found": True,
        "name": intel.get("name", ""),
        "title": intel.get("title", ""),
        "archetype": intel.get("archetype", ""),
        "style_num": intel.get("style_num"),
        "damage_type": intel.get("damage_type", ""),
        "attack_type": intel.get("attack_type", ""),
        "difficulty": intel.get("difficulty", ""),
        "roles": intel.get("roles", []),
        "ratings": ratings,
        "signals": signals,
        "abilities": abilities,
        "countered_by": countered_by,
        "counters": counters,
    }


def _wrap_text(text, width=60, indent="     "):
    """Word-wrap text for terminal display."""
    words = text.split()
    lines = []
    line = indent
    for word in words:
        if len(line) + len(word) + 1 > width + len(indent):
            lines.append(line)
            line = indent + word
        else:
            line = line + " " + word if line.strip() else indent + word
    if line.strip():
        lines.append(line)
    return "\n".join(lines)


# ── Champion Base Stats ──────────────────────────────────────────────

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

def print_champ_stats(champion):
    """Print champion base stats from LeagueVault."""
    import os
    from verdict_paths import VAULT_PATH

    query_lower = champion.lower()
    vault_path = VAULT_PATH

    files = os.listdir(vault_path)
    exact = [f for f in files if f.lower() == f"{query_lower}.md"]
    starts = [f for f in files if f.lower().startswith(query_lower)]
    contains = [f for f in files if query_lower in f.lower() and len(query_lower) >= 4]

    matches = exact or starts or contains
    if not matches:
        print(f"No champion found matching '{champion}'")
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
            inner = line[4:]
            if ":**" in inner:
                label, val = inner.split(":**", 1)
                stats[label.strip().lower().replace(" ", "")] = val.strip()

    print(f"\n  {'='*45}")
    print(f"  {name} — {title}")
    print(f"  Tags: {tags}")
    print(f"  {'='*45}")
    for key, label in STAT_LABELS.items():
        val = stats.get(key) or stats.get(key.replace("perlevel", "perlevel"))
        if val:
            print(f"  {label:<22} {val}")
    print()


def print_intel_profile(champion_name):
    result = analyze_intel_profile(champion_name)

    if not result["found"]:
        print(f"\n  No intel profile found for {champion_name}.")
        print(f"  Run 'face update' to refresh the vault.")
        return

    print(f"\n  {'='*62}")
    print(f"  CHAMPION INTEL — {result['name']}")
    print(f"  {result['title']}")
    print(f"  {'='*62}")
    print()
    print(f"  Archetype:    {result['archetype']}  (Style {result['style_num']})")
    print(f"  Damage Type:  {result['damage_type']}")
    print(f"  Attack Type:  {result['attack_type'].capitalize()}")
    print(f"  Difficulty:   {result['difficulty']}")
    print(f"  Roles:        {', '.join(r.capitalize() for r in result['roles'])}")
    print()

    print(f"  ── PLAYSTYLE RATINGS {'─'*41}")
    for key, label in [("damage","Damage"),("durability","Durability"),
                       ("cc","Crowd Control"),("mobility","Mobility"),("utility","Utility")]:
        val = result["ratings"].get(key, 0)
        bar = "█" * val + "░" * (3 - val)
        tier = ["","Low","Medium","High"][val] if val else "N/A"
        print(f"  {label:<15} {bar}  {tier}")
    print()

    sig = result["signals"]
    print(f"  ── THREAT SIGNALS {'─'*44}")
    print(f"  Threat Window:  {sig.get('threat_window', 'Unknown')}")
    print(f"  Invade Risk:    {sig.get('invade_threat_level', 'UNKNOWN')}")
    if sig.get("has_suppression"):
        print(f"  Suppression:    YES — ult cannot be escaped with flash")
    if sig.get("has_healing"):
        print(f"  Built-in Heal:  YES — anti-healing reduces effectiveness")
    if sig.get("resourceless"):
        print(f"  Resourceless:   YES — no mana constraint on ability usage")
    if sig.get("hard_cc"):
        print(f"  Hard CC:        {len(sig['hard_cc'])} type(s) detected")
    print()

    print(f"  ── KEY MECHANIC {'─'*46}")
    print(f"  {sig.get('key_mechanic', 'No key mechanic derived.')}")
    print()

    print(f"  ── ABILITIES {'─'*49}")
    for ab in result["abilities"]:
        cd = f"  CD: {ab['cooldown']}s" if ab.get("cooldown") else ""
        rng = f"  Range: {ab['range']}" if ab.get("range") else ""
        print(f"  {ab['slot']}  {ab['name']}{cd}{rng}")
        if ab.get("description"):
            print(_wrap_text(ab["description"]))
        print()

    if result["countered_by"]:
        print(f"  ── COUNTERED BY {'─'*46}")
        for item in result["countered_by"]:
            print(f"  → {item}")
        print()

    if result["counters"]:
        print(f"  ── COUNTERS {'─'*50}")
        for item in result["counters"]:
            print(f"  → {item}")
        print()

    print(f"  {'='*62}")
    print()
