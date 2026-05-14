"""
FaceCheck Display — Core game display functions.

Renders single-game reports, compact game rows, synthesis verdicts,
team breakdowns, and helper formatting.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from facecheck_data import get_current_rank_string

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

# ─────────────────────────────────────────────
# PLAYER ANALYSIS
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

# ─────────────────────────────────────────────
# TEAM BREAKDOWN
# ─────────────────────────────────────────────

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

            # Try cached engine outputs first, fall back to running all 7
            from facecheck_engine_cache import load_engine_outputs, save_engine_outputs
            engines = load_engine_outputs(player_id, historical_games)
            if engines is None:
                death_output = run_death_engine(games=historical_games, player_id=player_id)
                economy_output = run_economy_engine(games=historical_games, player_id=player_id)
                combat_output = run_combat_engine(games=historical_games, player_id=player_id)
                durability_output = run_durability_engine(games=historical_games, player_id=player_id)
                vision_output = run_vision_engine(games=historical_games, player_id=player_id)
                objective_output = run_objective_engine(games=historical_games, player_id=player_id)
                draft_output = run_draft_engine(games=historical_games, player_id=player_id)
                engines = MultiEngineOutput(
                    death=death_output, economy=economy_output, combat=combat_output,
                    durability=durability_output, vision=vision_output,
                    objective=objective_output, draft=draft_output,
                )
                save_engine_outputs(player_id, historical_games, engines)

            if engines.death:
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
        # ── RAW STATS (no synthesis available) ─────────────────────
        print(f"\n  ── RAW STATS {'─'*46}")
        k = game.get("kills", 0)
        d = game.get("deaths", 0)
        a = game.get("assists", 0)
        cs = game.get("cs", 0) or game.get("total_minions_killed", 0)
        cs_15 = game.get("cs_15", 0)
        gold = game.get("gold_earned", 0)
        dmg = game.get("damage_dealt", 0) or game.get("total_damage_dealt_to_champions", 0)
        dmg_taken = game.get("damage_taken", 0) or game.get("total_damage_taken", 0)
        vision = game.get("vision_score", 0)
        wards = game.get("control_wards_bought", 0) or game.get("vision_wards_bought_in_game", 0)
        duration = game.get("duration", 0)
        result = "WIN" if game.get("win") else "LOSS"

        print(f"  {result}  |  KDA: {k}/{d}/{a}  |  CS: {cs} (CS@15: {cs_15})")
        print(f"  Gold: {fmt_k(gold)}  |  Damage: {fmt_k(dmg)}  |  Damage taken: {fmt_k(dmg_taken)}")
        print(f"  Vision: {vision:.0f}  |  Control wards: {wards}  |  Duration: {duration:.0f} min")
        if d > 0:
            print(f"  KDA ratio: {((k + a) / d):.1f}:1")
        print()

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

    # Raw stats summary (no legacy diagnosis)
    d = game.get("deaths", 0)
    k = game.get("kills", 0)
    a = game.get("assists", 0)
    kda_ratio = f"{((k + a) / d):.1f}:1" if d > 0 else "Perfect"
    print(f"  └─ KDA {kda_ratio}  |  CS@15: {game.get('cs_15', 'N/A')}  |  Vision: {game.get('vision_score', game.get('vision', 'N/A'))}")