"""
Verdict Display — Core game display functions.

Renders single-game reports, compact game rows, synthesis verdicts,
team breakdowns, and helper formatting.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from verdict_data import get_current_rank_string
from verdict_game_model import Game, PlayerStats, EnemyPlayer, TeamObjectives
from verdict_synthesis import Observation

# Synthesis availability check
try:
    from verdict_aggregate import synthesize_games_with_engines
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
    roles = [g.role for g in games]
    most_common = max(set(roles), key=roles.count)
    return ROLE_LABELS.get(most_common, "opponent")

# ─────────────────────────────────────────────
# PLAYER ANALYSIS
# ─────────────────────────────────────────────

def analyze_player(player, avg_damage, avg_cs, is_enemy_team=False):
    """Generate a one-line note about a player if something stands out."""
    notes = []
    kda_ratio = (player.kills + player.assists) / max(player.deaths, 1)
    dmg = player.damage
    cs = player.cs

    if player.deaths >= 8:
        notes.append(f"fed hard ({player.deaths} deaths)")
    elif player.deaths >= 6:
        notes.append(f"died too much ({player.deaths} deaths)")

    if dmg >= avg_damage * 1.5:
        notes.append(f"dominant damage ({fmt_k(dmg)})")
    elif dmg < avg_damage * 0.5 and player.role not in ("SUPPORT",):
        notes.append(f"low impact ({fmt_k(dmg)} damage)")

    if kda_ratio >= 5 and player.kills + player.assists >= 10:
        notes.append(f"carried ({player.kills}/{player.deaths}/{player.assists})")

    if player.first_blood_kill:
        notes.append("got first blood")

    if player.turret_kills >= 3:
        notes.append(f"split push threat ({player.turret_kills} towers)")

    if player.control_wards == 0 and player.role not in ("JUNGLE",) and not is_enemy_team:
        notes.append("0 control wards")

    return ", ".join(notes) if notes else None

# ─────────────────────────────────────────────
# TEAM BREAKDOWN
# ─────────────────────────────────────────────

def render_team_breakdown(game: Game):
    """Return structured team breakdown data for a game."""
    all_players = game.all_players
    if not all_players:
        return None

    my_team = sorted([p for p in all_players if p.team == "ally"], key=lambda p: role_order(p.role))
    enemy_team = sorted([p for p in all_players if p.team == "enemy"], key=lambda p: role_order(p.role))

    duration_min = game.duration_min or 1
    my_obj = game.my_team
    enemy_obj = game.enemy_team

    all_dmg = [p.damage for p in all_players]
    avg_dmg = sum(all_dmg) / len(all_dmg) if all_dmg else 1

    result = {"my_team": [], "enemy_team": [], "composition_notes": []}

    for label, team, obj in [("my_team", my_team, my_obj), ("enemy_team", enemy_team, enemy_obj)]:
        team_kills = sum(p.kills for p in team)
        team_deaths = sum(p.deaths for p in team)
        team_assists = sum(p.assists for p in team)
        dragons = obj.dragon_kills
        barons = obj.baron_kills
        towers = obj.tower_kills
        first_blood = obj.first_blood
        first_dragon = obj.first_dragon
        first_tower = obj.first_tower

        players = []
        for p in team:
            players.append({
                "role": p.role,
                "champion": p.champion,
                "kda": f"{p.kills}/{p.deaths}/{p.assists}",
                "kills": p.kills, "deaths": p.deaths, "assists": p.assists,
                "cs": p.cs, "damage": p.damage, "vision": p.vision, "gold": p.gold,
                "is_me": p.is_me,
                "note": analyze_player(p, avg_dmg, 0, is_enemy_team=(label == "enemy_team")),
                "build_order": p.build_order,
            })

        result[label] = {
            "players": players,
            "team_kda": f"{team_kills}/{team_deaths}/{team_assists}",
            "dragons": dragons, "barons": barons, "towers": towers,
            "first_blood": first_blood, "first_dragon": first_dragon, "first_tower": first_tower,
        }

    # Composition notes
    enemy_sorted = sorted(enemy_team, key=lambda p: p.damage, reverse=True)
    top_enemy = enemy_sorted[0] if enemy_sorted else None
    if top_enemy and top_enemy.damage > avg_dmg * 1.3:
        total_enemy_dmg = sum(p.damage for p in enemy_team) or 1
        total_enemy_kills = sum(p.kills for p in enemy_team) or 1
        dmg_share = top_enemy.damage / total_enemy_dmg * 100
        kp_pct = (top_enemy.kills + top_enemy.assists) / total_enemy_kills * 100
        result["composition_notes"].append({
            "type": "enemy_carry",
            "champion": top_enemy.champion, "role": top_enemy.role,
            "damage": top_enemy.damage, "dmg_share_pct": round(dmg_share, 1),
            "kda": f"{top_enemy.kills}/{top_enemy.deaths}/{top_enemy.assists}",
            "kp_pct": round(kp_pct, 1),
        })

    my_sorted = sorted(my_team, key=lambda p: p.damage, reverse=True)
    top_ally = my_sorted[0] if my_sorted else None
    if top_ally and not top_ally.is_me and top_ally.damage > avg_dmg * 1.2:
        result["composition_notes"].append({
            "type": "ally_performer",
            "champion": top_ally.champion, "role": top_ally.role,
            "damage": top_ally.damage,
            "kda": f"{top_ally.kills}/{top_ally.deaths}/{top_ally.assists}",
        })

    feeders = [p for p in my_team if p.deaths >= 8 and not p.is_me]
    if feeders:
        total_team_deaths = sum(p.deaths for p in my_team) or 1
        feeder_deaths = sum(p.deaths for p in feeders)
        feeder_pct = feeder_deaths / total_team_deaths * 100
        result["composition_notes"].append({
            "type": "feeder",
            "champions": [f"{p.champion} ({p.deaths} deaths)" for p in feeders],
            "feeder_death_pct": round(feeder_pct, 1),
        })

    return result

def print_team_breakdown(game):
    """Print the full 10-player breakdown after verdict."""
    data = render_team_breakdown(game)
    if not data:
        return

    print(f"\n  ── TEAM BREAKDOWN {'─'*45}")

    for label, team_key in [("YOUR TEAM", "my_team"), ("ENEMY TEAM", "enemy_team")]:
        team_data = data[team_key]
        players = team_data["players"]
        is_enemy = team_key == "enemy_team"

        dragons = team_data["dragons"]
        barons = team_data["barons"]
        towers = team_data["towers"]
        fb = "✓ First Blood" if team_data["first_blood"] else ""
        fd = "✓ First Dragon" if team_data["first_dragon"] else ""
        ft = "✓ First Tower" if team_data["first_tower"] else ""

        badges = "  ".join(b for b in [fb, fd, ft] if b)

        print(f"\n  ┌─ {label} — {team_data['team_kda']}  |  🐉{dragons}  🏰{barons}  🗼{towers}")
        if badges:
            print(f"  │  {badges}")
        print(f"  │")
        print(f"  │  {'Role':<9} {'Champion':<14} {'KDA':<12} {'CS':<6} {'Damage':<10} {'Vision':<8} {'Gold':<8} Notes")
        print(f"  │  {'─'*100}")
        for p in players:
            me = " ◄" if p["is_me"] else ""
            note_str = f"  {p['note']}" if p["note"] else ""
            print(f"  │  {p['role']:<9} {p['champion']:<14} {p['kda']:<12} {p['cs']:<6} {fmt_k(p['damage']):<10} {p['vision']:<8} {fmt_k(p['gold']):<8}{me}{note_str}")

        # Build orders for this team
        print(f"  │")
        print(f"  │  BUILD ORDERS:")
        for p in players:
            if p.get("build_order"):
                me = " ◄" if p["is_me"] else ""
                build_str = " → ".join(p["build_order"][:4])
                if len(p["build_order"]) > 4:
                    build_str += " ..."
                print(f"  │  {p['role']:<9} {p['champion']:<14} {build_str}{me}")

        print(f"  └{'─'*108}")

    # Comp analysis
    print(f"\n  ── COMPOSITION NOTES {'─'*41}")
    for note in data["composition_notes"]:
        if note["type"] == "enemy_carry":
            print(f"  Enemy carry: {note['champion']} ({note['role']}) — {fmt_k(note['damage'])} damage ({note['dmg_share_pct']:.0f}% of team), {note['kda']} KDA, {note['kp_pct']:.0f}% KP")
        elif note["type"] == "ally_performer":
            print(f"  Ally performer: {note['champion']} ({note['role']}) — {fmt_k(note['damage'])} damage, {note['kda']} KDA")
        elif note["type"] == "feeder":
            feeder_str = ", ".join(note["champions"])
            print(f"  Feeding: {feeder_str} — {note['feeder_death_pct']:.0f}% of team deaths")
    print()

# ─────────────────────────────────────────────
# SYNTHESIS VERDICT RENDERER
# ─────────────────────────────────────────────

def render_verdict(verdict):
    """Return a structured dict representation of a synthesis verdict."""
    summary_text = verdict.summary.to_text() if hasattr(verdict.summary, 'to_text') else verdict.summary
    result = {
        "statement": verdict.statement,
        "confidence": verdict.confidence,
        "summary": summary_text,
        "summary_sections": [{"domain": s.domain, "statement": s.statement, "data": s.data} for s in verdict.summary.sections] if hasattr(verdict.summary, 'sections') else [],
        "evidence": [],
        "lessons": [],
        "divergences": [d.statement for d in verdict.divergences] if verdict.divergences and hasattr(verdict.divergences[0], 'statement') else list(verdict.divergences) if verdict.divergences else [],
        "divergence_details": [{"type": d.divergence_type, "statement": d.statement, "data": d.data, "win": d.win} for d in verdict.divergences] if verdict.divergences and hasattr(verdict.divergences[0], 'divergence_type') else [],
        "drill_down_prompt": verdict.drill_down_prompt if verdict.drill_down_available else None,
        "cluster_label": verdict.cluster_label,
        "mechanism": verdict.mechanism,
        "counterfactual_insight": verdict.counterfactual_insight,
        "similar_games": verdict.similar_games[:3] if verdict.similar_games else [],
        "pattern_insight": verdict.pattern_insight,
        "matched_patterns": verdict.matched_patterns[:3] if verdict.matched_patterns else [],
        "secondary_observations": [],
    }
    for ev in (verdict.primary_evidence or []):
        result["evidence"].append({
            "type": ev.evidence_type,
            "description": ev.description,
            "value": ev.value,
            "context": ev.context,
        })
    for lesson in (verdict.lessons or []):
        result["lessons"].append({
            "priority": lesson.priority,
            "text": lesson.text,
        })
    if verdict.observations and len(verdict.observations) > 1:
        for obs in verdict.observations[1:4]:
            result["secondary_observations"].append({
                "label": obs.label,
                "priority": obs.priority,
            })
    return result

def print_synthesis_block(verdict):
    """Render a full synthesis verdict to the user."""
    print(f"\n  ── SYNTHESIS VERDICT {'─'*41}")
    print(f"  ╔{'═'*60}╗")
    print(f"  ║  {verdict.statement:<56} ║")
    print(f"  ╚{'═'*60}╝")
    print(f"\n  Confidence: {verdict.confidence:.0%}")
    if verdict.summary:
        summary_text = verdict.summary.to_text() if hasattr(verdict.summary, 'to_text') else verdict.summary
        print(f"\n  {summary_text}")

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
            text = div.statement if hasattr(div, 'statement') else div
            print(f"    • {text}")

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

    # Secondary observations (Phase E)
    if verdict.observations and len(verdict.observations) > 1:
        print(f"\n  Also detected:")
        for obs in verdict.observations[1:4]:
            print(f"    • {obs.label} ({obs.priority})")

# ─────────────────────────────────────────────
# FULL SINGLE GAME OUTPUT
# ─────────────────────────────────────────────

def render_game(game: Game, game_number=None, historical_games=None, legacy=False, player_id=None, cache=None, service=None):
    """Return structured data for a full single-game report.

    Includes header, performance, enemy counterpart, team summary,
    verdict (from synthesis) or raw_stats, and team breakdown.
    """
    win = game.win
    result_label = "WIN" if win else "LOSS"
    label = f"GAME {game_number}" if game_number else "LAST GAME"
    rank_str = get_current_rank_string(cache) if cache else None
    enemy = game.enemy

    # ── HEADER ──────────────────────────────────────────────────────
    header = {
        "label": label,
        "result": result_label,
        "queue": game.queue,
        "champion": game.champion,
        "duration_min": game.duration_min,
        "player_id": player_id,
        "rank_str": rank_str,
    }

    # ── YOUR PERFORMANCE ──────────────────────────────────────────
    my_team_kills = game.my_team.kills
    my_team_deaths = game.my_team.deaths
    ally_dmg = sum(p.damage for p in game.all_players if p.team == "ally")
    kp_pct = round((game.kills + game.assists) / max(my_team_kills, 1) * 100)
    ds_pct = round(game.deaths / max(my_team_deaths, 1) * 100)
    dmg_pct = round(game.damage / max(ally_dmg, 1) * 100)

    performance = {
        "kda": f"{game.kills}/{game.deaths}/{game.assists}",
        "kills": game.kills, "deaths": game.deaths, "assists": game.assists,
        "kp_pct": kp_pct, "dmg_share_pct": dmg_pct, "death_share_pct": ds_pct,
        "cs_final": game.cs_final, "cs_per_min": game.cs_per_min,
        "cs_10": game.cs_10 or "N/A", "cs_15": game.cs_15 or "N/A",
        "damage": game.damage, "damage_per_min": game.damage_per_min,
        "vision": game.vision, "vision_per_min": game.vision_per_min,
        "wards_placed": game.wards_placed,
        "control_wards": game.control_wards,
        "gold": game.gold, "gold_per_min": game.gold_per_min,
        "gold_15": game.gold_15,
        "turret_kills": game.turret_kills,
        "first_blood_kill": game.first_blood_kill,
        "largest_killing_spree": game.largest_killing_spree,
        "build_order": game.build_order,
    }

    # ── ENEMY COUNTERPART ──────────────────────────────────────────
    ROLE_HEADERS = {
        "JUNGLE":  "ENEMY JUNGLER",
        "TOP":     "ENEMY TOP LANER",
        "MIDDLE":  "ENEMY MID LANER",
        "BOTTOM":  "ENEMY ADC",
        "UTILITY": "ENEMY SUPPORT",
    }
    role = game.role or "JUNGLE"
    enemy_data = None
    if enemy:
        cs_diff = game.cs_final - enemy.cs
        dmg_diff = game.damage - enemy.damage
        gold_diff = game.gold - enemy.gold
        gold_15_diff = game.gold_lead_15
        enemy_data = {
            "role_header": ROLE_HEADERS.get(role, "ENEMY COUNTERPART"),
            "champion": enemy.champion,
            "kda": f"{enemy.kills}/{enemy.deaths}/{enemy.assists}",
            "kills": enemy.kills, "deaths": enemy.deaths, "assists": enemy.assists,
            "cs": enemy.cs, "cs_diff": cs_diff,
            "damage": enemy.damage, "dmg_diff": dmg_diff,
            "gold": enemy.gold, "gold_diff": gold_diff,
            "gold_15_diff": gold_15_diff,
            "killed_by_enemy_jungler": game.killed_by_enemy_jungler,
        }

    # ── TEAM SUMMARY ──────────────────────────────────────────────
    my_team_data = game.my_team
    enemy_team_data = game.enemy_team
    team_summary = None
    if my_team_data and enemy_team_data:
        firsts = []
        if my_team_data.first_blood: firsts.append("First Blood")
        if my_team_data.first_dragon: firsts.append("First Dragon")
        if my_team_data.first_tower: firsts.append("First Tower")
        team_summary = {
            "my_team": {
                "kills": my_team_data.kills,
                "deaths": my_team_data.deaths,
                "dragons": my_team_data.dragon_kills,
                "barons": my_team_data.baron_kills,
                "towers": my_team_data.tower_kills,
            },
            "enemy_team": {
                "kills": enemy_team_data.kills,
                "deaths": enemy_team_data.deaths,
                "dragons": enemy_team_data.dragon_kills,
                "barons": enemy_team_data.baron_kills,
                "towers": enemy_team_data.tower_kills,
            },
            "secured_firsts": firsts,
        }

    # ── ANALYSIS (synthesis or raw stats) ──────────────────────────
    verdict_data = None
    _raw_verdict = None
    raw_stats = None
    synthesis_error = None

    if SYNTHESIS_AVAILABLE and historical_games and not legacy:
        try:
            if not player_id:
                from verdict_config import ensure_config; ensure_config()
                from config import MY_GAME_NAME, MY_TAG_LINE
                player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"
                header["player_id"] = player_id

            if service is not None:
                # Use cached pipeline data from AnalysisService
                pairs = service.pairs
                engines = service.engines
            else:
                from verdict_aggregate import synthesize_games_with_engines
                pairs, engines = synthesize_games_with_engines(historical_games, player_id)

            if engines and engines.death:
                # Find this game's verdict from the synthesized pairs
                verdict_obj = None
                for g, v in pairs:
                    if g is game or g.match_id == game.match_id:
                        verdict_obj = v
                        break

                if verdict_obj:
                    verdict_data = render_verdict(verdict_obj)
                    _raw_verdict = verdict_obj
        except Exception as e:
            synthesis_error = str(e)

    if verdict_data is None and synthesis_error is None:
        k = game.kills
        d = game.deaths
        a = game.assists
        cs = game.cs_final
        cs_15 = game.cs_15 or 0
        gold = game.gold
        dmg = game.damage
        dmg_taken = game.total_damage_taken
        vision = game.vision
        wards = game.control_wards
        duration = game.duration_min
        raw_stats = {
            "result": "WIN" if game.win else "LOSS",
            "kda": f"{k}/{d}/{a}",
            "kills": k, "deaths": d, "assists": a,
            "cs": cs, "cs_15": cs_15,
            "gold": gold, "damage": dmg, "damage_taken": dmg_taken,
            "vision": vision, "control_wards": wards, "duration": duration,
        }

    # ── TEAM BREAKDOWN ────────────────────────────────────────────
    team_breakdown = render_team_breakdown(game)

    return {
        "header": header,
        "performance": performance,
        "enemy": enemy_data,
        "team_summary": team_summary,
        "verdict": verdict_data,
        "raw_stats": raw_stats,
        "synthesis_error": synthesis_error,
        "team_breakdown": team_breakdown,
        "_verdict_obj": _raw_verdict,
    }


def _diff_label(val):
    """Show differential from YOUR perspective — positive means YOU are ahead."""
    if val is None:
        return "N/A"
    v = round(val)
    if v > 0:
        return f"+{v} your favor"
    if v < 0:
        return f"{v} their favor"
    return "even"


def print_full_game(game, game_number=None, historical_games=None, legacy=False, player_id=None, cache=None, service=None):
    data = render_game(game, game_number=game_number, historical_games=historical_games,
                       legacy=legacy, player_id=player_id, cache=cache, service=service)

    h = data["header"]
    p = data["performance"]
    border = "╔" + "═" * 62 + "╗"
    border_bot = "╚" + "═" * 62 + "╝"

    print(f"\n  {border}")
    print(f"  ║  VERDICT — {h['label']:<48}║")
    if h["rank_str"] and h["player_id"]:
        print(f"  ║  {h['player_id']}  —  {h['rank_str']:<43}║")
    elif h["player_id"]:
        print(f"  ║  {h['player_id']:<55}║")
    print(f"  ║  {h['queue']}  |  {h['champion']}  |  {h['duration_min']}m  |  {h['result']:<33}║")
    print(f"  {border_bot}")

    # ── YOUR PERFORMANCE ──────────────────────────────────────────
    print(f"\n  ── YOUR PERFORMANCE {'─'*43}")
    print(f"  KDA:      {p['kda']}")
    print(f"  KP:       {p['kp_pct']}%  |  Dmg Share: {p['dmg_share_pct']}%  |  Death Share: {p['death_share_pct']}%")
    print(f"  CS:       {p['cs_final']}  ({p['cs_per_min']}/min)  |  CS@10: {p['cs_10']}  |  CS@15: {p['cs_15']}")
    print(f"  Damage:   {fmt_k(p['damage'])}  ({fmt_k(p['damage_per_min'])}/min)")
    print(f"  Vision:   {p['vision']}  ({p['vision_per_min']}/min)  |  Wards: {p['wards_placed']}  |  Control: {p['control_wards']}")
    print(f"  Gold:     {fmt_k(p['gold'])}  ({fmt_k(p['gold_per_min'])}/min)  |  Gold@15: {fmt_k(p['gold_15'])}")
    if p["turret_kills"]:
        print(f"  Towers:   {p['turret_kills']}")
    if p["first_blood_kill"]:
        print(f"  First Blood: ✓")
    if p["largest_killing_spree"] >= 3:
        print(f"  Killing Spree: {p['largest_killing_spree']}")
    build_str = " → ".join(p["build_order"])
    print(f"  Build:    {build_str if build_str else 'N/A'}")

    # ── ENEMY COUNTERPART ─────────────────────────────────────────
    e = data["enemy"]
    if e:
        print(f"\n  ── {e['role_header']} {'─'*46}")
        print(f"  {e['champion']}  |  {e['kda']}")
        print(f"  CS:       {e['cs']}  ({_diff_label(e['cs_diff'])})")
        print(f"  Damage:   {fmt_k(e['damage'])}  ({_diff_label(e['dmg_diff'])})")
        print(f"  Gold:     {fmt_k(e['gold'])}  ({_diff_label(e['gold_diff'])})")
        if e["gold_15_diff"] is not None:
            print(f"  Gold@15:  {_diff_label(e['gold_15_diff'])}")
        if e["killed_by_enemy_jungler"]:
            print(f"  Killed you: {e['killed_by_enemy_jungler']}x")

    # ── TEAM SUMMARY ──────────────────────────────────────────────
    ts = data["team_summary"]
    if ts:
        mt = ts["my_team"]
        et = ts["enemy_team"]
        print(f"\n  ── TEAM SUMMARY {'─'*47}")
        print(f"  {'':12} {'Kills':<8} {'Deaths':<8} {'Dragons':<10} {'Barons':<8} {'Towers'}")
        print(f"  {'Your Team':<12} {mt['kills']:<8} {mt['deaths']:<8} {mt['dragons']:<10} {mt['barons']:<8} {mt['towers']}")
        print(f"  {'Enemy Team':<12} {et['kills']:<8} {et['deaths']:<8} {et['dragons']:<10} {et['barons']:<8} {et['towers']}")
        if ts["secured_firsts"]:
            print(f"  Your team secured: {', '.join(ts['secured_firsts'])}")

    # ── ANALYSIS ──────────────────────────────────────────────────
    if data["_verdict_obj"]:
        print_synthesis_block(data["_verdict_obj"])
    elif data["synthesis_error"]:
        print(f"\n  [Synthesis engine error: {data['synthesis_error']}]")
        print("  Falling back to raw stats...")
        if data["raw_stats"]:
            _print_raw_stats(data["raw_stats"])
    elif data["raw_stats"]:
        _print_raw_stats(data["raw_stats"])

    # ── TEAM BREAKDOWN ────────────────────────────────────────────
    print_team_breakdown(game)

    print(f"  {'═'*62}")


def _print_raw_stats(stats):
    """Print raw stats block from structured data."""
    print(f"\n  ── RAW STATS {'─'*46}")
    print(f"  {stats['result']}  |  KDA: {stats['kda']}  |  CS: {stats['cs']} (CS@15: {stats['cs_15']})")
    print(f"  Gold: {fmt_k(stats['gold'])}  |  Damage: {fmt_k(stats['damage'])}  |  Damage taken: {fmt_k(stats['damage_taken'])}")
    print(f"  Vision: {stats['vision']:.0f}  |  Control wards: {stats['control_wards']}  |  Duration: {stats['duration']:.0f} min")
    if stats["deaths"] > 0:
        print(f"  KDA ratio: {((stats['kills'] + stats['assists']) / stats['deaths']):.1f}:1")
    print()

# ─────────────────────────────────────────────
# COMPACT GAME OUTPUT (for verdict games)
# ─────────────────────────────────────────────

def render_compact_game(game: Game, game_number, historical_games=None):
    """Return structured data for compact game display."""
    enemy = game.enemy
    kda = f"{game.kills}/{game.deaths}/{game.assists}"

    build_order = game.build_order
    build_short = " → ".join(build_order[:3])
    if len(build_order) > 3:
        build_short += " ..."

    d = game.deaths
    k = game.kills
    a = game.assists
    kda_ratio = f"{((k + a) / d):.1f}:1" if d > 0 else "Perfect"

    result = {
        "game_number": game_number,
        "champion": game.champion,
        "result": "WIN" if game.win else "LOSS",
        "kda": kda,
        "kda_ratio": kda_ratio,
        "cs": game.cs_final,
        "cs_per_min": game.cs_per_min,
        "cs_15": game.cs_15 or "N/A",
        "damage": game.damage,
        "vision": game.vision,
        "vision_score": game.vision,
        "gold": game.gold,
        "role": game.role,
        "duration_min": game.duration_min or 0,
        "queue": game.queue,
        "build_short": build_short if build_order else None,
        "enemy": None,
        "streak_info": None,
    }

    if enemy:
        cs_diff = game.cs_final - enemy.cs
        result["enemy"] = {
            "champion": enemy.champion,
            "kda": f"{enemy.kills}/{enemy.deaths}/{enemy.assists}",
            "cs": enemy.cs,
            "cs_diff": cs_diff,
        }

    return result

def print_compact_game(game, game_number, historical_games=None):
    """Print a compact game summary."""
    data = render_compact_game(game, game_number, historical_games)

    print(f"\n  ┌─ [{data['game_number']}] {data['queue']} — {data['champion']} — {data['duration_min']}m — {data['result']}")
    print(f"  │  {data['kda']}  |  CS: {data['cs']} ({data['cs_per_min']}/min)  |  Dmg: {fmt_k(data['damage'])}  |  Vision: {data['vision']}  |  Gold: {fmt_k(data['gold'])}")
    if data["build_short"]:
        print(f"  │  Build: {data['build_short']}")
    if data["enemy"]:
        e = data["enemy"]
        print(f"  │  Enemy: {e['champion']}  {e['kda']}  |  CS: {e['cs']} ({fmt_num(e['cs_diff'], plus=True)})")

    print(f"  └─ KDA {data['kda_ratio']}  |  CS@15: {data['cs_15']}  |  Vision: {data['vision_score']}")