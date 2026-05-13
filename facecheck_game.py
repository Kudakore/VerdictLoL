import json
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Data layer
from facecheck_data import get_current_rank_string

# Champion Intelligence — optional, graceful fallback if vault not available
try:
    sys.path.insert(0, "C:\\Facecheck")
    from facecheck_champ_intel import (
        get_matchup_context, print_matchup_context,
        print_counter_command, print_intel_profile,
        load_champion_intel
    )
    INTEL_AVAILABLE = True
except Exception:
    INTEL_AVAILABLE = False

# Synthesis Layer — 7 Domain-Pure Engines
try:
    sys.path.insert(0, "C:\\Facecheck")
    from facecheck_engine_death import run_death_engine
    from facecheck_engine_economy import run_economy_engine
    from facecheck_engine_combat import run_combat_engine
    from facecheck_engine_durability import run_durability_engine
    from facecheck_engine_vision import run_vision_engine
    from facecheck_engine_objective import run_objective_engine
    from facecheck_engine_draft import run_draft_engine
    from facecheck_player_model import get_or_create_player_model
    from facecheck_synthesis import SynthesisLayer, MultiEngineOutput
    from facecheck_similarity import SimilarityEngine, SimilarityOutput
    SYNTHESIS_AVAILABLE = True
except Exception:
    SYNTHESIS_AVAILABLE = False

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def fmt_num(n, plus=False):
    if n is None:
        return "N/A"
    n = round(n)
    return f"+{n}" if plus and n > 0 else str(n)

def fmt_k(n):
    """Format large numbers with commas."""
    if n is None:
        return "N/A"
    return f"{int(n):,}"

def role_order(role):
    order = {"TOP": 0, "JUNGLE": 1, "MID": 2, "BOT": 3, "SUPPORT": 4, "N/A": 5}
    return order.get(role, 5)

ROLE_LABELS = {
    "JUNGLE":  "jungler",
    "MIDDLE":  "mid laner",
    "TOP":     "top laner",
    "BOTTOM":  "ADC",
    "UTILITY": "support",
    "":        "opponent",
}

def enemy_role_label(games):
    """Derive the most common role from a list of games and return the label."""
    if not games:
        return "opponent"
    roles = [g.get("role", "") for g in games]
    most_common = max(set(roles), key=roles.count)
    return ROLE_LABELS.get(most_common, "opponent")

def get_ranked_games(cache, champion=None, count=None):
    """Return ranked games only, optionally filtered."""
    games = [g for g in cache.get("games", []) if g.get("queue_id") in (420, 440)]
    if champion:
        games = [g for g in games if g["champion"].lower() == champion.lower()]
    if count:
        games = games[:count]
    return games

# ─────────────────────────────────────────────
# PER-GAME DIAGNOSIS
# ─────────────────────────────────────────────

def diagnose_game(game, game_index=None, historical_games=None):
    """
    Generate findings for a single game.
    historical_games: all cached games for context (e.g. build winrate lookup)
    """
    findings = []
    enemy = game.get("enemy")
    duration_min = game.get("duration_min", 1)
    win = game.get("win", False)
    role = game.get("role", "JUNGLE")
    enemy_role_str = ROLE_LABELS.get(role, "opponent")
    matchup_category = f"{role.capitalize().replace('_', ' ')} Matchup" if role not in ("JUNGLE",) else "Jungle Matchup"

    # ── BUILD ──────────────────────────────────────────────────────
    first_item = game.get("first_item")
    if first_item and historical_games:
        item_games = [g for g in historical_games if g.get("first_item") == first_item]
        if len(item_games) >= 5:
            wr = round(sum(1 for g in item_games if g["win"]) / len(item_games) * 100, 1)
            if wr < 45:
                findings.append({
                    "level": "CRITICAL",
                    "category": "Build",
                    "text": f"Starting {first_item}: {wr}% winrate across {len(item_games)} games in your history. This is a known losing pattern for you."
                })
            elif wr >= 55:
                findings.append({
                    "level": "POSITIVE",
                    "category": "Build",
                    "text": f"Starting {first_item}: {wr}% winrate across {len(item_games)} games. Good call."
                })

    # ── EARLY GAME ─────────────────────────────────────────────────
    early_deaths = game.get("early_deaths", 0)
    if early_deaths >= 3:
        findings.append({
            "level": "CRITICAL",
            "category": "Early Game",
            "text": f"{early_deaths} deaths before 15 minutes. The game was compromised before mid-game started."
        })
    elif early_deaths >= 2:
        findings.append({
            "level": "CLEAR",
            "category": "Early Game",
            "text": f"{early_deaths} deaths pre-15min. Early pressure cost you farm and tempo."
        })

    killed_by_enemy = game.get("killed_by_enemy_jungler", 0)
    if killed_by_enemy >= 2:
        findings.append({
            "level": "CRITICAL",
            "category": "Early Game",
            "text": f"Killed by the enemy {enemy_role_str} {killed_by_enemy} times. You were targeted and it worked."
        })

    cs_15 = game.get("cs_15")
    if cs_15 is not None:
        if cs_15 < 55:
            findings.append({
                "level": "CRITICAL",
                "category": "Early Game",
                "text": f"{cs_15} CS at 15 minutes. That is a significant farm deficit early — below the threshold for a healthy jungle clear."
            })
        elif cs_15 < 70:
            findings.append({
                "level": "CLEAR",
                "category": "Early Game",
                "text": f"{cs_15} CS at 15 minutes. Slightly behind pace. Invades or slow clears cost you here."
            })
        elif cs_15 >= 90:
            findings.append({
                "level": "POSITIVE",
                "category": "Early Game",
                "text": f"{cs_15} CS at 15 minutes. Strong early farm. You controlled your {role.lower()} in the opening phase."
            })

    # ── GOLD ───────────────────────────────────────────────────────
    gold_lead = game.get("gold_lead_15")
    if gold_lead is not None:
        if gold_lead <= -800:
            findings.append({
                "level": "CRITICAL",
                "category": "Economy",
                "text": f"{fmt_num(gold_lead)} gold vs enemy {enemy_role_str} at 15 minutes. That deficit equals a completed component item. The resource gap was established before mid-game."
            })
        elif gold_lead <= -400:
            findings.append({
                "level": "CLEAR",
                "category": "Economy",
                "text": f"{fmt_num(gold_lead)} gold vs enemy {enemy_role_str} at 15 minutes. Behind in resources entering mid-game."
            })
        elif gold_lead >= 800:
            findings.append({
                "level": "POSITIVE",
                "category": "Economy",
                "text": f"+{fmt_num(gold_lead)} gold vs enemy {enemy_role_str} at 15 minutes. You won the early economy battle."
            })

    # ── VISION ─────────────────────────────────────────────────────
    control_wards = game.get("control_wards", 0)
    wards_placed = game.get("wards_placed", 0)
    if duration_min >= 25:
        if control_wards == 0:
            findings.append({
                "level": "CRITICAL",
                "category": "Vision",
                "text": f"0 control wards placed in {round(duration_min)} minutes. Dragon, baron, and river entrances were blind the entire game."
            })
        elif control_wards == 1:
            findings.append({
                "level": "CLEAR",
                "category": "Vision",
                "text": f"1 control ward placed in {round(duration_min)} minutes. Insufficient map control for a game this length."
            })

    vision_per_min = game.get("vision_per_min", 0)
    if vision_per_min < 0.7 and duration_min >= 20:
        findings.append({
            "level": "CLEAR",
            "category": "Vision",
            "text": f"{vision_per_min} vision/min. Below average map presence. Objectives were contested without information."
        })

    # ── ENEMY MATCHUP ──────────────────────────────────────────────
    if enemy:
        cs_diff = game.get("cs_final", 0) - enemy.get("cs", 0)
        if cs_diff <= -50:
            findings.append({
                "level": "CRITICAL",
                "category": matchup_category,
                "text": f"{fmt_num(cs_diff)} CS vs enemy {enemy_role_str}. That gap is approximately {abs(cs_diff) * 20:,} gold in farm. The 1v1 was lost."
            })
        elif cs_diff <= -20:
            findings.append({
                "level": "CLEAR",
                "category": matchup_category,
                "text": f"{fmt_num(cs_diff)} CS vs enemy {enemy_role_str}. Behind in the farm race."
            })
        elif cs_diff >= 50:
            findings.append({
                "level": "POSITIVE",
                "category": matchup_category,
                "text": f"+{cs_diff} CS vs enemy {enemy_role_str}. You won the farm battle convincingly."
            })

        dmg_diff = game.get("damage", 0) - enemy.get("damage", 0)
        if dmg_diff <= -5000:
            findings.append({
                "level": "CRITICAL",
                "category": matchup_category,
                "text": f"{fmt_k(dmg_diff)} damage vs enemy {enemy_role_str}. The enemy {enemy_role_str} was the bigger combat threat on the map."
            })
        elif dmg_diff >= 5000:
            findings.append({
                "level": "POSITIVE",
                "category": matchup_category,
                "text": f"+{fmt_k(dmg_diff)} damage vs enemy {enemy_role_str}. You out-threatened them in fights."
            })

        kill_diff = game.get("kills", 0) - enemy.get("kills", 0)
        if kill_diff <= -4:
            findings.append({
                "level": "CRITICAL",
                "category": matchup_category,
                "text": f"{fmt_num(kill_diff)} kills vs enemy {enemy_role_str}. The 1v1 duel went heavily against you."
            })
        elif kill_diff >= 4:
            findings.append({
                "level": "POSITIVE",
                "category": matchup_category,
                "text": f"+{kill_diff} kills vs enemy {enemy_role_str}. You dominated the individual matchup."
            })

    # ── DEATHS ─────────────────────────────────────────────────────
    total_deaths = game.get("deaths", 0)
    if total_deaths >= 10:
        findings.append({
            "level": "CRITICAL",
            "category": "Deaths",
            "text": f"{total_deaths} deaths. Feeding at this level gives the enemy team uncontrollable snowball potential."
        })
    elif total_deaths >= 7:
        findings.append({
            "level": "CLEAR",
            "category": "Deaths",
            "text": f"{total_deaths} deaths. Too many deaths to maintain map pressure and objective control."
        })
    elif total_deaths <= 2 and duration_min >= 25:
        findings.append({
            "level": "POSITIVE",
            "category": "Deaths",
            "text": f"{total_deaths} deaths in {round(duration_min)} minutes. Clean game — you stayed alive and kept pressure."
        })

    # ── OBJECTIVES ─────────────────────────────────────────────────
    my_team = game.get("my_team", {})
    enemy_team = game.get("enemy_team", {})
    if my_team and enemy_team:
        my_drags = my_team.get("dragon_kills", 0)
        enemy_drags = enemy_team.get("dragon_kills", 0)
        if enemy_drags >= 3 and my_drags == 0:
            findings.append({
                "level": "CRITICAL",
                "category": "Objectives",
                "text": f"Enemy team took {enemy_drags} dragons, your team took 0. The map was conceded entirely."
            })
        elif my_drags >= 3 and enemy_drags == 0:
            findings.append({
                "level": "POSITIVE",
                "category": "Objectives",
                "text": f"Your team secured {my_drags} dragons with 0 given up. Dominant objective control."
            })

        my_towers = my_team.get("tower_kills", 0)
        enemy_towers = enemy_team.get("tower_kills", 0)
        if enemy_towers >= 6 and my_towers <= 2:
            findings.append({
                "level": "CRITICAL",
                "category": "Objectives",
                "text": f"Enemy team destroyed {enemy_towers} towers vs your {my_towers}. The map was lost structurally."
            })

    # ── TEAM DIFF ──────────────────────────────────────────────────
    if my_team and enemy_team:
        my_kills = my_team.get("kills", 0)
        enemy_kills = enemy_team.get("kills", 0)
        my_deaths = my_team.get("deaths", 0)

        if my_deaths >= 30 and duration_min < 35:
            findings.append({
                "level": "CRITICAL",
                "category": "Team",
                "text": f"Your team died {my_deaths} times vs {enemy_kills} enemy kills. Collective feeding made this unwinnable regardless of your performance."
            })
        elif enemy_kills >= my_kills * 2 and not win:
            findings.append({
                "level": "CLEAR",
                "category": "Team",
                "text": f"Team kill differential: {my_kills} vs {enemy_kills}. The enemy team had a significant team-wide advantage."
            })

    # ── PERFORMANCE HIGHLIGHTS ─────────────────────────────────────
    largest_spree = game.get("largest_killing_spree", 0)
    if largest_spree >= 5:
        findings.append({
            "level": "POSITIVE",
            "category": "Performance",
            "text": f"Killing spree of {largest_spree}. You found your moments and capitalized."
        })

    turret_kills = game.get("turret_kills", 0)
    if turret_kills >= 3:
        findings.append({
            "level": "POSITIVE",
            "category": "Performance",
            "text": f"{turret_kills} turrets destroyed. Strong objective conversion after picks."
        })

    return findings

