"""
Verdict Special — Specialized mode handlers.

Matchups, guide, bans, heatmap, pathing, and select interface.
"""

import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from verdict_game_model import Game
from verdict_data import get_ranked_games, get_current_rank_string
from verdict_display import ROLE_LABELS, enemy_role_label, print_full_game
from verdict_aggregate import synthesize_games, synthesize_games_with_engines, mine_observations, worst_patterns, best_patterns, compare_players, _winrate, _split_by_result

# Champion Intelligence — optional, graceful fallback
try:
    from verdict_champ_intel import (
        get_matchup_context, print_matchup_context,
        print_counter_command, print_intel_profile,
        load_champion_intel
    )
    INTEL_AVAILABLE = True
except Exception:
    INTEL_AVAILABLE = False

# ─────────────────────────────────────────────
# SELECT INTERFACE
# ─────────────────────────────────────────────

def get_select_games(cache, champion=None, result_filter=None):
    """Get filtered game list for select mode. Returns list of Game objects."""
    games = get_ranked_games(cache, champion=champion)
    if not games:
        return []

    if result_filter == "wins":
        games = [g for g in games if g.win]
    elif result_filter == "losses":
        games = [g for g in games if not g.win]

    return games


def get_select_page(games, page=0, page_size=10):
    """Return a single page of select data. No input() calls."""
    total_pages = max(1, (len(games) - 1) // page_size + 1)
    start = page * page_size
    end = min(start + page_size, len(games))
    page_games = games[start:end]

    rows = []
    for i, g in enumerate(page_games):
        num = start + i + 1
        rows.append({
            "num": num, "queue": g.queue, "champion": g.champion,
            "result": "WIN" if g.win else "LOSS",
            "duration_min": g.duration_min,
            "kda": f"{g.kills}/{g.deaths}/{g.assists}",
            "game_index": start + i,
        })

    return {
        "page": page, "total_pages": total_pages,
        "total_games": len(games),
        "rows": rows,
        "has_next": page < total_pages - 1,
        "has_prev": page > 0,
    }


def run_select(cache, champion=None, result_filter=None):
    """Interactive game browser. Uses input() — only for terminal use."""
    games = get_select_games(cache, champion=champion, result_filter=result_filter)
    if not games:
        label = f" for {champion}" if champion else ""
        print("No ranked games found." + label)
        return

    page_size = 10
    page = 0
    title_parts = []
    if champion:
        title_parts.append(champion)
    if result_filter:
        title_parts.append(result_filter.capitalize())
    title_suffix = f" — {' '.join(title_parts)}" if title_parts else ""

    while True:
        page_data = get_select_page(games, page=page, page_size=page_size)

        print(f"\n  Verdict Select{title_suffix}  |  Page {page_data['page'] + 1}/{page_data['total_pages']}  |  {page_data['total_games']} games")
        print(f"  {'─'*70}")
        print(f"  {'#':<5} {'Queue':<20} {'Champion':<14} {'Result':<6} {'Duration':<10} {'KDA'}")
        print(f"  {'─'*70}")

        for r in page_data["rows"]:
            print(f"  {r['num']:<5} {r['queue']:<20} {r['champion']:<14} {r['result']:<6} {r['duration_min']}m{'':<5} {r['kda']}")

        print(f"\n  Enter game number, [n]ext page, [p]rev page, or [q]uit:")
        try:
            inp = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if inp == "q":
            break
        elif inp == "n":
            if page_data["has_next"]:
                page += 1
            else:
                print("  Already on last page.")
        elif inp == "p":
            if page_data["has_prev"]:
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

def _avg(lst):
    lst = [v for v in lst if v is not None]
    return round(sum(lst) / len(lst), 1) if lst else 0


def analyze_matchups(games, champion=None):
    """Analyze matchup data. Returns structured dict with profiles, categories, and patterns."""
    games_e = [g for g in games if g.enemy]
    wins_total = len([g for g in games if g.win])
    losses_total = len([g for g in games if not g.win])
    wr_overall = round(wins_total / len(games) * 100, 1) if games else 0

    header = {
        "label": f"VERDICT MATCHUPS — {champion}" if champion else "VERDICT MATCHUPS",
        "total_games": len(games), "wins": wins_total, "losses": losses_total,
        "wr": wr_overall,
        "games_with_enemy": len(games_e),
        "enemy_label": f"enemy {enemy_role_label(games)}",
    }

    if not games_e:
        return {"header": header, "profiles": [], "worst": [], "tough": [], "even": [],
                "favorable": [], "small_sample": [], "patterns": []}

    # Build per-enemy-champion profile
    enemy_profiles = defaultdict(lambda: {
        "games": [], "wins": [], "losses": [],
        "cs_diff": [], "damage_diff": [], "kill_diff": [], "gold_diff": [],
        "early_death_games": [], "killed_by": [],
    })

    for g in games_e:
        e = g.enemy
        ec = e.champion
        p = enemy_profiles[ec]
        p["games"].append(g)
        p["cs_diff"].append(g.cs_final - e.cs)
        p["damage_diff"].append(g.damage - e.damage)
        p["kill_diff"].append(g.kills - e.kills)
        p["gold_diff"].append(g.gold - e.gold)
        p["killed_by"].append(g.killed_by_enemy_jungler)
        if g.win:
            p["wins"].append(g)
        else:
            p["losses"].append(g)
            if g.early_deaths >= 2:
                p["early_death_games"].append(g)

    qualified = {ec: p for ec, p in enemy_profiles.items() if len(p["games"]) >= 3}
    small_sample = {ec: p for ec, p in enemy_profiles.items() if len(p["games"]) < 3}

    profiles = []
    for ec, p in qualified.items():
        total = len(p["games"])
        wr = round(len(p["wins"]) / total * 100, 1) if total > 0 else 0
        profiles.append({
            "champion": ec, "games": total, "wins": len(p["wins"]), "losses": len(p["losses"]),
            "wr": wr,
            "avg_cs_diff": _avg(p["cs_diff"]), "avg_dmg_diff": _avg(p["damage_diff"]),
            "avg_kill_diff": _avg(p["kill_diff"]), "avg_gold_diff": _avg(p["gold_diff"]),
            "avg_killed_by": _avg(p["killed_by"]), "early_death_losses": len(p["early_death_games"]),
        })
    profiles.sort(key=lambda x: x["wr"])

    worst = [p for p in profiles if p["wr"] <= 35]
    tough = [p for p in profiles if 35 < p["wr"] <= 49]
    even = [p for p in profiles if 49 < p["wr"] <= 59]
    favorable = [p for p in profiles if p["wr"] > 59]

    # Interpretation notes for losing matchups
    for p in worst + tough:
        ec = p["champion"]
        cs, wr = p["avg_cs_diff"], p["wr"]
        dmg, killed_by = p["avg_dmg_diff"], p["avg_killed_by"]
        early_d, losses_n = p["early_death_losses"], p["losses"]
        if cs > 0 and wr <= 40:
            p["note"] = f"You farm ahead of {ec} (+{cs:.0f} CS) but lose anyway — combat is the issue, not farm."
        elif cs < -20:
            p["note"] = f"{ec} out-farms you by {-cs:.0f} CS — the resource gap drives {100-wr:.0f}% of your losses."
        elif killed_by >= 1.5:
            p["note"] = f"{ec} kills you {killed_by:.1f}x per game — they're finding you in your jungle {killed_by:.1f}x/game."
        elif dmg < -3000:
            p["note"] = f"{ec} outscales you in combat by {abs(dmg):,.0f} damage per game — avoid fighting without an advantage."
        elif early_d >= losses_n * 0.5:
            p["note"] = f"{early_d} of {losses_n} losses to {ec} involve early deaths — they dictate tempo before 15min."
        else:
            p["note"] = f"Losing record against {ec}. Run: face select {ec}"

    # Interpretation notes for winning matchups
    for p in favorable:
        ec = p["champion"]
        cs, dmg, kills = p["avg_cs_diff"], p["avg_dmg_diff"], p["avg_kill_diff"]
        if cs > 30 and dmg > 2000:
            p["note"] = f"+{cs:.0f} CS and +{dmg:,.0f} damage vs {ec} — strongest matchup in your pool."
        elif cs > 20:
            p["note"] = f"+{cs:.0f} CS vs {ec} — resource advantage is consistent across {p['games']} games."
        elif kills > 2:
            p["note"] = f"+{kills:.1f} kills vs {ec} per game — winning duels but need objectives to close."
        else:
            p["note"] = f"{p['wr']}% WR over {p['games']} games vs {ec} — favorable matchup."
        # Attach intel if available
        if INTEL_AVAILABLE:
            ec_intel = load_champion_intel(ec)
            if ec_intel:
                sig = ec_intel.get("signals", {})
                p["intel_key_mechanic"] = sig.get("key_mechanic", "")

    # Small sample data
    small_data = []
    for ec, p in sorted(small_sample.items(), key=lambda x: len(x[1]["games"]), reverse=True):
        small_data.append({
            "champion": ec, "games": len(p["games"]),
            "wins": len(p["wins"]), "losses": len(p["losses"]),
        })

    # Cross-matchup patterns
    patterns = []
    if worst:
        positive_cs_losses = [p for p in worst if p["avg_cs_diff"] > 0]
        if len(positive_cs_losses) >= 2:
            champs = ", ".join(p["champion"] for p in positive_cs_losses)
            patterns.append({
                "type": "fight_loss", "champions": champs,
                "insight": "These are fight-loss matchups. The farm is not the issue — the combat outcome is.",
            })
        high_kill_by = [p for p in worst if p["avg_killed_by"] >= 1.5]
        if high_kill_by:
            champs = ", ".join(p["champion"] for p in high_kill_by)
            patterns.append({
                "type": "hunted", "champions": champs,
                "insight": "These champions are likely running you down in your own jungle. Ward the river and your second buff.",
            })

    return {
        "header": header, "profiles": profiles,
        "worst": worst, "tough": tough, "even": even, "favorable": favorable,
        "small_sample": small_data, "patterns": patterns,
    }


def print_matchups(games, champion=None):
    result = analyze_matchups(games, champion=champion)
    h = result["header"]

    print(f"\n  {'='*62}")
    print(f"  {h['label']}")
    print(f"  {'='*62}")
    print(f"  {h['total_games']} games  |  {h['wins']}W {h['losses']}L  |  {h['wr']}% WR")
    print(f"  {h['games_with_enemy']} games with {h['enemy_label']} data")
    print(f"  {'='*62}")

    if not result["profiles"] and not result["small_sample"]:
        print("  No enemy matchup data found.")
        return

    # ── LOSING MATCHUPS ───────────────────────────────────────────
    if result["worst"] or result["tough"]:
        print(f"\n  ── LOSING MATCHUPS {'─'*44}")
        print()
        for p in result["worst"] + result["tough"]:
            ec = p["champion"]
            tier = "BAD" if p["wr"] <= 35 else "TOUGH"
            print(f"  ┌─ {ec}  [{tier}]  {p['wins']}W {p['losses']}L  ({p['wr']}%)")
            print(f"  │  CS:     {p['avg_cs_diff']:+.0f}  avg vs {ec}")
            print(f"  │  Damage: {p['avg_dmg_diff']:+,.0f}  avg vs {ec}")
            print(f"  │  Kills:  {p['avg_kill_diff']:+.1f}  avg vs {ec}")
            print(f"  │  Gold:   {p['avg_gold_diff']:+,.0f}  avg vs {ec}")
            if p["avg_killed_by"] >= 1:
                print(f"  │  Killed by them: {p['avg_killed_by']:.1f}x per game on average")
            if p["early_death_losses"] >= 2:
                print(f"  │  Early death losses: {p['early_death_losses']} of {p['losses']} losses had 2+ deaths pre-15min")
            if p.get("note"):
                print(f"  │  {p['note']}")
            print(f"  └{'─'*63}")
            print()

    # ── EVEN MATCHUPS ─────────────────────────────────────────────
    if result["even"]:
        print(f"  ── EVEN MATCHUPS {'─'*46}")
        print()
        for p in result["even"]:
            print(f"  {p['champion']:<18} {p['wins']}W {p['losses']}L  ({p['wr']}%)   CS: {p['avg_cs_diff']:+.0f}  Dmg: {p['avg_dmg_diff']:+,.0f}  Kills: {p['avg_kill_diff']:+.1f}")
        print()

    # ── WINNING MATCHUPS ──────────────────────────────────────────
    if result["favorable"]:
        print(f"  ── WINNING MATCHUPS {'─'*43}")
        print()
        for p in sorted(result["favorable"], key=lambda x: x["wr"], reverse=True):
            ec = p["champion"]
            print(f"  ┌─ {ec}  [FAVORED]  {p['wins']}W {p['losses']}L  ({p['wr']}%)")
            print(f"  │  CS: {p['avg_cs_diff']:+.0f}  |  Damage: {p['avg_dmg_diff']:+,.0f}  |  Kills: {p['avg_kill_diff']:+.1f}")
            if p.get("note"):
                print(f"  │  {p['note']}")
            if p.get("intel_key_mechanic"):
                print(f"  │  Intel: {p['intel_key_mechanic']}")
            print(f"  └{'─'*63}")
            print()

    # ── SMALL SAMPLE ──────────────────────────────────────────────
    if result["small_sample"]:
        print(f"  ── LIMITED DATA (1-2 games) {'─'*35}")
        print()
        for s in result["small_sample"][:8]:
            print(f"  {s['champion']:<18} {s['wins']}W {s['losses']}L  ({s['games']} game{'s' if s['games'] > 1 else ''} — not enough to conclude)")
        print()

    # ── OVERALL MATCHUP SUMMARY ───────────────────────────────────
    print(f"  ── MATCHUP SUMMARY {'─'*44}")
    print()
    n_qualified = len(result["profiles"])
    if n_qualified:
        n_bad = len(result["worst"])
        n_tough = len(result["tough"])
        n_even = len(result["even"])
        n_fav = len(result["favorable"])
        print(f"  {n_qualified} champions with 3+ games:")
        print(f"  Losing  ({n_bad + n_tough}) — Tough/Bad matchups to study")
        print(f"  Even    ({n_even}) — Coin flip matchups")
        print(f"  Winning ({n_fav}) — Seek these out")
        print()

    if result["worst"]:
        hardest = result["worst"][0]
        print(f"  Hardest matchup:  {hardest['champion']} — {hardest['wr']}% WR across {hardest['games']} games")
    if result["favorable"]:
        easiest = sorted(result["favorable"], key=lambda x: x["wr"], reverse=True)[0]
        print(f"  Easiest matchup:  {easiest['champion']} — {easiest['wr']}% WR across {easiest['games']} games")

    for pat in result["patterns"]:
        print(f"\n  Pattern detected: You average positive CS against {pat['champions']} but still lose.")
        print(f"  {pat['insight']}")

    print()

# ─────────────────────────────────────────────
# GUIDE
# ─────────────────────────────────────────────

def analyze_guide():
    """Return structured guide data."""
    return {
        "sections": [
            {
                "title": "AFTER A LOSS",
                "lines": [
                    "Run: face lastgame",
                    "Check the VERDICT section — it names the primary loss factor.",
                    "If the loss was unwinnable (team feed pattern), note it and move on.",
                    "If it was your early game, run: face Viego (or your champion)",
                    "Look for the CS@15 gap and early death patterns. Fix those first.",
                ],
            },
            {
                "title": "BEFORE QUEUING",
                "lines": [
                    "Run: face pool",
                    "Play your PLAY verdict champions. Avoid AVOID.",
                    "If CONDITIONAL appears, play only in low-stakes games while trending up.",
                    "Run: face matchups to see your hardest enemy champions.",
                    "If you see one of your losing matchups, dodge or adjust your approach.",
                ],
            },
            {
                "title": "IMPROVING A CHAMPION",
                "lines": [
                    "Run: face Viego (or champion name)",
                    "Look for CRITICAL findings — these are your known losing patterns.",
                    "Run: face Viego worst for the blunt summary of what to stop doing.",
                    "Run: face Viego best for what to keep doing.",
                    "Compare the two to identify your personal improvement edges.",
                ],
            },
            {
                "title": "SCOUTING AN OPPONENT",
                "lines": [
                    "Run: face scout Name#TAG",
                    "Check their pool health and recent trends.",
                    "If they are on a declining trend, exploit the tilt.",
                    "If they have strong matchups against your pick, reconsider or adjust playstyle.",
                ],
            },
            {
                "title": "UNDERSTANDING A CHAMPION",
                "lines": [
                    "Run: face counter [champion]",
                    "Shows what beats them, what they have, and what items counter them.",
                    "Run: face intel [champion]",
                    "Full kit breakdown, threat window, and your personal matchup data if available.",
                ],
            },
            {
                "title": "MANAGING YOUR CACHE",
                "lines": [
                    "Run: face fetch 50",
                    "Pulls latest ranked games. Do this after every session.",
                    "Run: face fetch 50 --force",
                    "Rebuilds entire cache. Use if you suspect data corruption.",
                    "Run: face clean",
                    "Removes duplicates after force fetch. Safe to run anytime.",
                ],
            },
        ]
    }


def print_guide():
    data = analyze_guide()
    print(f"\n  {'='*60}")
    print(f"  VERDICT GUIDE")
    print(f"  {'='*60}\n")
    for section in data["sections"]:
        print(f"  {section['title']}")
        print(f"  {'─' * len(section['title'])}")
        for line in section["lines"]:
            print(f"  {line}")
        print()
    print(f"  {'='*60}")
    print()

# ─────────────────────────────────────────────
# BANS
# ─────────────────────────────────────────────

def analyze_bans(games):
    """Analyze ban recommendations. Returns structured dict with ban profiles and categories."""
    games_e = [g for g in games if g.enemy]
    total_losses = sum(1 for g in games_e if not g.win)

    if not games_e:
        return {"header": {"games_with_enemy": 0, "total_losses": 0},
                "profiles": [], "high_ban": [], "medium_ban": [], "low_ban": [],
                "insufficient_data": True}

    enemy_stats = defaultdict(lambda: {"games": 0, "losses": 0, "wins": 0})
    for g in games_e:
        ec = g.enemy.champion
        enemy_stats[ec]["games"] += 1
        if g.win:
            enemy_stats[ec]["wins"] += 1
        else:
            enemy_stats[ec]["losses"] += 1

    profiles = []
    for ec, stats in enemy_stats.items():
        if stats["games"] >= 3:
            profiles.append({
                "champion": ec, "games": stats["games"],
                "losses": stats["losses"], "wins": stats["wins"],
                "loss_rate": round(stats["losses"] / stats["games"] * 100, 1),
            })
    profiles.sort(key=lambda x: (-x["loss_rate"], -x["games"]))

    return {
        "header": {"games_with_enemy": len(games_e), "total_losses": total_losses},
        "profiles": profiles,
        "high_ban": [p for p in profiles if p["loss_rate"] >= 60],
        "medium_ban": [p for p in profiles if 50 <= p["loss_rate"] < 60],
        "low_ban": [p for p in profiles if p["loss_rate"] < 50],
        "insufficient_data": len(profiles) == 0,
    }


def print_bans(games):
    result = analyze_bans(games)
    h = result["header"]

    if h["games_with_enemy"] == 0:
        print("\n  No enemy matchup data found.")
        return

    if result["insufficient_data"]:
        print("\n  Not enough games to build ban recommendations (need 3+ games vs same champion).")
        print(f"  You have {h['games_with_enemy']} games with enemy data but no champion repeats 3+ times.")
        return

    print(f"\n  {'='*70}")
    print(f"  VERDICT BANS — Counter Pool Tracker")
    print(f"  {'='*70}")
    print(f"  {h['games_with_enemy']} games with enemy data  |  {h['total_losses']} total losses analyzed")
    print(f"  {'='*70}\n")

    if result["high_ban"]:
        print(f"  BAN THESE (60%+ loss rate)")
        print(f"  {'─'*70}")
        for p in result["high_ban"]:
            print(f"  {p['champion']:<18} {p['losses']}L / {p['games']}G  ({p['loss_rate']}% loss)")
        print()

    if result["medium_ban"]:
        print(f"  CONSIDER BANNING (50-59% loss rate)")
        print(f"  {'─'*70}")
        for p in result["medium_ban"]:
            print(f"  {p['champion']:<18} {p['losses']}L / {p['games']}G  ({p['loss_rate']}% loss)")
        print()

    if result["low_ban"]:
        print(f"  DON'T BAN — You beat these (<50% loss rate)")
        print(f"  {'─'*70}")
        for p in result["low_ban"][:5]:
            print(f"  {p['champion']:<18} {p['losses']}L / {p['games']}G  ({p['loss_rate']}% loss)")
        print()

    print(f"  {'─'*70}")
    print(f"  BAN PRIORITY SUMMARY")
    print(f"  {'─'*70}")
    if result["high_ban"]:
        top3 = result["high_ban"][:3]
        print(f"  Ban: {', '.join(p['champion'] for p in top3[:3])}")
        rates = ", ".join(f"{p['loss_rate']}%" for p in top3[:3])
        print(f"  Loss rates: {rates}")
        if len(result["high_ban"]) > 3:
            print(f"  ({len(result['high_ban']) - 3} more high-loss champions — run 'face matchups' for full list)")
    elif result["medium_ban"]:
        top = result["medium_ban"][0]
        print(f"  No 60%+ loss champions found. Consider: {top['champion']} ({top['loss_rate']}% loss)")
    else:
        print(f"  No problematic matchups found. You're winning against everyone in your pool.")

    print(f"\n  {'='*70}")
    print()

# ─────────────────────────────────────────────
# HEATMAP
# ─────────────────────────────────────────────

def analyze_heatmap(games):
    """Analyze time-of-game death distribution. Returns structured dict with buckets, phases, and recommendations."""
    all_deaths = []
    games_with_data = 0
    for g in games:
        death_mins = g.death_minutes
        if death_mins:
            all_deaths.extend(death_mins)
            games_with_data += 1

    if not all_deaths:
        return {"has_data": False, "games_with_data": games_with_data}

    bucket_size = 5
    buckets = {}
    for dm in all_deaths:
        bucket = (dm // bucket_size) * bucket_size
        buckets[bucket] = buckets.get(bucket, 0) + 1

    sorted_buckets = sorted(buckets.items())
    total_deaths = len(all_deaths)
    avg_per_bucket = total_deaths / len(buckets)
    max_deaths = max(buckets.values())
    peak_bucket = max(buckets.items(), key=lambda x: x[1])[0]
    dangerous = [(b, c) for b, c in sorted_buckets if c >= avg_per_bucket * 2 and c >= 3]

    # Phase breakdown
    early_deaths = sum(1 for dm in all_deaths if dm < 15)
    late_deaths = sum(1 for dm in all_deaths if dm >= 30)
    mid_deaths = total_deaths - early_deaths - late_deaths

    # Recommendations
    recommendations = []
    if early_deaths / total_deaths > 0.4:
        recommendations.append(f"{early_deaths}/{total_deaths} deaths ({early_deaths/total_deaths:.0%}) are pre-15min — prioritize early survival.")
    elif late_deaths / total_deaths > 0.4:
        recommendations.append(f"{late_deaths}/{total_deaths} deaths ({late_deaths/total_deaths:.0%}) are post-25min — avoid overextension in late game.")
    else:
        recommendations.append(f"Deaths spread across phases — {total_deaths} deaths total, no single phase dominates.")
    if dangerous:
        recommendations.append(f"Peak risk: {dangerous[0][0]}-{dangerous[0][0]+4} min ({len(dangerous)} concentrated death minutes).")

    return {
        "has_data": True,
        "games_with_data": games_with_data,
        "total_deaths": total_deaths,
        "buckets": [{"start": b, "end": b + bucket_size - 1, "count": c,
                      "pct": round(c / total_deaths * 100, 1), "is_peak": b == peak_bucket}
                     for b, c in sorted_buckets],
        "peak_bucket": peak_bucket,
        "peak_deaths": buckets[peak_bucket],
        "peak_pct": round(buckets[peak_bucket] / total_deaths * 100, 1),
        "max_deaths": max_deaths,
        "avg_per_bucket": avg_per_bucket,
        "dangerous": [{"start": b, "end": b + bucket_size - 1, "count": c,
                       "multiplier": round(c / avg_per_bucket, 1)} for b, c in dangerous],
        "phases": {
            "early": {"deaths": early_deaths, "pct": round(early_deaths / total_deaths * 100, 1)},
            "mid": {"deaths": mid_deaths, "pct": round(mid_deaths / total_deaths * 100, 1)},
            "late": {"deaths": late_deaths, "pct": round(late_deaths / total_deaths * 100, 1)},
        },
        "recommendations": recommendations,
    }


def print_heatmap(games):
    result = analyze_heatmap(games)

    if not result["has_data"]:
        print("\n  No death timeline data found.")
        print("  This feature requires games fetched with the latest update.")
        print(f"  Found {result['games_with_data']} games with death minute data.")
        return

    total = result["total_deaths"]
    gwd = result["games_with_data"]

    print(f"\n  {'='*70}")
    print(f"  VERDICT HEATMAP — Time-of-Game Death Analysis")
    print(f"  {'='*70}")
    print(f"  {total} total deaths across {gwd} games")
    print(f"  {'='*70}\n")

    print(f"  Death Distribution (5-minute buckets)")
    print(f"  {'─'*70}")
    for b in result["buckets"]:
        bar_len = min(int(b["count"] / result["max_deaths"] * 40), 40)
        bar = "█" * bar_len
        marker = " ← PEAK" if b["is_peak"] else ""
        print(f"  {b['start']:>2}-{b['end']:<2} min │{bar:<40} {b['count']:>3} ({b['pct']}%){marker}")
    print(f"  {'─'*70}\n")

    print(f"  KEY INSIGHTS")
    print(f"  {'─'*70}")
    print(f"  Peak danger zone: Minutes {result['peak_bucket']}-{result['peak_bucket'] + 4}")
    print(f"  ({result['peak_deaths']} deaths = {result['peak_pct']}% of all deaths)")
    print()

    if result["dangerous"]:
        print(f"  HIGH-RISK WINDOWS (2x+ above average):")
        for d in result["dangerous"]:
            print(f"  • Minutes {d['start']}-{d['end']}: You die {d['multiplier']}x more than average")
    else:
        max_mult = max(b["count"] / result["avg_per_bucket"] for b in result["buckets"])
        if max_mult >= 1.5:
            peak = result["buckets"][0]
            for b in result["buckets"]:
                if b["is_peak"]:
                    peak = b
                    break
            print(f"  Elevated risk: Minutes {peak['start']}-{peak['end']}")
            print(f"  You die {peak['count']/result['avg_per_bucket']:.1f}x more than your average 5-minute window.")
        else:
            print(f"  No clear danger zones — deaths are evenly distributed.")

    print()
    ph = result["phases"]
    print(f"  GAME PHASE BREAKDOWN")
    print(f"  {'─'*70}")
    print(f"  Early (0-14 min):   {ph['early']['deaths']:>3} deaths ({ph['early']['pct']}%)")
    print(f"  Mid (15-29 min):    {ph['mid']['deaths']:>3} deaths ({ph['mid']['pct']}%)")
    print(f"  Late (30+ min):     {ph['late']['deaths']:>3} deaths ({ph['late']['pct']}%)")
    print()

    print(f"  RECOMMENDATIONS")
    print(f"  {'─'*70}")
    for rec in result["recommendations"]:
        print(f"  • {rec}")

    print(f"\n  {'='*70}")
    print()

# ─────────────────────────────────────────────
# PATHING
# ─────────────────────────────────────────────

def analyze_pathing(games):
    """Analyze jungle pathing efficiency. Returns structured dict with clear timing, CS benchmarks, and recommendations."""
    jungle_games = [g for g in games if g.role == "JUNGLE" and g.jungle_pathing]
    total_jungle_games = len([g for g in games if g.role == "JUNGLE"])

    if not jungle_games:
        return {"has_data": False, "total_jungle_games": total_jungle_games}

    first_clears = []
    cs_at_5, cs_at_10, cs_at_15 = [], [], []
    for g in jungle_games:
        jp = g.jungle_pathing
        if jp.first_clear_min: first_clears.append(jp.first_clear_min)
        if jp.cs_at_5: cs_at_5.append(jp.cs_at_5)
        if jp.cs_at_10: cs_at_10.append(jp.cs_at_10)
        if jp.cs_at_15: cs_at_15.append(jp.cs_at_15)

    if not first_clears and not cs_at_5:
        return {"has_data": False, "total_jungle_games": total_jungle_games, "insufficient": True}

    avg_first_clear = _avg(first_clears)
    avg_cs_5 = _avg(cs_at_5)
    avg_cs_10 = _avg(cs_at_10)
    avg_cs_15 = _avg(cs_at_15)

    benchmarks = {5: (28, "6 camps"), 10: (56, "2 full clears"), 15: (84, "3 full clears")}

    cs_progression = []
    for time_key, cs_list in [(5, cs_at_5), (10, cs_at_10), (15, cs_at_15)]:
        if cs_list:
            a = _avg(cs_list)
            target, desc = benchmarks.get(time_key, (0, ""))
            diff = a - target
            status = "▲ Ahead" if diff >= 5 else ("→ On pace" if diff >= -5 else "▼ Behind")
            cs_progression.append({"time": time_key, "avg": a, "target": target, "status": status, "desc": desc})

    # Win/loss CS@15 comparison
    wins = [g for g in jungle_games if g.win]
    losses = [g for g in jungle_games if not g.win]
    win_loss_diff = None
    if wins and losses:
        win_cs_15 = _avg([g.jungle_pathing.cs_at_15 for g in wins if g.jungle_pathing.cs_at_15])
        loss_cs_15 = _avg([g.jungle_pathing.cs_at_15 for g in losses if g.jungle_pathing.cs_at_15])
        if win_cs_15 and loss_cs_15:
            win_loss_diff = {"win_cs_15": win_cs_15, "loss_cs_15": loss_cs_15, "diff": win_cs_15 - loss_cs_15}

    # Recommendations
    recommendations = []
    if avg_first_clear > 3.5:
        recommendations.append(f"First clear averages {avg_first_clear:.1f} min — target 3:15 for full clear.")
    if avg_cs_15 < 70:
        recommendations.append(f"CS@15 averages {avg_cs_15:.0f} — below 70 threshold. Farm more before ganking.")
    if avg_cs_15 >= 80:
        recommendations.append(f"CS@15 averages {avg_cs_15:.0f} — strong farm. Look for gank windows between camps.")

    return {
        "has_data": True, "insufficient": False,
        "jungle_games_with_data": len(jungle_games), "total_jungle_games": total_jungle_games,
        "first_clear": {
            "avg": avg_first_clear, "fast": len([x for x in first_clears if x <= 3]),
            "slow": len([x for x in first_clears if x >= 4]), "total": len(first_clears),
        } if first_clears else None,
        "cs_progression": cs_progression,
        "win_loss_diff": win_loss_diff,
        "recommendations": recommendations,
    }


def print_pathing(games):
    result = analyze_pathing(games)

    if not result["has_data"]:
        if result.get("insufficient"):
            print("\n  Insufficient pathing data for analysis.")
        else:
            print("\n  No jungle pathing data found.")
            print("  This feature requires jungle games fetched with the latest update.")
        return

    print(f"\n  {'='*70}")
    print(f"  VERDICT PATHING — Jungle Camp Efficiency")
    print(f"  {'='*70}")
    print(f"  {result['jungle_games_with_data']} games with pathing data  |  {result['total_jungle_games']} total jungle games")
    print(f"  {'='*70}\n")

    if result["first_clear"]:
        fc = result["first_clear"]
        print(f"  FIRST CLEAR TIMING")
        print(f"  {'─'*70}")
        print(f"  Average first clear complete: {fc['avg']} minutes")
        print(f"  Fast clears (≤3:00):  {fc['fast']} games ({round(fc['fast']/fc['total']*100, 1)}%)")
        print(f"  Slow clears (≥4:00): {fc['slow']} games ({round(fc['slow']/fc['total']*100, 1)}%)")
        if fc["avg"] <= 3.0:
            print(f"  ✓ Your first clear is efficient. You complete camps quickly.")
        elif fc["avg"] <= 3.5:
            print(f"  → Your first clear is average. Room for optimization.")
        else:
            print(f"  ⚠ Slow first clear detected. You're losing tempo early.")
        print()

    print(f"  CS PROGRESSION BENCHMARKS")
    print(f"  {'─'*70}")
    print(f"  {'Time':<12} {'Your Avg':<12} {'Target':<12} {'Status':<15}")
    print(f"  {'─'*70}")
    for cs in result["cs_progression"]:
        print(f"  @{cs['time']} min     {cs['avg']:<12.0f} {cs['target']:<12} {cs['status']:<15} ({cs['desc']})")
    print()

    if result["win_loss_diff"]:
        wld = result["win_loss_diff"]
        print(f"  WINS VS LOSSES COMPARISON")
        print(f"  {'─'*70}")
        print(f"  CS@15 in wins:   {wld['win_cs_15']:.0f} average")
        print(f"  CS@15 in losses: {wld['loss_cs_15']:.0f} average")
        if wld["diff"] > 10:
            print(f"  → You farm {wld['diff']:.0f} more CS by 15 min in wins. Early farm matters.")
        elif wld["diff"] > 0:
            print(f"  → Slight farm advantage in wins (+{wld['diff']:.0f} CS).")
        else:
            print(f"  → Farm is similar in wins/losses. Look for other factors.")
        print()

    print(f"  RECOMMENDATIONS")
    print(f"  {'─'*70}")
    for rec in result["recommendations"]:
        print(f"  • {rec}")

    print(f"\n  {'='*70}")
    print()


# ─────────────────────────────────────────────
# SCOUT
# ─────────────────────────────────────────────

def analyze_scout(games, player_id, riot_id):
    """Analyze an arbitrary player. Returns structured dict with pool, patterns, and recent games."""
    wins, losses = _split_by_result(games)
    wr = _winrate(games) or 0

    header = {
        "riot_id": riot_id,
        "total_games": len(games), "wins": len(wins), "losses": len(losses), "wr": wr,
    }

    # Champion pool
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g.champion].append(g)
    champ_rows = []
    for champ, cg in champ_games.items():
        cwr = _winrate(cg)
        if cwr is not None:
            champ_rows.append({"champion": champ, "games": len(cg), "wr": cwr})
    champ_rows.sort(key=lambda x: (-x["games"], -x["wr"]))

    # Synthesis-powered analysis
    loss_patterns = []
    win_patterns = []
    worst_items = []
    best_items = []
    bottom_line = None
    has_synthesis = False

    if len(games) >= 3:
        pairs = synthesize_games(games, player_id)
        if pairs:
            has_synthesis = True
            loss_patterns = mine_observations(pairs, result_filter="loss")
            win_patterns = mine_observations(pairs, result_filter="win")
            worst_data = worst_patterns(pairs)
            best_data = best_patterns(pairs)
            worst_items = worst_data["items"][:3]
            best_items = best_data["items"][:3]
            bottom_line = worst_data.get("bottom_line")

    # Recent games
    recent = []
    for i, g in enumerate(games[:10], 1):
        recent.append({
            "num": i, "champion": g.champion or "?",
            "result": "WIN" if g.win else "LOSS",
            "kda": f"{g.kills}/{g.deaths}/{g.assists}",
            "cs_per_min": g.cs_per_min,
            "dpm": g.damage_per_min,
        })

    return {
        "header": header, "champion_pool": champ_rows[:8],
        "has_synthesis": has_synthesis,
        "loss_patterns": loss_patterns[:4], "win_patterns": win_patterns[:4],
        "worst_items": worst_items, "best_items": best_items,
        "bottom_line": bottom_line,
        "recent_games": recent,
    }


def print_scout(games, player_id, riot_id):
    result = analyze_scout(games, player_id, riot_id)
    h = result["header"]

    print(f"\n  {'='*60}")
    print(f"  VERDICT SCOUT — {h['riot_id']}")
    print(f"  {'='*60}")
    print(f"  {h['total_games']} games  |  {h['wins']}W {h['losses']}L  |  {h['wr']}% WR")
    print(f"  {'='*60}\n")

    if result["champion_pool"]:
        print(f"  ── CHAMPION POOL ─────────────────────────────────────────────")
        print(f"  {'Champion':<16} {'Games':>6}  {'WR':>6}")
        print(f"  {'─'*38}")
        for c in result["champion_pool"]:
            print(f"  {c['champion']:<16} {c['games']:>6}  {c['wr']:>5}%")
        print()

    if result["has_synthesis"]:
        if result["loss_patterns"]:
            print(f"  ── LOSS PATTERNS ────────────────────────────────────────────")
            for pat in result["loss_patterns"]:
                print(f"  {pat['label'].title()}: {pat['count']} losses ({pat['pct']}%) — {pat['priority']}")
                for stmt in pat["statements"][:2]:
                    print(f"    → {stmt}")
            print()

        if result["win_patterns"]:
            print(f"  ── WIN PATTERNS ─────────────────────────────────────────────")
            for pat in result["win_patterns"]:
                print(f"  {pat['label'].title()}: {pat['count']} wins ({pat['pct']}%) — {pat['priority']}")
                for stmt in pat["statements"][:2]:
                    print(f"    → {stmt}")
            print()

        if result["worst_items"]:
            print(f"  ── WORST BUILDS ─────────────────────────────────────────────")
            for item_info in result["worst_items"]:
                print(f"  {item_info['item']}: {item_info['wr']}% WR across {item_info['games']} games")
            print()

        if result["best_items"]:
            print(f"  ── BEST BUILDS ─────────────────────────────────────────────")
            for item_info in result["best_items"]:
                print(f"  {item_info['item']}: {item_info['wr']}% WR across {item_info['games']} games")
            print()

        if result["bottom_line"]:
            print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
            for line in result["bottom_line"].split("\n"):
                print(f"  {line}")
            print()
    elif h["total_games"] >= 3:
        print(f"  Not enough data for synthesis analysis (need 3+ games with verdicts).\n")
    else:
        print(f"  Not enough games for pattern analysis (need 3+, have {h['total_games']}).\n")

    print(f"  ── RECENT GAMES ─────────────────────────────────────────────")
    print(f"  {'#':>3}  {'Champion':<14}  {'Result':>6}  {'KDA':>8}  {'CS/min':>7}  {'DPM':>5}")
    print(f"  {'─'*54}")
    for r in result["recent_games"]:
        print(f"  {r['num']:>3}  {r['champion']:<14}  {r['result']:>6}  {r['kda']:>8}  {r['cs_per_min']:>7.1f}  {r['dpm']:>5.0f}")
    print()


# ─────────────────────────────────────────────
# COMPARE
# ─────────────────────────────────────────────

def analyze_compare(my_games, my_pairs, my_engines, ref_games, ref_pairs, ref_engines, my_id, ref_id):
    """Compare two players. Returns structured dict with header, deltas, and bottom line."""
    data = compare_players(my_pairs, ref_pairs, my_engines, ref_engines, my_games, ref_games)
    return {
        "header": {
            "my_id": my_id, "ref_id": ref_id,
            "my_games": len(my_games), "ref_games": len(ref_games),
            "my_wr": _winrate(my_games) or 0, "ref_wr": _winrate(ref_games) or 0,
        },
        "observation_deltas": data["observation_deltas"],
        "distribution_deltas": data["distribution_deltas"],
        "bottom_line": data["bottom_line"],
    }


def print_compare(my_games, my_pairs, my_engines, ref_games, ref_pairs, ref_engines, my_id, ref_id):
    result = analyze_compare(my_games, my_pairs, my_engines, ref_games, ref_pairs, ref_engines, my_id, ref_id)
    h = result["header"]

    print(f"\n  {'='*60}")
    print(f"  VERDICT COMPARE")
    print(f"  {'='*60}")
    print(f"  You: {h['my_games']} games, {h['my_wr']}% WR")
    print(f"  Them: {h['ref_games']} games, {h['ref_wr']}% WR")
    print(f"  {'='*60}\n")

    if result["observation_deltas"]:
        print(f"  ── PATTERN DELTAS ───────────────────────────────────────────")
        for d in result["observation_deltas"][:6]:
            delta_sign = "+" if d["delta_pp"] > 0 else ""
            print(f"  {d['label'].title()}: You {d['my_pct']}% vs Them {d['ref_pct']}% ({delta_sign}{d['delta_pp']}pp)")
            if abs(d["delta_pp"]) >= 10:
                if d["delta_pp"] > 0:
                    print(f"    → You have this pattern significantly more often.")
                else:
                    print(f"    → They have this pattern significantly more often.")
            elif abs(d["delta_pp"]) < 5:
                print(f"    → Similar rate — not a key differentiator.")
        print()

    if result["distribution_deltas"]:
        print(f"  ── DISTRIBUTION DELTAS ─────────────────────────────────────")
        for d in result["distribution_deltas"][:6]:
            delta_sign = "+" if d["delta_median"] > 0 else ""
            pct_str = f" ({d['delta_pct']:+.0f}%)" if d.get("delta_pct") else ""
            print(f"  {d['label']}: You {d['my_median']:.1f} vs Them {d['ref_median']:.1f} ({delta_sign}{d['delta_median']:.1f}){pct_str}")
            if abs(d.get("delta_pct", 0)) >= 25:
                print(f"    → Large gap — this is a meaningful difference.")
            elif abs(d.get("delta_pct", 0)) >= 10:
                print(f"    → Moderate gap — worth noting.")
        print()

    print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
    for line in result["bottom_line"].split("\n"):
        print(f"  {line}")
    print()


# ─────────────────────────────────────────────
# RECENT — Match History
# ─────────────────────────────────────────────

QUEUE_LABELS = {420: "Solo/Duo", 440: "Flex"}


def analyze_recent(games, queue_filter=None, count=20, cache=None):
    """Analyze match history. Returns structured dict with game rows, streaks, and champion summary."""
    if queue_filter:
        filtered = [g for g in games if g.queue_id == queue_filter]
        queue_label = QUEUE_LABELS.get(queue_filter, "Ranked")
    else:
        filtered = list(games)
        queue_label = "All Ranked"

    if not filtered:
        return {"header": {"queue_label": queue_label, "empty": True}}

    show = filtered[:count]
    wins = sum(1 for g in show if g.win)
    losses = len(show) - wins
    wr = wins / len(show) * 100 if show else 0

    # Streak calculation
    streaks = []
    current_streak = 0
    current_type = None
    for g in show:
        w = g.win
        if current_type is None or w != current_type:
            if current_type is not None:
                streaks.append((current_type, current_streak))
            current_type = w
            current_streak = 1
        else:
            current_streak += 1
    if current_type is not None:
        streaks.append((current_type, current_streak))

    best_win = max((s for s in streaks if s[0]), key=lambda x: x[1], default=None)
    worst_loss = max((s for s in streaks if not s[0]), key=lambda x: x[1], default=None)

    cur = streaks[0] if streaks else None
    current_streak_str = f"{'W' if cur[0] else 'L'}{cur[1]} (current)" if cur else "—"
    best_w_str = f"W{best_win[1]}" if best_win else "—"
    worst_l_str = f"L{worst_loss[1]}" if worst_loss else "—"

    # Rank
    rank_str = ""
    if cache and cache.get("rank_history"):
        latest = cache["rank_history"][-1]
        for qname, qdata in latest.get("queues", {}).items():
            if queue_filter:
                qid_map = {"Solo/Duo": 420, "Flex": 440}
                if qid_map.get(qname) != queue_filter:
                    continue
            rank_str = f"{qdata.get('tier', '')} {qdata.get('rank', '')} {qdata.get('lp', 0)} LP"

    # Game rows
    rows = []
    for i, g in enumerate(show, 1):
        dmg = g.damage or 0
        rows.append({
            "num": i, "result": "W" if g.win else "L",
            "champion": (g.champion or "?")[:14],
            "kda": f"{g.kills}/{g.deaths}/{g.assists}",
            "cs": g.cs_final or 0,
            "cs_per_min": g.cs_per_min or 0,
            "damage": dmg, "damage_str": f"{dmg/1000:.1f}k" if dmg >= 1000 else str(dmg),
            "duration_min": g.duration_min or 0,
            "role": g.role or "?",
        })

    # Per-champion summary
    champ_stats = defaultdict(lambda: {"w": 0, "l": 0})
    for g in show:
        c = g.champion or "?"
        if g.win:
            champ_stats[c]["w"] += 1
        else:
            champ_stats[c]["l"] += 1

    champ_summary = []
    if len(show) >= 10 and len(champ_stats) > 1:
        champs_sorted = sorted(champ_stats.items(), key=lambda x: x[1]["w"] + x[1]["l"], reverse=True)[:8]
        champ_summary = [{"champion": c, "w": s["w"], "total": s["w"] + s["l"]} for c, s in champs_sorted]

    return {
        "header": {
            "queue_label": queue_label, "empty": False,
            "count": len(show), "wins": wins, "losses": losses, "wr": wr,
            "rank_str": rank_str,
            "current_streak": current_streak_str,
            "best_win_streak": best_w_str,
            "worst_loss_streak": worst_l_str,
        },
        "rows": rows,
        "champion_summary": champ_summary,
    }


def print_recent(games, queue_filter=None, count=20, cache=None):
    result = analyze_recent(games, queue_filter=queue_filter, count=count, cache=cache)
    h = result["header"]

    if h.get("empty"):
        print(f"\n  No {h['queue_label']} games found.\n")
        return

    header_text = f"Match History — {h['queue_label']}, last {h['count']}"
    if h["rank_str"]:
        header_text += f"  |  {h['rank_str']}"

    print(f"\n  {'='*64}")
    print(f"  {header_text}")
    print(f"  {'='*64}")
    print(f"  {'#':>3}  {'W/L':>4}  {'Champion':<14} {'KDA':>8}  {'CS':>5}  {'CS/m':>5}  {'Dmg':>6}  {'Min':>5}  {'Role':>7}")
    print(f"  {'─'*64}")

    for r in result["rows"]:
        print(f"  {r['num']:>3}  {r['result']:>4}  {r['champion']:<14} {r['kda']:>8}  {r['cs']:>5}  {r['cs_per_min']:>5.1f}  {r['damage_str']:>6}  {r['duration_min']:>5.1f}  {r['role']:>7}")

    print(f"  {'─'*64}")
    print(f"  Record: {h['wins']}W {h['losses']}L ({h['wr']:.0f}%)  |  Streak: {h['current_streak']}  |  Best: {h['best_win_streak']}  Worst: {h['worst_loss_streak']}")

    if result["champion_summary"]:
        champ_line = "  ".join(f"{c['champion']} {c['w']}/{c['total']}" for c in result["champion_summary"])
        print(f"  By champ: {champ_line}")

    print()


# ─────────────────────────────────────────────
# ENEMY — Live Enemy Scout
# ─────────────────────────────────────────────

SPECTATOR_ROLES = {
    "TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MID",
    "BOTTOM": "BOT", "UTILITY": "SUPPORT",
    "TOP_lane": "TOP", "JUNGLE_lane": "JUNGLE", "MID_lane": "MID",
    "BOT_lane": "BOT", "SUPPORT_lane": "SUPPORT",
}


def analyze_enemy(games, player_id, riot_id, champion=None, role=None, my_games=None, my_player_id=None):
    """Analyze enemy player for live scout. Returns structured dict with roles, weaknesses, and bottom line."""
    if not games or len(games) < 3:
        return {"has_data": False, "riot_id": riot_id}

    total = len(games)
    wins = sum(1 for g in games if g.win)
    wr = _winrate(games)

    # Role versatility
    role_counts = defaultdict(lambda: {"w": 0, "l": 0})
    for g in games:
        r = g.role or "?"
        if g.win:
            role_counts[r]["w"] += 1
        else:
            role_counts[r]["l"] += 1

    roles_sorted = sorted(role_counts.items(), key=lambda x: x[1]["w"] + x[1]["l"], reverse=True)
    primary_role, primary_stats = roles_sorted[0]
    primary_total = primary_stats["w"] + primary_stats["l"]

    if primary_total / total >= 0.7:
        role_line = f"{primary_role} main ({primary_total}/{total} games)"
    else:
        role_parts = [f"{r} {s['w']}/{s['w']+s['l']}" for r, s in roles_sorted[:3]]
        role_line = ", ".join(role_parts)

    best_role = max(roles_sorted, key=lambda x: x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1))
    best_total = best_role[1]["w"] + best_role[1]["l"]
    best_wr = best_role[1]["w"] / best_total * 100 if best_total else 0

    role_wr_line = ""
    if best_role[0] != primary_role or best_total != primary_total:
        role_wr_line = f" | Best: {best_role[0]} {best_wr:.0f}% WR"
    elif len(roles_sorted) > 1:
        role_wr_line = f" | Overall: {wr}% WR"

    # Synthesis
    weaknesses = []
    bottom_line = None
    pairs, engines = synthesize_games_with_engines(games, player_id)
    if pairs:
        loss_pairs = [(g, v) for g, v in pairs if not g.win]
        loss_obs = mine_observations(loss_pairs, result_filter="loss") if loss_pairs else []
        for obs in loss_obs[:3]:
            weaknesses.append({
                "label": obs.get("label", obs.get("obs_type", "?")).title(),
                "pct": obs.get("pct", 0),
                "count": obs.get("count", 0),
                "total_losses": len(loss_pairs),
                "statement": obs.get("statement", ""),
            })
        if loss_obs:
            top = loss_obs[0]
            obs_type = top.get("obs_type", "")
            label = top.get("label", obs_type).title()
            pct = top.get("pct", 0)
            action_map = {
                "death_cluster": f"Punish early deaths — {pct:.0f}% of their losses cluster.",
                "early_deaths": f"Invade early — {pct:.0f}% of losses have pre-15min deaths.",
                "inefficient_combat": f"They deal low damage per death — force fights, they lose trades.",
                "poor_farming": f"Out-farm them — they fall behind in gold by {pct:.0f}% of losses.",
                "countered": f"They were counter-picked and lost — draft advantage matters.",
                "blind_pick": f"They drafted blind and lost — early pick disadvantage.",
                "cs_deficit_early": f"They fall behind in CS early — pressure their lane.",
                "gold_deficit": f"They fall behind in gold by 15 — snowball your lead.",
                "vision_deficit": f"They ward sparingly — gank freely, they lack vision control.",
                "low_vision": f"They ward sparingly — gank freely, they lack vision control.",
                "no_dragon": f"They neglect objectives — take dragons/herald early.",
                "no_turret_pressure": f"They don't push towers — pressure their lanes.",
                "low_kp": f"They avoid fights — force skirmishes, they don't show up.",
            }
            advice = action_map.get(obs_type, f"Exploit their {label.lower()} pattern ({pct:.0f}% of losses).")
            bottom_line = {"weakness": label, "pct": pct, "advice": advice}

    # Stats comparison
    my_edge = None
    if my_games and len(my_games) >= 5:
        my_deaths = sum(g.deaths for g in my_games) / len(my_games)
        their_deaths = sum(g.deaths for g in games) / len(games)
        my_cs = sum(g.cs_per_min or 0 for g in my_games) / len(my_games)
        their_cs = sum(g.cs_per_min or 0 for g in games) / len(games)
        my_dpm = sum(g.damage_per_min or 0 for g in my_games) / len(my_games)
        their_dpm = sum(g.damage_per_min or 0 for g in games) / len(games)
        my_edge = {
            "deaths": {"me": my_deaths, "them": their_deaths},
            "cs_per_min": {"me": my_cs, "them": their_cs},
            "dpm": {"me": my_dpm, "them": their_dpm},
        }

    return {
        "has_data": True,
        "header": {
            "riot_id": riot_id, "champion": champion, "role": role,
            "total": total, "wins": wins, "wr": wr,
            "role_line": role_line, "role_wr_line": role_wr_line,
        },
        "weaknesses": weaknesses,
        "my_edge": my_edge,
        "bottom_line": bottom_line,
    }