def generate_verdict(game, findings):
    """Synthesize the top findings into a single paragraph verdict."""
    win = game.get("win", False)
    champion = game.get("champion", "")
    duration = round(game.get("duration_min", 0))
    enemy = game.get("enemy", {})
    enemy_champ = enemy.get("champion", "enemy jungler") if enemy else "enemy jungler"

    # Role-aware language
    role = game.get("role", "JUNGLE")
    role_map = {
        "JUNGLE":  ("the jungle", "jungle", "jungle control", "jungle 1v1"),
        "MIDDLE":  ("mid lane", "mid", "lane control", "lane matchup"),
        "TOP":     ("top lane", "top", "lane control", "lane matchup"),
        "BOTTOM":  ("bot lane", "ADC", "lane control", "lane matchup"),
        "UTILITY": ("support", "support", "vision control", "support matchup"),
    }
    rl = role_map.get(role, role_map["JUNGLE"])
    r_the, r_short, r_control, r_matchup = rl

    critical = [f for f in findings if f["level"] == "CRITICAL"]
    positives = [f for f in findings if f["level"] == "POSITIVE"]
    categories = [f["category"] for f in critical]

    if win:
        if "Jungle Matchup" in categories or "Economy" in categories:
            return f"You controlled the game from {r_the}. The early resource advantage translated directly into map control and the win."
        elif positives:
            pos_cats = [f["category"] for f in positives]
            return f"Clean performance. {', '.join(set(pos_cats[:2]))} were strengths in this game. Keep building on this."
        else:
            return f"Win in {duration} minutes. The game went in your favor — replicate the approach."
    else:
        # Loss verdict
        if not critical:
            return f"Close loss in {duration} minutes. No dominant factors — this one came down to team execution and variance."

        # Build a narrative from the critical findings
        primary = critical[0]["category"]
        secondary = critical[1]["category"] if len(critical) > 1 else None

        if "Early Game" in categories and "Economy" in categories:
            early_deaths = game.get("early_deaths", 0)
            gold_lead = game.get("gold_lead_15", 0) or 0
            return (
                f"This game was decided in the first 15 minutes. "
                f"{early_deaths} early deaths and {fmt_num(gold_lead)} gold vs {enemy_champ} at 15 — "
                f"the deficit was structural before mid-game even started. "
                f"When Viego falls behind that early, the reset mechanic has nothing to work with."
                if champion == "Viego" else
                f"This game was decided in the first 15 minutes. "
                f"{early_deaths} early deaths and {fmt_num(gold_lead)} gold vs {enemy_champ} at 15 — "
                f"the deficit was structural before mid-game even started."
            )
        elif "Jungle Matchup" in categories and "Deaths" in categories:
            deaths = game.get("deaths", 0)
            cs_final = game.get("cs_final", 0)
            enemy_cs = enemy.get("cs", 0) if enemy else 0
            cs_diff = cs_final - enemy_cs
            return (
                f"{enemy_champ} won the {r_matchup} outright. "
                f"{fmt_num(cs_diff)} CS, {deaths} deaths on your end. "
                f"The individual matchup went against you and it cascaded into a team-wide deficit."
            )
        elif "Team" in categories:
            my_team = game.get("my_team", {})
            my_deaths = my_team.get("deaths", 0) if my_team else 0
            return (
                f"Your team collapsed around you. {my_deaths} team deaths tells the story — "
                f"lanes fed and the map was unplayable before you could establish {r_control}. "
                f"This loss has more to do with the people in your lobby than your individual performance."
            )
        elif "Vision" in categories and "Objectives" in categories:
            return (
                f"Map control was the decisive factor. No control wards, conceded objectives — "
                f"the enemy team moved freely and converted it into structural advantages you couldn't recover."
            )
        elif "Build" in categories:
            first_item = game.get("first_item", "that first item")
            return (
                f"The build choice cost you before the first fight. "
                f"{first_item} is a losing pattern in your history — the data has been telling you this. "
                f"Fix the first item and this game looks different."
            )
        else:
            primary_text = critical[0]["text"].split(".")[0]
            return f"Primary loss factor: {primary_text}. The game unraveled from there."

# ─────────────────────────────────────────────
# TEAM BREAKDOWN
# ─────────────────────────────────────────────

def analyze_player(player, avg_damage, avg_cs, is_enemy_team=False):
    """Generate a one-line note about a player if something stands out."""
    notes = []
    kda_ratio = (player["kills"] + player["assists"]) / max(player["deaths"], 1)
    dmg = player["damage"]
    cs = player["cs"]

    if player["deaths"] >= 8:
        notes.append(f"fed hard ({player['deaths']} deaths)")
    elif player["deaths"] >= 6:
        notes.append(f"died too much ({player['deaths']} deaths)")

    if dmg >= avg_damage * 1.5:
        notes.append(f"dominant damage ({fmt_k(dmg)})")
    elif dmg < avg_damage * 0.5 and player["role"] not in ("SUPPORT",):
        notes.append(f"low impact ({fmt_k(dmg)} damage)")

    if kda_ratio >= 5 and player["kills"] + player["assists"] >= 10:
        notes.append(f"carried ({player['kills']}/{player['deaths']}/{player['assists']})")

    if player.get("first_blood_kill"):
        notes.append("got first blood")

    if player.get("turret_kills", 0) >= 3:
        notes.append(f"split push threat ({player['turret_kills']} towers)")

    if player.get("control_wards", 0) == 0 and player["role"] not in ("JUNGLE",) and not is_enemy_team:
        notes.append("0 control wards")

    return ", ".join(notes) if notes else None

def print_team_breakdown(game):
    """Print the full 10-player breakdown after verdict."""
    all_players = game.get("all_players", [])
    if not all_players:
        return

    my_team = [p for p in all_players if p["team"] == "ally"]
    enemy_team = [p for p in all_players if p["team"] == "enemy"]

    my_team.sort(key=lambda p: role_order(p["role"]))
    enemy_team.sort(key=lambda p: role_order(p["role"]))

    duration_min = game.get("duration_min", 1)
    my_obj = game.get("my_team", {})
    enemy_obj = game.get("enemy_team", {})

    # Avg damage for context
    all_dmg = [p["damage"] for p in all_players]
    avg_dmg = sum(all_dmg) / len(all_dmg) if all_dmg else 1

    print(f"\n  ── TEAM BREAKDOWN {'─'*45}")

    for label, team, obj, is_enemy in [("YOUR TEAM", my_team, my_obj, False), ("ENEMY TEAM", enemy_team, enemy_obj, True)]:
        team_kills = sum(p["kills"] for p in team)
        team_deaths = sum(p["deaths"] for p in team)
        team_assists = sum(p["assists"] for p in team)
        dragons = obj.get("dragon_kills", 0)
        barons = obj.get("baron_kills", 0)
        towers = obj.get("tower_kills", 0)
        fb = "✓ First Blood" if obj.get("first_blood") else ""
        fd = "✓ First Dragon" if obj.get("first_dragon") else ""
        ft = "✓ First Tower" if obj.get("first_tower") else ""

        badges = "  ".join(b for b in [fb, fd, ft] if b)

        print(f"\n  ┌─ {label} — {team_kills}/{team_deaths}/{team_assists}  |  🐉{dragons}  🏰{barons}  🗼{towers}")
        if badges:
            print(f"  │  {badges}")
        print(f"  │")
        print(f"  │  {'Role':<9} {'Champion':<14} {'KDA':<12} {'CS':<6} {'Damage':<10} {'Vision':<8} {'Gold':<8} Notes")
        print(f"  │  {'─'*100}")

        for p in team:
            kda = f"{p['kills']}/{p['deaths']}/{p['assists']}"
            note = analyze_player(p, avg_dmg, 0, is_enemy_team=is_enemy)
            me = " ◄" if p.get("is_me") else ""
            note_str = f"  {note}" if note else ""
            print(f"  │  {p['role']:<9} {p['champion']:<14} {kda:<12} {p['cs']:<6} {fmt_k(p['damage']):<10} {p['vision']:<8} {fmt_k(p['gold']):<8}{me}{note_str}")

        # Build orders for this team
        print(f"  │")
        print(f"  │  BUILD ORDERS:")
        for p in team:
            if p.get("build_order"):
                me = " ◄" if p.get("is_me") else ""
                build_str = " → ".join(p["build_order"][:4])
                if len(p["build_order"]) > 4:
                    build_str += " ..."
                print(f"  │  {p['role']:<9} {p['champion']:<14} {build_str}{me}")

        print(f"  └{'─'*108}")

    # Comp analysis
    print(f"\n  ── COMPOSITION NOTES {'─'*41}")
    my_roles = [p["role"] for p in my_team]
    enemy_roles = [p["role"] for p in enemy_team]

    # Who carried the enemy team
    enemy_sorted = sorted(enemy_team, key=lambda p: p["damage"], reverse=True)
    top_enemy = enemy_sorted[0] if enemy_sorted else None
    if top_enemy and top_enemy["damage"] > avg_dmg * 1.3:
        print(f"  Enemy carry: {top_enemy['champion']} ({top_enemy['role']}) — {fmt_k(top_enemy['damage'])} damage, {top_enemy['kills']}/{top_enemy['deaths']}/{top_enemy['assists']} KDA")
        print(f"  They were the primary threat. Everything they touched turned into pressure.")

    # Did anyone on your team actually perform
    my_sorted = sorted(my_team, key=lambda p: p["damage"], reverse=True)
    top_ally = my_sorted[0] if my_sorted else None
    if top_ally and not top_ally.get("is_me") and top_ally["damage"] > avg_dmg * 1.2:
        print(f"  Ally performer: {top_ally['champion']} ({top_ally['role']}) — {fmt_k(top_ally['damage'])} damage, {top_ally['kills']}/{top_ally['deaths']}/{top_ally['assists']} KDA")

    # Feeders
    feeders = [p for p in my_team if p["deaths"] >= 8 and not p.get("is_me")]
    if feeders:
        feeder_str = ", ".join(f"{p['champion']} ({p['deaths']} deaths)" for p in feeders)
        print(f"  Feeding: {feeder_str}")
        if len(feeders) >= 2:
            print(f"  Multiple lanes feeding simultaneously makes jungle recovery impossible.")

    print()

# ─────────────────────────────────────────────
# SYNTHESIS VERDICT RENDERER
# ─────────────────────────────────────────────

def print_synthesis_block(verdict):
    """Render a full synthesis verdict to the user."""
    print(f"\n  ── SYNTHESIS VERDICT {'─'*41}")
    print(f"  ╔{'═'*60}╗")
    print(f"  ║  {verdict.statement:<56} ║")
    print(f"  ╚{'═'*60}╝")
    print(f"\n  Confidence: {verdict.confidence:.0%}")
    if verdict.summary:
        print(f"\n  {verdict.summary}")

    if verdict.primary_evidence:
        print(f"\n  Evidence:")
        for ev in verdict.primary_evidence:
            if ev.evidence_type == "stat":
                print(f"    • {ev.description}: {ev.value} ({ev.context})")
            elif ev.evidence_type == "pattern":
                print(f"    • {ev.description} at {ev.value} — {ev.context}")
            else:
                print(f"    • {ev.description}: {ev.value}")

    if verdict.lessons:
        print(f"\n  Lessons:")
        for lesson in verdict.lessons:
            badge = {"critical": "[!]", "high": "[!]", "medium": "[~]", "low": "[-]"}
            print(f"    {badge.get(lesson.priority, '[~]')} [{lesson.priority.upper()}] {lesson.text}")

    if verdict.divergences:
        print(f"\n  Divergences from your pattern:")
        for div in verdict.divergences:
            print(f"    • {div}")

    if verdict.drill_down_available:
        print(f"\n  Drill-down: {verdict.drill_down_prompt}")

    if verdict.cluster_label:
        print(f"\n  Pattern: {verdict.cluster_label}")
    if verdict.mechanism:
        print(f"\n  Mechanism: {verdict.mechanism}")
    if verdict.counterfactual_insight:
        print(f"  {verdict.counterfactual_insight}")
    if verdict.similar_games:
        print(f"\n  Structurally similar games: {', '.join(verdict.similar_games[:3])}")
    if verdict.pattern_insight:
        print(f"  {verdict.pattern_insight}")

    if verdict.matched_patterns:
        print(f"\n  Matched Patterns ({len(verdict.matched_patterns)}):")
        for pid in verdict.matched_patterns[:3]:
            print(f"    • {pid.replace('_', ' ').title()}")


# ─────────────────────────────────────────────
# FULL SINGLE GAME OUTPUT
# ─────────────────────────────────────────────

def print_full_game(game, game_number=None, historical_games=None, legacy=False, player_id=None, cache=None):
    win = game["win"]
    result = "WIN" if win else "LOSS"
    border = "╔" + "═" * 62 + "╗"
    border_bot = "╚" + "═" * 62 + "╝"
    divider = "  " + "═" * 62

    label = f"GAME {game_number}" if game_number else "LAST GAME"
    rank_str = get_current_rank_string(cache) if cache else None

    print(f"\n  {border}")
    print(f"  ║  FACECHECK — {label:<48}║")
    if rank_str and player_id:
        print(f"  ║  {player_id}  —  {rank_str:<43}║")
    elif player_id:
        print(f"  ║  {player_id:<55}║")
    print(f"  ║  {game['queue']}  |  {game['champion']}  |  {game['duration_min']}m  |  {result:<33}║")
    print(f"  {border_bot}")

    duration_min = game["duration_min"]
    enemy = game.get("enemy", {})

    # ── YOUR PERFORMANCE ──────────────────────────────────────────
    print(f"\n  ── YOUR PERFORMANCE {'─'*43}")
    kda = f"{game['kills']}/{game['deaths']}/{game['assists']}"
    print(f"  KDA:      {kda}")
    my_team_kills = game.get("my_team", {}).get("kills", 0)
    my_team_deaths = game.get("my_team", {}).get("deaths", 0)
    ally_dmg = sum(p["damage"] for p in game.get("all_players", []) if p.get("team") == "ally")
    kp_pct = round((game["kills"] + game["assists"]) / max(my_team_kills, 1) * 100)
    ds_pct = round(game["deaths"] / max(my_team_deaths, 1) * 100)
    dmg_pct = round(game["damage"] / max(ally_dmg, 1) * 100)
    print(f"  KP:       {kp_pct}%  |  Dmg Share: {dmg_pct}%  |  Death Share: {ds_pct}%")
    print(f"  CS:       {game['cs_final']}  ({game['cs_per_min']}/min)  |  CS@10: {game.get('cs_10', 'N/A')}  |  CS@15: {game.get('cs_15', 'N/A')}")
    print(f"  Damage:   {fmt_k(game['damage'])}  ({fmt_k(game.get('damage_per_min', 0))}/min)")
    print(f"  Vision:   {game['vision']}  ({game.get('vision_per_min', 0)}/min)  |  Wards: {game.get('wards_placed', 0)}  |  Control: {game.get('control_wards', 0)}")
    print(f"  Gold:     {fmt_k(game['gold'])}  ({fmt_k(game.get('gold_per_min', 0))}/min)  |  Gold@15: {fmt_k(game.get('gold_15'))}")
    if game.get("turret_kills", 0):
        print(f"  Towers:   {game['turret_kills']}")
    if game.get("first_blood_kill"):
        print(f"  First Blood: ✓")
    if game.get("largest_killing_spree", 0) >= 3:
        print(f"  Killing Spree: {game['largest_killing_spree']}")
    build_str = " → ".join(game.get("build_order", []))
    print(f"  Build:    {build_str if build_str else 'N/A'}")

    # ── ENEMY COUNTERPART ─────────────────────────────────────────────
    ROLE_HEADERS = {
        "JUNGLE":  "ENEMY JUNGLER",
        "TOP":     "ENEMY TOP LANER",
        "MIDDLE":  "ENEMY MID LANER",
        "BOTTOM":  "ENEMY ADC",
        "UTILITY": "ENEMY SUPPORT",
    }
    role = game.get("role", "JUNGLE")
    enemy_role_header = ROLE_HEADERS.get(role, "ENEMY COUNTERPART")
    if enemy:
        print(f"\n  ── {enemy_role_header} {'─'*46}")
        enemy_kda = f"{enemy['kills']}/{enemy['deaths']}/{enemy['assists']}"
        cs_diff = game['cs_final'] - enemy.get('cs', 0)
        dmg_diff = game['damage'] - enemy.get('damage', 0)
        gold_diff = game['gold'] - enemy.get('gold', 0)
        gold_15_diff = game.get('gold_lead_15')

        def diff_label(val):
            """Show differential from YOUR perspective — positive means YOU are ahead."""
            if val is None: return "N/A"
            v = round(val)
            if v > 0:  return f"+{v} your favor"
            if v < 0:  return f"{v} their favor"
            return "even"

        print(f"  {enemy['champion']}  |  {enemy_kda}")
        print(f"  CS:       {enemy.get('cs', 'N/A')}  ({diff_label(cs_diff)})")
        print(f"  Damage:   {fmt_k(enemy.get('damage'))}  ({diff_label(dmg_diff)})")
        print(f"  Gold:     {fmt_k(enemy.get('gold'))}  ({diff_label(gold_diff)})")
        if gold_15_diff is not None:
            print(f"  Gold@15:  {diff_label(gold_15_diff)}")
        if game.get("killed_by_enemy_jungler", 0):
            print(f"  Killed you: {game['killed_by_enemy_jungler']}x")

    # ── TEAM SUMMARY ──────────────────────────────────────────────
    my_team_data = game.get("my_team", {})
    enemy_team_data = game.get("enemy_team", {})
    if my_team_data and enemy_team_data:
        print(f"\n  ── TEAM SUMMARY {'─'*47}")
        print(f"  {'':12} {'Kills':<8} {'Deaths':<8} {'Dragons':<10} {'Barons':<8} {'Towers'}")
        print(f"  {'Your Team':<12} {my_team_data.get('kills', 0):<8} {my_team_data.get('deaths', 0):<8} {my_team_data.get('dragon_kills', 0):<10} {my_team_data.get('baron_kills', 0):<8} {my_team_data.get('tower_kills', 0)}")
        print(f"  {'Enemy Team':<12} {enemy_team_data.get('kills', 0):<8} {enemy_team_data.get('deaths', 0):<8} {enemy_team_data.get('dragon_kills', 0):<10} {enemy_team_data.get('baron_kills', 0):<8} {enemy_team_data.get('tower_kills', 0)}")

        firsts = []
        if my_team_data.get("first_blood"): firsts.append("First Blood")
        if my_team_data.get("first_dragon"): firsts.append("First Dragon")
        if my_team_data.get("first_tower"): firsts.append("First Tower")
        if firsts:
            print(f"  Your team secured: {', '.join(firsts)}")

    # ── ANALYSIS ──────────────────────────────────────────────────
    synthesis_active = False
    if SYNTHESIS_AVAILABLE and historical_games and not legacy:
        try:
            if not player_id:
                from config import MY_GAME_NAME, MY_TAG_LINE
                player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"

            # Run all 7 engines on full history
            death_output = run_death_engine(games=historical_games, player_id=player_id)
            economy_output = run_economy_engine(games=historical_games, player_id=player_id)
            combat_output = run_combat_engine(games=historical_games, player_id=player_id)
            durability_output = run_durability_engine(games=historical_games, player_id=player_id)
            vision_output = run_vision_engine(games=historical_games, player_id=player_id)
            objective_output = run_objective_engine(games=historical_games, player_id=player_id)
            draft_output = run_draft_engine(games=historical_games, player_id=player_id)

            if death_output:
                # Load player model
                player_model = get_or_create_player_model(player_id, historical_games)

                # Run SimilarityEngine once for full history
                similarity_output = None
                cluster_membership = {}
                try:
                    sim_engine = SimilarityEngine()
                    sim_result = sim_engine.analyze(historical_games)
                    if sim_result and sim_result.fingerprints:
                        similarity_output = sim_result
                        cluster_result = sim_engine.cluster()
                        if cluster_result and cluster_result.clusters:
                            for cluster in cluster_result.clusters:
                                for fp in cluster.games:
                                    cluster_membership[fp.match_id] = cluster.cluster_id
                        # Phase 2: discover co-occurring patterns
                        try:
                            sim_engine.discover_patterns()
                        except Exception:
                            pass  # best-effort
                except Exception as e:
                    pass  # SimilarityEngine is best-effort; don't block verdict

                engines = MultiEngineOutput(
                    death=death_output, economy=economy_output, combat=combat_output,
                    durability=durability_output, vision=vision_output,
                    objective=objective_output, draft=draft_output,
                )
                synthesis = SynthesisLayer(player_model,
                                          similarity_output=similarity_output,
                                          cluster_membership=cluster_membership)
                verdict = synthesis.analyze_single_game(game, engines)

                if verdict:
                    print_synthesis_block(verdict)
                    synthesis_active = True
        except Exception as e:
            print(f"\n  [Synthesis engine error: {e}]")
            print("  Falling back to legacy analysis...")

    if not synthesis_active:
        # ── WHAT HAPPENED (Legacy) ────────────────────────────────
        findings = diagnose_game(game, historical_games=historical_games)

        if findings:
            print(f"\n  ── WHAT HAPPENED {'─'*45}")
            level_order = {"CRITICAL": 0, "CLEAR": 1, "NOTABLE": 2, "POSITIVE": 3}
            findings.sort(key=lambda f: level_order.get(f["level"], 4))

            for f in findings:
                level = f["level"]
                if level == "POSITIVE":
                    badge = "[+]"
                elif level == "CRITICAL":
                    badge = "[CRITICAL]"
                elif level == "CLEAR":
                    badge = "[CLEAR]"
                else:
                    badge = "[NOTABLE]"
                # Wrap text at 70 chars
                text = f["text"]
                print(f"  {badge} {text}")

        # ── VERDICT ───────────────────────────────────────────────
        verdict = generate_verdict(game, findings)
        print(f"\n  ── VERDICT {'─'*51}")
        # Word wrap verdict at ~70 chars
        words = verdict.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 72:
                print(line)
                line = "  " + word
            else:
                line = line + " " + word if line.strip() else "  " + word
        if line.strip():
            print(line)

    # ── TEAM BREAKDOWN ────────────────────────────────────────────
    print_team_breakdown(game)

    print(f"  {'═'*62}")