def print_enemy(games, player_id, riot_id, champion=None, role=None, my_games=None, my_player_id=None):
    result = analyze_enemy(games, player_id, riot_id, champion=champion, role=role,
                           my_games=my_games, my_player_id=my_player_id)

    if not result["has_data"]:
        print(f"\n  Not enough data for {result['riot_id']} (need 3+ ranked games).\n")
        return

    h = result["header"]
    champ_str = f" vs {h['champion']}" if h["champion"] else ""
    role_str = f" ({h['role']})" if h["role"] else ""

    print(f"\n  {'='*58}")
    print(f"  VERDICT ENEMY{champ_str}{role_str}")
    print(f"  {'='*58}")
    print(f"  {h['riot_id']} | {h['total']} games | {h['wr']}% WR")
    print(f"  Role: {h['role_line']}{h['role_wr_line']}")
    print(f"  {'='*58}\n")

    if result["weaknesses"]:
        print(f"  ── WEAKNESSES ──────────────────────────────────────────────")
        for w in result["weaknesses"]:
            print(f"  → {w['label']}: {w['pct']:.0f}% of losses ({w['count']}/{w['total_losses']})")
            if w["statement"]:
                print(f"    {w['statement']}")
        print()

    if result["my_edge"]:
        e = result["my_edge"]
        print(f"  ── YOUR EDGE ───────────────────────────────────────────────")
        if e["deaths"]["me"] != e["deaths"]["them"]:
            delta = "fewer" if e["deaths"]["me"] < e["deaths"]["them"] else "more"
            print(f"  Deaths/game: You {e['deaths']['me']:.1f} vs Them {e['deaths']['them']:.1f} ({abs(e['deaths']['me'] - e['deaths']['them']):.1f} {delta})")
        if e["cs_per_min"]["me"] != e["cs_per_min"]["them"]:
            delta = "more" if e["cs_per_min"]["me"] > e["cs_per_min"]["them"] else "less"
            print(f"  CS/min: You {e['cs_per_min']['me']:.1f} vs Them {e['cs_per_min']['them']:.1f} ({abs(e['cs_per_min']['me'] - e['cs_per_min']['them']):.1f} {delta})")
        if abs(e["dpm"]["me"] - e["dpm"]["them"]) > 50:
            delta = "more" if e["dpm"]["me"] > e["dpm"]["them"] else "less"
            print(f"  DPM: You {e['dpm']['me']:.0f} vs Them {e['dpm']['them']:.0f} ({abs(e['dpm']['me'] - e['dpm']['them']):.0f} {delta})")
        print()

    if result["bottom_line"]:
        bl = result["bottom_line"]
        print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
        print(f"  Their biggest weakness: {bl['weakness']} ({bl['pct']:.0f}% of losses).")
        print(f"  {bl['advice']}")
        print()