# ─────────────────────────────────────────────
# COMPACT GAME OUTPUT (for facecheck games)
# ─────────────────────────────────────────────

def print_compact_game(game, game_number, historical_games=None):
    win = game["win"]
    result = "WIN" if win else "LOSS"
    enemy = game.get("enemy", {})
    findings = diagnose_game(game, historical_games=historical_games)
    critical = [f for f in findings if f["level"] == "CRITICAL"]
    positives = [f for f in findings if f["level"] == "POSITIVE"]

    kda = f"{game['kills']}/{game['deaths']}/{game['assists']}"
    build_str = " → ".join(game.get("build_order", [])[:3])
    if len(game.get("build_order", [])) > 3:
        build_str += " ..."

    print(f"\n  ┌─ [{game_number}] {game['queue']} — {game['champion']} — {game['duration_min']}m — {result}")
    print(f"  │  {kda}  |  CS: {game['cs_final']} ({game.get('cs_per_min', 0)}/min)  |  Dmg: {fmt_k(game['damage'])}  |  Vision: {game['vision']}  |  Gold: {fmt_k(game['gold'])}")
    if build_str:
        print(f"  │  Build: {build_str}")
    if enemy:
        enemy_kda = f"{enemy['kills']}/{enemy['deaths']}/{enemy['assists']}"
        cs_diff = game['cs_final'] - enemy.get('cs', 0)
        print(f"  │  Enemy: {enemy['champion']}  {enemy_kda}  |  CS: {enemy.get('cs', 0)} ({fmt_num(cs_diff, plus=True)})")

    if critical:
        for f in critical[:2]:
            print(f"  │  [CRITICAL] {f['text'][:80]}")
    elif not win and not positives:
        print(f"  │  No dominant loss factors identified.")

    if positives:
        for f in positives[:1]:
            print(f"  │  [+] {f['text'][:80]}")

    verdict = generate_verdict(game, findings)
    # One line verdict
    verdict_short = verdict[:100] + "..." if len(verdict) > 100 else verdict
    print(f"  └─ {verdict_short}")

# ─────────────────────────────────────────────
# AGGREGATE WORST / BEST
# ─────────────────────────────────────────────

def print_worst(games, champion=None):
    from facecheck_analysis import run_analysis, split_by_result, robust_avg, winrate
    from collections import defaultdict

    label = f"FACECHECK WORST — {champion}" if champion else "FACECHECK WORST"
    wins, losses = split_by_result(games)
    wr = round(len(wins) / len(games) * 100, 1) if games else 0

    print(f"\n  {'='*60}")
    print(f"  {label}")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    print(f"  {'='*60}")
    print(f"\n  Here is what is costing you games. No softening.\n")

    # Run full analysis to get findings
    findings = run_analysis(games)
    critical = [f for f in findings if f["confidence_label"] == "CRITICAL"]
    clear = [f for f in findings if f["confidence_label"] == "CLEAR"]

    # Worst items
    first_item_games = defaultdict(list)
    for g in games:
        if g.get("first_item"):
            first_item_games[g["first_item"]].append(g)

    worst_items = []
    for item, ig in first_item_games.items():
        if len(ig) >= 3:
            wr_item = winrate(ig)
            if wr_item is not None and wr_item < 45:
                worst_items.append((item, wr_item, len(ig)))
    worst_items.sort(key=lambda x: x[1])

    # Worst champions
    from collections import defaultdict as dd
    champ_games = dd(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    worst_champs = []
    for champ, cg in champ_games.items():
        if len(cg) >= 5:
            wr_c = winrate(cg)
            if wr_c is not None and wr_c < 45:
                worst_champs.append((champ, wr_c, len(cg)))
    worst_champs.sort(key=lambda x: x[1])

    if worst_items:
        print(f"  ── STOP BUILDING THESE ──────────────────────────────────────")
        for item, wr_item, n in worst_items:
            print(f"  {item}: {wr_item}% winrate across {n} games. This item is actively costing you.")
        print()

    if worst_champs and not champion:
        print(f"  ── STOP PLAYING THESE ───────────────────────────────────────")
        for champ, wr_c, n in worst_champs:
            print(f"  {champ}: {wr_c}% winrate across {n} games. The data does not support this pick.")
        print()

    print(f"  ── YOUR WORST PATTERNS ──────────────────────────────────────")
    shown = 0
    for f in critical + clear:
        if shown >= 6:
            break
        ftype = f["type"]
        data = f["data"]

        if ftype == "first_item_underperform":
            print(f"  {data['item']} first: {data['winrate']}% across {data['games']} games. Change it.")
        elif ftype.startswith("delta_") and f["data"].get("direction") == "lower":
            print(f"  {data['metric']}: {data['loss_avg']} in losses vs {data['win_avg']} in wins. You die more when you lose.")
        elif ftype.startswith("delta_"):
            print(f"  {data['metric']}: {data['win_avg']} in wins vs {data['loss_avg']} in losses. Gap: {data['delta']}.")
        elif ftype == "short_loss_pattern":
            print(f"  {data['pct']}% of losses end before 22 minutes. You are getting stomped early, repeatedly.")
        elif ftype == "cs15_gap":
            print(f"  CS at 15min: {data['loss_avg']} in losses vs {data['win_avg']} in wins. You fall behind early and stay there.")
        elif ftype == "pattern_invaded_early":
            print(f"  Invaded pattern in {data['pct']}% of losses. Pathing and ward coverage before second buff.")
        elif ftype == "pattern_won_jungle_lost_game":
            print(f"  Won jungle, lost game in {data['pct']}% of losses. Average {data['avg_deaths']} deaths. Stop fighting when ahead.")
        elif ftype == "cs_differential":
            print(f"  CS vs enemy: {round(data['win_avg_diff']):+} in wins, {round(data['loss_avg_diff']):+} in losses. The farm race determines the result.")
        elif ftype == "damage_differential":
            print(f"  Damage vs enemy: {round(data['win_avg_diff']):+} in wins, {round(data['loss_avg_diff']):+} in losses.")
        else:
            continue
        shown += 1

    print(f"\n  ── BOTTOM LINE ──────────────────────────────────────────────")
    bottom_lines = []

    if worst_items:
        bottom_lines.append(f"  Build: {worst_items[0][0]} at {worst_items[0][1]}% WR. This is a known losing start. Change it first.")
    if worst_champs and not champion:
        bottom_lines.append(f"  Champion: {worst_champs[0][0]} at {worst_champs[0][1]}% WR across {worst_champs[0][2]} games. The data does not support this pick.")
    if critical:
        top = critical[0]
        ftype = top["type"].lower()
        title = top.get("title", "").lower()
        data = top.get("data", {})
        if "cs" in ftype or "farm" in title:
            bottom_lines.append(f"  Farm: Losing the CS race is your most consistent loss condition. Win the 1v1 in farm.")
        elif "invaded" in ftype or "early" in ftype:
            bottom_lines.append(f"  Early game: You are losing before mid-game starts in too many games. One ward on your second buff entrance.")
        elif "death" in ftype:
            bottom_lines.append(f"  Deaths: You die too much. Every death is gold and tempo handed to the enemy.")
        elif "vision" in ftype or "no_vision" in ftype:
            bottom_lines.append(f"  Vision: 0 control wards in losses is a pattern. Two per game changes your dragon control.")
        elif "ahead_threw" in ftype:
            bottom_lines.append(f"  Decision making: You earn leads and lose them. Convert leads into objectives, not more fights.")
        elif "team_feed" in ftype:
            bottom_lines.append(f"  Team dependency: {data.get('pct', '')}% of losses your CS was fine but your team collapsed. Recognize these early and tilt-manage.")
        else:
            bottom_lines.append(f"  Primary issue: {top.get('title', 'See patterns above')}. Address this before anything else.")

    if not bottom_lines:
        # Guaranteed fallback — summarize WR with actionable
        wr_val = round(len(wins) / len(games) * 100, 1) if games else 0
        if wr_val < 45:
            bottom_lines.append(f"  At {wr_val}% WR the data needs more games to surface clear patterns. Keep playing and re-run.")
        else:
            bottom_lines.append(f"  No dominant weakness found at {wr_val}% WR. Focus on consistency — the small edges compound.")

    for line in bottom_lines:
        print(line)
    print()

def print_best(games, champion=None):
    from facecheck_analysis import run_analysis, split_by_result, winrate
    from collections import defaultdict

    label = f"FACECHECK BEST — {champion}" if champion else "FACECHECK BEST"
    wins, losses = split_by_result(games)
    wr = round(len(wins) / len(games) * 100, 1) if games else 0

    print(f"\n  {'='*60}")
    print(f"  {label}")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    print(f"  {'='*60}")
    print(f"\n  Here is what is working for you. Keep doing this.\n")

    # Best items
    first_item_games = defaultdict(list)
    for g in games:
        if g.get("first_item"):
            first_item_games[g["first_item"]].append(g)

    best_items = []
    for item, ig in first_item_games.items():
        if len(ig) >= 3:
            wr_item = winrate(ig)
            if wr_item is not None and wr_item >= 55:
                best_items.append((item, wr_item, len(ig)))
    best_items.sort(key=lambda x: x[1], reverse=True)

    # Best champions
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    best_champs = []
    for champ, cg in champ_games.items():
        if len(cg) >= 5:
            wr_c = winrate(cg)
            if wr_c is not None and wr_c >= 55:
                best_champs.append((champ, wr_c, len(cg)))
    best_champs.sort(key=lambda x: x[1], reverse=True)

    if best_items:
        print(f"  ── KEEP BUILDING THESE ──────────────────────────────────────")
        for item, wr_item, n in best_items:
            print(f"  {item}: {wr_item}% winrate across {n} games. This is a winning pattern.")
        print()

    if best_champs and not champion:
        print(f"  ── KEEP PLAYING THESE ───────────────────────────────────────")
        for champ, wr_c, n in best_champs:
            print(f"  {champ}: {wr_c}% winrate across {n} games. This champion works for you.")
        print()

    # Win game patterns
    findings = run_analysis(games)
    print(f"  ── WHAT YOUR WINNING GAMES HAVE IN COMMON ───────────────────")

    win_patterns = []
    for f in findings:
        ftype = f["type"]
        data = f["data"]
        if ftype.startswith("delta_") and data.get("direction") == "higher":
            win_patterns.append(f"  Higher {data['metric']} in every win. Wins avg: {data['win_avg']}. Keep pushing this.")
        elif ftype == "pattern_won_jungle_lost_game":
            win_patterns.append(f"  When you win the farm battle, you win the game. Farm is your win condition.")
        elif ftype == "cs_differential":
            win_patterns.append(f"  +{round(data['win_avg_diff'])} CS vs enemy jungler in wins. The farm battle is the game.")
        elif ftype == "pattern_dragon_control":
            win_patterns.append(f"  Dragon control correlates with wins. Your team wins when it controls drakes.")

    for p in win_patterns[:5]:
        print(p)

    print(f"\n  ── BOTTOM LINE ──────────────────────────────────────────────")
    if best_items:
        print(f"  Build: {best_items[0][0]} at {best_items[0][1]}% WR. This is your winning item. Do not deviate.")
    if best_champs:
        print(f"  Champion: {best_champs[0][0]} at {best_champs[0][1]}% WR. When you want to climb, play this.")
    if win_patterns:
        print(f"  Pattern: Your wins are built on farm advantage and map control. Protect the early game.")
    print()

# ─────────────────────────────────────────────
# POOL REPORT
# ─────────────────────────────────────────────

def print_pool(games, min_games=3):
    from collections import defaultdict
    from facecheck_analysis import winrate

    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)

    rows = []
    for champ, cg in champ_games.items():
        if len(cg) < min_games:
            continue
        wr = winrate(cg)
        if wr is None:
            continue
        recent = cg[:5]
        recent_wr = winrate(recent)
        if recent_wr is None or len(recent) < 3:
            trend = "→"
        elif recent_wr >= wr + 10:
            trend = "↑"
        elif recent_wr <= wr - 10:
            trend = "↓"
        else:
            trend = "→"

        if len(cg) < 3:
            verdict = "UNSTABLE"
        elif wr >= 58 and trend != "↓":
            verdict = "PLAY"
        elif wr >= 58 and trend == "↓":
            verdict = "PLAY (DECLINING)"
        elif wr >= 50 and len(cg) >= 10:
            verdict = "SOLID"
        elif wr >= 50 and len(cg) < 10:
            verdict = "PLAY (LOW SAMPLE)"
        elif wr < 50 and trend == "↑" and len(cg) >= 10:
            verdict = "CONDITIONAL"
        elif wr < 50 and trend == "↑" and len(cg) < 10:
            verdict = "UNSTABLE"
        elif wr < 45:
            verdict = "AVOID"
        else:
            verdict = "INCONSISTENT"

        rows.append((champ, len(cg), wr, trend, verdict))

    rows.sort(key=lambda x: x[2], reverse=True)

    wins_total = sum(1 for g in games if g["win"])
    print(f"\n  {'='*60}")
    print(f"  FACECHECK POOL")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {wins_total}W {len(games)-wins_total}L  |  {round(wins_total/len(games)*100,1)}% WR")
    print(f"  Showing champions with {min_games}+ games")
    print(f"  {'='*60}\n")

    if not rows:
        print(f"  Not enough data. Play more games on each champion.")
        return

    print(f"  {'Champion':<20} {'Games':>6}  {'WR':>6}  {'Trend':>6}  Verdict")
    print(f"  {'─'*58}")
    for champ, n, wr, trend, verdict in rows:
        print(f"  {champ:<20} {n:>6}  {wr:>5}%  {trend:>6}  {verdict}")

    print(f"\n  {'─'*58}")
    play_these = [r for r in rows if r[4] == "PLAY"]
    conditional_these = [r for r in rows if r[4] == "CONDITIONAL"]
    avoid_these = [r for r in rows if r[4] == "AVOID"]
    if play_these:
        best = play_these[0]
        print(f"  Climb pick: {best[0]} — {best[2]}% WR across {best[1]} games.")
    if conditional_these:
        c = conditional_these[0]
        print(f"  CONDITIONAL: {c[0]} — Trending up but hasn't crossed 50%. Play in low-stakes games while the trend holds.")
    if avoid_these:
        worst = avoid_these[-1]
        print(f"  Bench:      {worst[0]} — {worst[2]}% WR. The data does not support this pick.")
    print()

# ─────────────────────────────────────────────
# SELECT INTERFACE
# ─────────────────────────────────────────────

def run_select(cache, champion=None, result_filter=None):
    games = get_ranked_games(cache, champion=champion)
    if not games:
        print("No ranked games found." + (f" for {champion}" if champion else ""))
        return

    if result_filter == "wins":
        games = [g for g in games if g["win"]]
    elif result_filter == "losses":
        games = [g for g in games if not g["win"]]

    if not games:
        filter_label = f"{champion} " if champion else ""
        print(f"No {filter_label}{result_filter} found.")
        return

    page_size = 10
    page = 0
    total_pages = (len(games) - 1) // page_size + 1

    title_parts = []
    if champion:
        title_parts.append(champion)
    if result_filter:
        title_parts.append(result_filter.capitalize())
    title_suffix = f" — {' '.join(title_parts)}" if title_parts else ""

    while True:
        start = page * page_size
        end = min(start + page_size, len(games))
        page_games = games[start:end]

        print(f"\n  FaceCheck Select{title_suffix}  |  Page {page + 1}/{total_pages}  |  {len(games)} games")
        print(f"  {'─'*70}")
        print(f"  {'#':<5} {'Queue':<20} {'Champion':<14} {'Result':<6} {'Duration':<10} {'KDA'}")
        print(f"  {'─'*70}")

        for i, g in enumerate(page_games):
            num = start + i + 1
            kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
            result = "WIN" if g["win"] else "LOSS"
            print(f"  {num:<5} {g['queue']:<20} {g['champion']:<14} {result:<6} {g['duration_min']}m{'':<5} {kda}")

        print(f"\n  Enter game number, [n]ext page, [p]rev page, or [q]uit:")
        try:
            inp = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if inp == "q":
            break
        elif inp == "n":
            if page < total_pages - 1:
                page += 1
            else:
                print("  Already on last page.")
        elif inp == "p":
            if page > 0:
                page -= 1
            else:
                print("  Already on first page.")
        elif inp.isdigit():
            idx = int(inp) - 1
            if 0 <= idx < len(games):
                historical = get_ranked_games(cache)
                print_full_game(games[idx], game_number=idx + 1, historical_games=historical, cache=cache)
            else:
                print(f"  Invalid number. Enter 1-{len(games)}.")
        else:
            print("  Invalid input.")

# ─────────────────────────────────────────────
# MATCHUPS DEEP DIVE
# ─────────────────────────────────────────────

def print_matchups(games, champion=None):
    from collections import defaultdict

    label = f"FACECHECK MATCHUPS — {champion}" if champion else "FACECHECK MATCHUPS"
    games_e = [g for g in games if g.get("enemy")]
    wins_total = [g for g in games if g["win"]]
    losses_total = [g for g in games if not g["win"]]
    wr_overall = round(len(wins_total) / len(games) * 100, 1) if games else 0

    print(f"\n  {'='*62}")
    print(f"  {label}")
    print(f"  {'='*62}")
    print(f"  {len(games)} games  |  {len(wins_total)}W {len(losses_total)}L  |  {wr_overall}% WR")
    role_label = enemy_role_label(games)
    enemy_label = f"enemy {role_label}"
    print(f"  {len(games_e)} games with {enemy_label} data")
    print(f"  {'='*62}")

    if not games_e:
        print("  No enemy matchup data found.")
        return

    # Build per-enemy-champion profile
    enemy_profiles = defaultdict(lambda: {
        "games": [],
        "wins": [],
        "losses": [],
        "cs_diff": [],
        "damage_diff": [],
        "kill_diff": [],
        "gold_diff": [],
        "early_death_games": [],
        "killed_by": [],
    })

    for g in games_e:
        e = g["enemy"]
        ec = e["champion"]
        p = enemy_profiles[ec]
        p["games"].append(g)

        cs_diff = g.get("cs_final", 0) - e.get("cs", 0)
        dmg_diff = g.get("damage", 0) - e.get("damage", 0)
        kill_diff = g.get("kills", 0) - e.get("kills", 0)
        gold_diff = g.get("gold", 0) - e.get("gold", 0)

        p["cs_diff"].append(cs_diff)
        p["damage_diff"].append(dmg_diff)
        p["kill_diff"].append(kill_diff)
        p["gold_diff"].append(gold_diff)
        p["killed_by"].append(g.get("killed_by_enemy_jungler", 0))

        if g["win"]:
            p["wins"].append(g)
        else:
            p["losses"].append(g)
            if g.get("early_deaths", 0) >= 2:
                p["early_death_games"].append(g)

    # Filter to meaningful sample sizes
    qualified = {
        ec: p for ec, p in enemy_profiles.items()
        if len(p["games"]) >= 3
    }
    small_sample = {
        ec: p for ec, p in enemy_profiles.items()
        if len(p["games"]) < 3
    }

    if not qualified and not small_sample:
        print("  Not enough games to build matchup profiles.")
        return

    # Build summary rows
    def avg(lst):
        lst = [v for v in lst if v is not None]
        return round(sum(lst) / len(lst), 1) if lst else 0

    def wr_pct(p):
        total = len(p["games"])
        return round(len(p["wins"]) / total * 100, 1) if total > 0 else 0

    profiles = []
    for ec, p in qualified.items():
        profiles.append({
            "champion": ec,
            "games": len(p["games"]),
            "wins": len(p["wins"]),
            "losses": len(p["losses"]),
            "wr": wr_pct(p),
            "avg_cs_diff": avg(p["cs_diff"]),
            "avg_dmg_diff": avg(p["damage_diff"]),
            "avg_kill_diff": avg(p["kill_diff"]),
            "avg_gold_diff": avg(p["gold_diff"]),
            "avg_killed_by": avg(p["killed_by"]),
            "early_death_losses": len(p["early_death_games"]),
            "raw": p,
        })

    profiles.sort(key=lambda x: x["wr"])

    worst = [p for p in profiles if p["wr"] <= 35]
    tough  = [p for p in profiles if 35 < p["wr"] <= 49]
    even   = [p for p in profiles if 49 < p["wr"] <= 59]
    favorable = [p for p in profiles if p["wr"] > 59]

    # ── LOSING MATCHUPS ───────────────────────────────────────────
    if worst or tough:
        print(f"\n  ── LOSING MATCHUPS {'─'*44}")
        print()

        for p in worst + tough:
            ec = p["champion"]
            tier = "BAD" if p["wr"] <= 35 else "TOUGH"
            wins_n = p["wins"]
            losses_n = p["losses"]
            games_n = p["games"]
            wr = p["wr"]
            cs = p["avg_cs_diff"]
            dmg = p["avg_dmg_diff"]
            kills = p["avg_kill_diff"]
            gold = p["avg_gold_diff"]
            killed_by = p["avg_killed_by"]
            early_d = p["early_death_losses"]

            print(f"  ┌─ {ec}  [{tier}]  {wins_n}W {losses_n}L  ({wr}%)")
            print(f"  │  CS:     {cs:+.0f}  avg vs {ec}")
            print(f"  │  Damage: {dmg:+,.0f}  avg vs {ec}")
            print(f"  │  Kills:  {kills:+.1f}  avg vs {ec}")
            print(f"  │  Gold:   {gold:+,.0f}  avg vs {ec}")
            if killed_by >= 1:
                print(f"  │  Killed by them: {killed_by:.1f}x per game on average")
            if early_d >= 2:
                print(f"  │  Early death losses: {early_d} of {losses_n} losses had 2+ deaths pre-15min")

            # Interpretation
            if cs > 0 and wr <= 40:
                note = f"  You are farming ahead of {ec} but still losing. This is a fight problem, not a farm problem."
            elif cs < -20:
                note = f"  {ec} is out-farming you consistently. The resource gap is the primary driver."
            elif killed_by >= 1.5:
                note = f"  {ec} is finding and killing you repeatedly. Pathing and positioning adjustment needed."
            elif dmg < -3000:
                note = f"  {ec} out-threatens you in combat. Every skirmish goes their way."
            elif early_d >= losses_n * 0.5:
                note = f"  More than half your losses to {ec} involve early deaths. They are setting the tempo before 15 minutes."
            else:
                note = f"  Losing record against {ec}. Review specific games with: facecheck select"

            print(f"  │  {note}")
            print(f"  └{'─'*63}")
            print()

    # ── EVEN MATCHUPS ─────────────────────────────────────────────
    if even:
        print(f"  ── EVEN MATCHUPS {'─'*46}")
        print()
        for p in even:
            ec = p["champion"]
            cs = p["avg_cs_diff"]
            print(f"  {ec:<18} {p['wins']}W {p['losses']}L  ({p['wr']}%)   CS: {cs:+.0f}  Dmg: {p['avg_dmg_diff']:+,.0f}  Kills: {p['avg_kill_diff']:+.1f}")
        print()

    # ── WINNING MATCHUPS ──────────────────────────────────────────
    if favorable:
        print(f"  ── WINNING MATCHUPS {'─'*43}")
        print()

        for p in sorted(favorable, key=lambda x: x["wr"], reverse=True):
            ec = p["champion"]
            wins_n = p["wins"]
            losses_n = p["losses"]
            games_n = p["games"]
            wr = p["wr"]
            cs = p["avg_cs_diff"]
            dmg = p["avg_dmg_diff"]
            kills = p["avg_kill_diff"]

            print(f"  ┌─ {ec}  [FAVORED]  {wins_n}W {losses_n}L  ({wr}%)")
            print(f"  │  CS: {cs:+.0f}  |  Damage: {dmg:+,.0f}  |  Kills: {kills:+.1f}")

            if cs > 30 and dmg > 2000:
                note = f"  You dominate {ec} in both farm and combat. This is your blueprint."
            elif cs > 20:
                note = f"  Farm advantage against {ec} is consistent. You control the resource race."
            elif kills > 2:
                note = f"  You win the individual duels against {ec}. Convert those kills into objectives."
            else:
                note = f"  Winning record against {ec}. The matchup suits your style."

            print(f"  │  {note}")
            if INTEL_AVAILABLE:
                ec_intel = load_champion_intel(ec)
                if ec_intel:
                    sig = ec_intel.get("signals", {})
                    km  = sig.get("key_mechanic", "")
                    tw  = sig.get("threat_window", "")
                    if km:
                        print(f"  │  Intel: {km}")
            print(f"  └{'─'*63}")
            print()

    # ── SMALL SAMPLE ──────────────────────────────────────────────
    if small_sample:
        small_list = sorted(small_sample.items(), key=lambda x: len(x[1]["games"]), reverse=True)
        print(f"  ── LIMITED DATA (1-2 games) {'─'*35}")
        print()
        for ec, p in small_list[:8]:
            g_count = len(p["games"])
            w_count = len(p["wins"])
            l_count = len(p["losses"])
            print(f"  {ec:<18} {w_count}W {l_count}L  ({g_count} game{'s' if g_count > 1 else ''} — not enough to conclude)")
        print()

    # ── OVERALL MATCHUP SUMMARY ───────────────────────────────────
    print(f"  ── MATCHUP SUMMARY {'─'*44}")
    print()

    total_qualified = len(profiles)
    n_bad = len(worst)
    n_tough = len(tough)
    n_even = len(even)
    n_fav = len(favorable)

    if total_qualified:
        print(f"  {total_qualified} champions with 3+ games:")
        print(f"  Losing  ({n_bad + n_tough}) — Tough/Bad matchups to study")
        print(f"  Even    ({n_even}) — Coin flip matchups")
        print(f"  Winning ({n_fav}) — Seek these out")
        print()

    # Key insight
    if worst:
        hardest = worst[0]
        print(f"  Hardest matchup:  {hardest['champion']} — {hardest['wr']}% WR across {hardest['games']} games")
    if favorable:
        easiest = sorted(favorable, key=lambda x: x["wr"], reverse=True)[0]
        print(f"  Easiest matchup:  {easiest['champion']} — {easiest['wr']}% WR across {easiest['games']} games")

    # Pattern detection across all losing matchups
    if worst:
        positive_cs_losses = [p for p in worst if p["avg_cs_diff"] > 0]
        if len(positive_cs_losses) >= 2:
            champs = ", ".join(p["champion"] for p in positive_cs_losses)
            print(f"\n  Pattern detected: You average positive CS against {champs} but still lose.")
            print(f"  These are fight-loss matchups. The farm is not the issue — the combat outcome is.")

        high_kill_by = [p for p in worst if p["avg_killed_by"] >= 1.5]
        if high_kill_by:
            champs = ", ".join(p["champion"] for p in high_kill_by)
            print(f"\n  Pattern detected: {champs} are actively hunting and killing you.")
            print(f"  These champions are likely running you down in your own jungle. Ward the river and your second buff.")

    print()


def print_guide():
    """Print the FaceCheck workflow guide."""
    print(f"\n  {'='*60}")
    print(f"  FACECHECK GUIDE")
    print(f"  {'='*60}\n")

    print(f"  AFTER A LOSS")
    print(f"  ─────────────")
    print(f"  Run: face lastgame")
    print(f"  Check the VERDICT section — it names the primary loss factor.")
    print(f"  If the loss was unwinnable (team feed pattern), note it and move on.")
    print(f"  If it was your early game, run: face Viego (or your champion)")
    print(f"  Look for the CS@15 gap and early death patterns. Fix those first.\n")

    print(f"  BEFORE QUEUING")
    print(f"  ───────────────")
    print(f"  Run: face pool")
    print(f"  Play your PLAY verdict champions. Avoid AVOID.")
    print(f"  If CONDITIONAL appears, play only in low-stakes games while trending up.")
    print(f"  Run: face matchups to see your hardest enemy champions.")
    print(f"  If you see one of your losing matchups, dodge or adjust your approach.\n")

    print(f"  IMPROVING A CHAMPION")
    print(f"  ─────────────────────")
    print(f"  Run: face Viego (or champion name)")
    print(f"  Look for CRITICAL findings — these are your known losing patterns.")
    print(f"  Run: face Viego worst for the blunt summary of what to stop doing.")
    print(f"  Run: face Viego best for what to keep doing.")
    print(f"  Compare the two to identify your personal improvement edges.\n")

    print(f"  SCOUTING AN OPPONENT")
    print(f"  ─────────────────────")
    print(f"  Run: face scout Name#TAG")
    print(f"  Check their pool health and recent trends.")
    print(f"  If they are on a declining trend, exploit the tilt.")
    print(f"  If they have strong matchups against your pick, reconsider or adjust playstyle.\n")

    print(f"  UNDERSTANDING A CHAMPION")
    print(f"  ─────────────────────────")
    print(f"  Run: face counter [champion]")
    print(f"  Shows what beats them, what they have, and what items counter them.")
    print(f"  Run: face intel [champion]")
    print(f"  Full kit breakdown, threat window, and your personal matchup data if available.\n")

    print(f"  MANAGING YOUR CACHE")
    print(f"  ────────────────────")
    print(f"  Run: face fetch 50")
    print(f"  Pulls latest ranked games. Do this after every session.")
    print(f"  Run: face fetch 50 --force")
    print(f"  Rebuilds entire cache. Use if you suspect data corruption.")
    print(f"  Run: face clean")
    print(f"  Removes duplicates after force fetch. Safe to run anytime.\n")

    print(f"  {'='*60}")
    print()


def print_bans(games):
    """
    Counter pool tracker — Shows which enemy champions to ban based on actual loss rates.
    Output format: "Ban Warwick (67% loss), not Viego (45% loss)"
    """
    from collections import defaultdict

    # Filter to games with enemy data
    games_e = [g for g in games if g.get("enemy")]

    if not games_e:
        print("\n  No enemy matchup data found.")
        return

    # Build per-enemy-champion stats
    enemy_stats = defaultdict(lambda: {"games": 0, "losses": 0, "wins": 0})

    for g in games_e:
        e = g["enemy"]
        ec = e["champion"]
        enemy_stats[ec]["games"] += 1
        if g["win"]:
            enemy_stats[ec]["wins"] += 1
        else:
            enemy_stats[ec]["losses"] += 1

    # Calculate loss rates and filter to meaningful sample (3+ games)
    ban_profiles = []
    for ec, stats in enemy_stats.items():
        games = stats["games"]
        if games >= 3:
            loss_rate = round(stats["losses"] / games * 100, 1)
            ban_profiles.append({
                "champion": ec,
                "games": games,
                "losses": stats["losses"],
                "wins": stats["wins"],
                "loss_rate": loss_rate,
            })

    if not ban_profiles:
        print("\n  Not enough games to build ban recommendations (need 3+ games vs same champion).")
        print(f"  You have {len(games_e)} games with enemy data but no champion repeats 3+ times.")
        return

    # Sort by loss rate (highest first)
    ban_profiles.sort(key=lambda x: (-x["loss_rate"], -x["games"]))

    # Header
    total_losses = sum(1 for g in games_e if not g["win"])
    print(f"\n  {'='*70}")
    print(f"  FACECHECK BANS — Counter Pool Tracker")
    print(f"  {'='*70}")
    print(f"  {len(games_e)} games with enemy data  |  {total_losses} total losses analyzed")
    print(f"  {'='*70}\n")

    # Categorize by loss rate
    high_ban = [p for p in ban_profiles if p["loss_rate"] >= 60]   # 60%+ loss = ban immediately
    medium_ban = [p for p in ban_profiles if 50 <= p["loss_rate"] < 60]  # 50-59% = consider
    low_ban = [p for p in ban_profiles if p["loss_rate"] < 50]  # <50% = don't ban

    # ── HIGH PRIORITY BANS (60%+ loss rate) ──────────────────────────
    if high_ban:
        print(f"  BAN THESE (60%+ loss rate)")
        print(f"  {'─'*70}")
        for p in high_ban:
            ec = p["champion"]
            losses = p["losses"]
            games = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games}G  ({lr}% loss)")
        print()

    # ── MEDIUM PRIORITY (50-59% loss rate) ───────────────────────────
    if medium_ban:
        print(f"  CONSIDER BANNING (50-59% loss rate)")
        print(f"  {'─'*70}")
        for p in medium_ban:
            ec = p["champion"]
            losses = p["losses"]
            games = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games}G  ({lr}% loss)")
        print()

    # ── DON'T BAN (<50% loss rate) ───────────────────────────────────
    if low_ban:
        print(f"  DON'T BAN — You beat these (<50% loss rate)")
        print(f"  {'─'*70}")
        for p in low_ban[:5]:  # Show top 5
            ec = p["champion"]
            losses = p["losses"]
            games = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games}G  ({lr}% loss)")
        print()

    # ── SUMMARY RECOMMENDATION ─────────────────────────────────────────
    print(f"  {'─'*70}")
    print(f"  BAN PRIORITY SUMMARY")
    print(f"  {'─'*70}")

    if high_ban:
        top3 = high_ban[:3]
        names = [p["champion"] for p in top3]
        rates = [f"{p['loss_rate']}%" for p in top3]
        print(f"  Ban: {', '.join(names[:3])}")
        print(f"  Loss rates: {', '.join(rates[:3])}")
        if len(high_ban) > 3:
            print(f"  ({len(high_ban) - 3} more high-loss champions — run 'face matchups' for full list)")
    elif medium_ban:
        top = medium_ban[0]
        print(f"  No 60%+ loss champions found. Consider: {top['champion']} ({top['loss_rate']}% loss)")
    else:
        print(f"  No problematic matchups found. You're winning against everyone in your pool.")

    print(f"\n  {'='*70}")
    print()


def print_heatmap(games):
    """
    Time-of-game heatmap — Shows when you die most during matches.
    Output: "You die 3x more in minutes 10-15"
    """
    # Collect all death minutes from games that have this data
    all_deaths = []
    games_with_data = 0

    for g in games:
        death_mins = g.get("death_minutes", [])
        if death_mins:
            all_deaths.extend(death_mins)
            games_with_data += 1

    if not all_deaths:
        print("\n  No death timeline data found.")
        print("  This feature requires games fetched with the latest update.")
        print(f"  Found {games_with_data} games with death minute data.")
        return

    # Create 5-minute buckets (0-5, 5-10, 10-15, etc.)
    buckets = {}
    bucket_size = 5
    for dm in all_deaths:
        bucket = (dm // bucket_size) * bucket_size
        buckets[bucket] = buckets.get(bucket, 0) + 1

    if not buckets:
        print("\n  No death data to analyze.")
        return

    # Sort buckets
    sorted_buckets = sorted(buckets.items())
    max_bucket = max(b[0] for b in sorted_buckets)

    # Calculate stats
    total_deaths = len(all_deaths)
    avg_deaths_per_bucket = total_deaths / len(buckets)
    max_deaths = max(buckets.values())
    peak_bucket = max(buckets.items(), key=lambda x: x[1])[0]

    # Find dangerous buckets (2x+ average)
    dangerous = [(b, c) for b, c in sorted_buckets if c >= avg_deaths_per_bucket * 2 and c >= 3]

    # Header
    print(f"\n  {'='*70}")
    print(f"  FACECHECK HEATMAP — Time-of-Game Death Analysis")
    print(f"  {'='*70}")
    print(f"  {total_deaths} total deaths across {games_with_data} games")
    print(f"  {'='*70}\n")

    # Visual bar chart
    print(f"  Death Distribution (5-minute buckets)")
    print(f"  {'─'*70}")

    for bucket, count in sorted_buckets:
        start_min = bucket
        end_min = bucket + bucket_size - 1
        bar_len = min(int(count / max_deaths * 40), 40)  # Scale to 40 chars max
        bar = "█" * bar_len
        pct = round(count / total_deaths * 100, 1)

        # Highlight peak bucket
        marker = " ← PEAK" if bucket == peak_bucket else ""
        print(f"  {start_min:>2}-{end_min:<2} min │{bar:<40} {count:>3} ({pct}%){marker}")

    print(f"  {'─'*70}\n")

    # Key insight
    print(f"  KEY INSIGHTS")
    print(f"  {'─'*70}")
    print(f"  Peak danger zone: Minutes {peak_bucket}-{peak_bucket + bucket_size - 1}")
    print(f"  ({buckets[peak_bucket]} deaths = {round(buckets[peak_bucket]/total_deaths*100, 1)}% of all deaths)")
    print()

    # Multiplier insights
    if dangerous:
        print(f"  HIGH-RISK WINDOWS (2x+ above average):")
        for bucket, count in dangerous:
            multiplier = round(count / avg_deaths_per_bucket, 1)
            start_min = bucket
            end_min = bucket + bucket_size - 1
            print(f"  • Minutes {start_min}-{end_min}: You die {multiplier}x more than average")
    else:
        # Find the highest relative to average
        max_mult = max(c / avg_deaths_per_bucket for _, c in sorted_buckets)
        if max_mult >= 1.5:
            bucket, count = max(sorted_buckets, key=lambda x: x[1])
            mult = round(count / avg_deaths_per_bucket, 1)
            print(f"  Elevated risk: Minutes {bucket}-{bucket+4}")
            print(f"  You die {mult}x more than your average 5-minute window.")
        else:
            print(f"  No clear danger zones — deaths are evenly distributed.")

    print()

    # Pattern analysis
    early_deaths = sum(1 for dm in all_deaths if dm < 15)
    late_deaths = sum(1 for dm in all_deaths if dm >= 30)
    mid_deaths = total_deaths - early_deaths - late_deaths

    print(f"  GAME PHASE BREAKDOWN")
    print(f"  {'─'*70}")
    print(f"  Early (0-14 min):   {early_deaths:>3} deaths ({round(early_deaths/total_deaths*100, 1)}%)")
    print(f"  Mid (15-29 min):    {mid_deaths:>3} deaths ({round(mid_deaths/total_deaths*100, 1)}%)")
    print(f"  Late (30+ min):     {late_deaths:>3} deaths ({round(late_deaths/total_deaths*100, 1)}%)")
    print()

    # Recommendations
    print(f"  RECOMMENDATIONS")
    print(f"  {'─'*70}")
    if early_deaths / total_deaths > 0.4:
        print(f"  • 40%+ of deaths are early. Focus on safer early game pathing.")
    elif late_deaths / total_deaths > 0.4:
        print(f"  • 40%+ of deaths are late. Watch for overextension in late game.")
    else:
        print(f"  • Deaths are spread across phases. Review the peak minutes above.")

    if dangerous:
        first_danger = dangerous[0]
        start = first_danger[0]
        end = start + 4
        print(f"  • Peak risk at {start}-{end} min: Play defensively during this window.")

    print(f"\n  {'='*70}")
    print()


def print_pathing(games):
    """
    Jungle pathing efficiency — Camp clear timing analysis.
    Shows first clear speed and CS progression vs enemy jungler.
    """
    # Filter to jungle games with pathing data
    jungle_games = [g for g in games if g.get("role") == "JUNGLE" and g.get("jungle_pathing")]

    if not jungle_games:
        print("\n  No jungle pathing data found.")
        print("  This feature requires jungle games fetched with the latest update.")
        return

    # Aggregate pathing stats
    first_clears = []
    cs_at_5 = []
    cs_at_10 = []
    cs_at_15 = []

    for g in jungle_games:
        jp = g["jungle_pathing"]
        if jp.get("first_clear_min"):
            first_clears.append(jp["first_clear_min"])
        if jp.get("cs_at_5"):
            cs_at_5.append(jp["cs_at_5"])
        if jp.get("cs_at_10"):
            cs_at_10.append(jp["cs_at_10"])
        if jp.get("cs_at_15"):
            cs_at_15.append(jp["cs_at_15"])

    if not first_clears and not cs_at_5:
        print("\n  Insufficient pathing data for analysis.")
        return

    # Calculate averages
    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0

    avg_first_clear = avg(first_clears)
    avg_cs_5 = avg(cs_at_5)
    avg_cs_10 = avg(cs_at_10)
    avg_cs_15 = avg(cs_at_15)

    # Header
    total_jungle_games = len([g for g in games if g.get("role") == "JUNGLE"])
    print(f"\n  {'='*70}")
    print(f"  FACECHECK PATHING — Jungle Camp Efficiency")
    print(f"  {'='*70}")
    print(f"  {len(jungle_games)} games with pathing data  |  {total_jungle_games} total jungle games")
    print(f"  {'='*70}\n")

    # First clear timing
    if first_clears:
        print(f"  FIRST CLEAR TIMING")
        print(f"  {'─'*70}")
        print(f"  Average first clear complete: {avg_first_clear} minutes")

        # Distribution
        fast = len([x for x in first_clears if x <= 3])
        slow = len([x for x in first_clears if x >= 4])
        print(f"  Fast clears (≤3:00):  {fast} games ({round(fast/len(first_clears)*100, 1)}%)")
        print(f"  Slow clears (≥4:00): {slow} games ({round(slow/len(first_clears)*100, 1)}%)")

        if avg_first_clear <= 3.0:
            print(f"  ✓ Your first clear is efficient. You complete camps quickly.")
        elif avg_first_clear <= 3.5:
            print(f"  → Your first clear is average. Room for optimization.")
        else:
            print(f"  ⚠ Slow first clear detected. You're losing tempo early.")
        print()

    # CS progression benchmarks
    print(f"  CS PROGRESSION BENCHMARKS")
    print(f"  {'─'*70}")
    print(f"  {'Time':<12} {'Your Avg':<12} {'Target':<12} {'Status':<15}")
    print(f"  {'─'*70}")

    # Jungle CS benchmarks (approximate full clear values)
    benchmarks = {
        5: (28, "6 camps"),    # Full clear = ~28 CS
        10: (56, "2 full clears"), # ~56 CS at 10 min
        15: (84, "3 full clears"), # ~84 CS at 15 min
    }

    for time_key, cs_list in [(5, cs_at_5), (10, cs_at_10), (15, cs_at_15)]:
        if cs_list:
            avg_cs = avg(cs_list)
            target, desc = benchmarks.get(time_key, (0, ""))
            diff = avg_cs - target

            if diff >= 5:
                status = "▲ Ahead"
            elif diff >= -5:
                status = "→ On pace"
            else:
                status = "▼ Behind"

            print(f"  @{time_key} min     {avg_cs:<12.0f} {target:<12} {status:<15} ({desc})")

    print()

    # Compare wins vs losses
    wins = [g for g in jungle_games if g["win"]]
    losses = [g for g in jungle_games if not g["win"]]

    if wins and losses:
        win_cs_15 = avg([g["jungle_pathing"]["cs_at_15"] for g in wins if g["jungle_pathing"].get("cs_at_15")])
        loss_cs_15 = avg([g["jungle_pathing"]["cs_at_15"] for g in losses if g["jungle_pathing"].get("cs_at_15")])

        if win_cs_15 and loss_cs_15:
            print(f"  WINS VS LOSSES COMPARISON")
            print(f"  {'─'*70}")
            print(f"  CS@15 in wins:   {win_cs_15:.0f} average")
            print(f"  CS@15 in losses: {loss_cs_15:.0f} average")
            diff = win_cs_15 - loss_cs_15
            if diff > 10:
                print(f"  → You farm {diff:.0f} more CS by 15 min in wins. Early farm matters.")
            elif diff > 0:
                print(f"  → Slight farm advantage in wins (+{diff:.0f} CS).")
            else:
                print(f"  → Farm is similar in wins/losses. Look for other factors.")
            print()

    # Recommendations
    print(f"  RECOMMENDATIONS")
    print(f"  {'─'*70}")

    if avg_first_clear > 3.5:
        print(f"  • Slow first clear: Practice your route in Practice Tool.")
        print(f"  • Aim for 3:15 full clear. Check: kite camps efficiently.")

    if avg_cs_15 < 70:
        print(f"  • Low CS@15: Consider more farm-heavy pathing.")
        print(f"  • Current meta: 6 CS/min minimum for junglers.")

    if avg_cs_15 >= 80:
        print(f"  • Strong farm efficiency. Maintain while adding gank pressure.")

    print(f"  • Compare your clear to pro junglers with 'face scout [pro]#TAG'")
    print(f"\n  {'='*70}")
    print()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from facecheck_data import load_cache

    cache = load_cache()

    if not cache.get("games"):
        print("No cached games found. Run: facecheck-fetch")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: face lastgame | face game N | face games [N] | face pool | face matchups | face counter [champ] | face intel [champ] | face guide | face scout Name#Tag | face worst [champ] | face best [champ]")
        sys.exit(1)

    mode = args[0]
    legacy = "--legacy" in args

    # Parse optional champion, count, and result_filter
    # Join all non-digit args — handles PowerShell splatting single chars
    champion = None
    count = None
    result_filter = None
    champ_parts = []
    digit_parts = []
    for arg in args[1:]:
        if arg == "--legacy":
            continue
        if arg.isdigit():
            digit_parts.append(arg)
        elif arg.lower() in ("wins", "losses"):
            result_filter = arg.lower()
        elif not arg.startswith("--"):
            champ_parts.append(arg)
    # PowerShell char-splits multi-digit numbers (e.g. "10" → ["1","0"]).
    # If all parts are single chars AND all are digits, rejoin them first.
    if digit_parts:
        digit_str = "".join(digit_parts) if all(len(d) == 1 for d in digit_parts) else digit_parts[0]
        count = int(digit_str)
    if champ_parts:
        # If all parts are single chars, PowerShell passed a string as chars — rejoin
        if all(len(p) == 1 for p in champ_parts):
            champion = "".join(champ_parts)
        else:
            champion = " ".join(champ_parts)

    ranked = get_ranked_games(cache, champion=champion)
    historical = get_ranked_games(cache)  # unfiltered for context
    from config import MY_GAME_NAME, MY_TAG_LINE
    player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"

    if mode == "last":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_full_game(ranked[0], game_number=1, historical_games=historical, legacy=legacy, player_id=player_id, cache=cache)

    elif mode == "game":
        n = count or 1
        if n < 1 or n > len(ranked):
            print(f"Game {n} not found. You have {len(ranked)} ranked games cached.")
            sys.exit(1)
        print_full_game(ranked[n - 1], game_number=n, historical_games=historical, legacy=legacy, player_id=player_id, cache=cache)

    elif mode == "games":
        n = count or 5
        games_to_show = ranked[:n]
        if not games_to_show:
            print("No ranked games found.")
            sys.exit(1)
        print(f"\n  FaceCheck — Last {len(games_to_show)} Games{f' ({champion})' if champion else ''}")
        for i, g in enumerate(games_to_show, 1):
            print_compact_game(g, i, historical_games=historical)

    elif mode == "select":
        run_select(cache, champion=champion, result_filter=result_filter)

    elif mode == "worst":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_worst(ranked, champion=champion)

    elif mode == "best":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_best(ranked, champion=champion)

    elif mode == "pool":
        min_g = count or 3
        print_pool(historical, min_games=min_g)

    elif mode == "matchups":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_matchups(ranked, champion=champion)

    elif mode == "counter":
        if not champion:
            print("Usage: facecheck counter [champion]")
            print("Example: facecheck counter Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'league-update' to populate the vault.")
            sys.exit(1)
        print_counter_command(champion, game_history=historical)

    elif mode == "intel":
        if not champion:
            print("Usage: facecheck intel [champion]")
            print("Example: facecheck intel Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'league-update' to populate the vault.")
            sys.exit(1)
        print_intel_profile(champion)

    elif mode == "guide":
        print_guide()

    elif mode == "bans":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_bans(ranked)

    elif mode == "heatmap":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_heatmap(ranked)

    elif mode == "pathing":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_pathing(ranked)

    else:
        print(f"Unknown mode: {mode}")
