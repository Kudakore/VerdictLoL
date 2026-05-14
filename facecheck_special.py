"""
FaceCheck Special — Specialized mode handlers.

Matchups, guide, bans, heatmap, pathing, and select interface.
"""

import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from facecheck_data import get_ranked_games, get_current_rank_string
from facecheck_display import ROLE_LABELS, enemy_role_label, print_full_game
from facecheck_aggregate import synthesize_games, mine_observations, worst_patterns, best_patterns, compare_players, _winrate, _split_by_result

# Champion Intelligence — optional, graceful fallback
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

# ─────────────────────────────────────────────
# GUIDE
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# BANS
# ─────────────────────────────────────────────

def print_bans(games):
    """
    Counter pool tracker — Shows which enemy champions to ban based on actual loss rates.
    Output format: "Ban Warwick (67% loss), not Viego (45% loss)"
    """
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
        games_count = stats["games"]
        if games_count >= 3:
            loss_rate = round(stats["losses"] / games_count * 100, 1)
            ban_profiles.append({
                "champion": ec,
                "games": games_count,
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
            games_count = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games_count}G  ({lr}% loss)")
        print()

    # ── MEDIUM PRIORITY (50-59% loss rate) ───────────────────────────
    if medium_ban:
        print(f"  CONSIDER BANNING (50-59% loss rate)")
        print(f"  {'─'*70}")
        for p in medium_ban:
            ec = p["champion"]
            losses = p["losses"]
            games_count = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games_count}G  ({lr}% loss)")
        print()

    # ── DON'T BAN (<50% loss rate) ───────────────────────────────────
    if low_ban:
        print(f"  DON'T BAN — You beat these (<50% loss rate)")
        print(f"  {'─'*70}")
        for p in low_ban[:5]:  # Show top 5
            ec = p["champion"]
            losses = p["losses"]
            games_count = p["games"]
            lr = p["loss_rate"]
            print(f"  {ec:<18} {losses}L / {games_count}G  ({lr}% loss)")
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

# ─────────────────────────────────────────────
# HEATMAP
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# PATHING
# ─────────────────────────────────────────────

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

    print(f"\n  {'='*70}")
    print()


# ─────────────────────────────────────────────
# SCOUT
# ─────────────────────────────────────────────

def print_scout(games, player_id, riot_id):
    """
    Display scout analysis for an arbitrary player.
    Uses the full synthesis pipeline: observations, worst/best patterns, champion pool.
    """
    wins, losses = _split_by_result(games)
    wr = _winrate(games) or 0

    print(f"\n  {'='*60}")
    print(f"  FACECHECK SCOUT — {riot_id}")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    print(f"  {'='*60}\n")

    # Champion pool
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    champ_rows = []
    for champ, cg in champ_games.items():
        cwr = _winrate(cg)
        if cwr is not None:
            champ_rows.append((champ, len(cg), cwr))
    champ_rows.sort(key=lambda x: (-x[1], -x[2]))
    if champ_rows:
        print(f"  ── CHAMPION POOL ─────────────────────────────────────────────")
        print(f"  {'Champion':<16} {'Games':>6}  {'WR':>6}")
        print(f"  {'─'*38}")
        for champ, n, cwr in champ_rows[:8]:
            print(f"  {champ:<16} {n:>6}  {cwr:>5}%")
        print()

    # Synthesis-powered analysis
    if len(games) >= 3:
        pairs = synthesize_games(games, player_id)
        if pairs:
            # Observation patterns (combined wins + losses)
            all_patterns = mine_observations(pairs)
            loss_patterns = mine_observations(pairs, result_filter="loss")
            win_patterns = mine_observations(pairs, result_filter="win")

            if loss_patterns:
                print(f"  ── LOSS PATTERNS ────────────────────────────────────────────")
                for pat in loss_patterns[:4]:
                    print(f"  {pat['label'].title()}: {pat['count']} losses ({pat['pct']}%) — {pat['priority']}")
                    for stmt in pat["statements"][:2]:
                        print(f"    → {stmt}")
                print()

            if win_patterns:
                print(f"  ── WIN PATTERNS ─────────────────────────────────────────────")
                for pat in win_patterns[:4]:
                    print(f"  {pat['label'].title()}: {pat['count']} wins ({pat['pct']}%) — {pat['priority']}")
                    for stmt in pat["statements"][:2]:
                        print(f"    → {stmt}")
                print()

            # Worst/best items and champions
            worst_data = worst_patterns(pairs)
            best_data = best_patterns(pairs)

            if worst_data["items"]:
                print(f"  ── WORST BUILDS ─────────────────────────────────────────────")
                for item_info in worst_data["items"][:3]:
                    print(f"  {item_info['item']}: {item_info['wr']}% WR across {item_info['games']} games")
                print()

            if best_data["items"]:
                print(f"  ── BEST BUILDS ─────────────────────────────────────────────")
                for item_info in best_data["items"][:3]:
                    print(f"  {item_info['item']}: {item_info['wr']}% WR across {item_info['games']} games")
                print()

            # Bottom line
            if worst_data.get("bottom_line"):
                print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
                for line in worst_data["bottom_line"].split("\n"):
                    print(f"  {line}")
                print()
        else:
            print(f"  Not enough data for synthesis analysis (need 3+ games with verdicts).\n")
    else:
        print(f"  Not enough games for pattern analysis (need 3+, have {len(games)}).\n")

    # Recent games
    print(f"  ── RECENT GAMES ─────────────────────────────────────────────")
    print(f"  {'#':>3}  {'Champion':<14}  {'Result':>6}  {'KDA':>8}  {'CS/min':>7}  {'DPM':>5}")
    print(f"  {'─'*54}")
    for i, g in enumerate(games[:10], 1):
        result = "WIN" if g.get("win") else "LOSS"
        kda = f"{g.get('kills',0)}/{g.get('deaths',0)}/{g.get('assists',0)}"
        cs_min = g.get("cs_per_min", 0)
        dpm = g.get("damage_per_min", 0)
        print(f"  {i:>3}  {g.get('champion','?'):<14}  {result:>6}  {kda:>8}  {cs_min:>7.1f}  {dpm:>5.0f}")
    print()


# ─────────────────────────────────────────────
# COMPARE
# ─────────────────────────────────────────────

def print_compare(my_games, my_pairs, my_engines, ref_games, ref_pairs, ref_engines, my_id, ref_id):
    """
    Display delta comparison between your patterns and a reference player's.
    Shows observation rate deltas and distribution deltas.
    """
    my_wr = _winrate(my_games) or 0
    ref_wr = _winrate(ref_games) or 0

    print(f"\n  {'='*60}")
    print(f"  FACECHECK COMPARE")
    print(f"  {'='*60}")
    print(f"  You: {len(my_games)} games, {my_wr}% WR")
    print(f"  Them: {len(ref_games)} games, {ref_wr}% WR")
    print(f"  {'='*60}\n")

    data = compare_players(my_pairs, ref_pairs, my_engines, ref_engines, my_games, ref_games)

    # Observation deltas
    if data["observation_deltas"]:
        print(f"  ── PATTERN DELTAS ───────────────────────────────────────────")
        for d in data["observation_deltas"][:6]:
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

    # Distribution deltas
    if data["distribution_deltas"]:
        print(f"  ── DISTRIBUTION DELTAS ─────────────────────────────────────")
        for d in data["distribution_deltas"][:6]:
            delta_sign = "+" if d["delta_median"] > 0 else ""
            pct_str = f" ({d['delta_pct']:+.0f}%)" if d.get("delta_pct") else ""
            print(f"  {d['label']}: You {d['my_median']:.1f} vs Them {d['ref_median']:.1f} ({delta_sign}{d['delta_median']:.1f}){pct_str}")
            if abs(d.get("delta_pct", 0)) >= 25:
                print(f"    → Large gap — this is a meaningful difference.")
            elif abs(d.get("delta_pct", 0)) >= 10:
                print(f"    → Moderate gap — worth noting.")
        print()

    # Bottom line
    print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
    for line in data["bottom_line"].split("\n"):
        print(f"  {line}")
    print()


# ─────────────────────────────────────────────
# RECENT — Match History
# ─────────────────────────────────────────────

QUEUE_LABELS = {420: "Solo/Duo", 440: "Flex"}


def print_recent(games, queue_filter=None, count=20, cache=None):
    """
    Display match history — pure facts, no synthesis.
    Queue filter: 420 (solo), 440 (flex), or None (all ranked).
    """
    if queue_filter:
        filtered = [g for g in games if g.get("queue_id") == queue_filter]
        queue_label = QUEUE_LABELS.get(queue_filter, "Ranked")
    else:
        filtered = list(games)
        queue_label = "All Ranked"

    if not filtered:
        print(f"\n  No {queue_label} games found.\n")
        return

    show = filtered[:count]
    wins = sum(1 for g in show if g.get("win"))
    losses = len(show) - wins
    wr = wins / len(show) * 100 if show else 0

    # Streak calculation
    streaks = []
    current_streak = 0
    current_type = None
    for g in show:
        w = g.get("win")
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

    # Current streak (first game is most recent)
    cur = streaks[0] if streaks else None
    if cur:
        streak_type = "W" if cur[0] else "L"
        streak_str = f"{streak_type}{cur[1]} (current)"
    else:
        streak_str = "—"

    best_w_str = f"W{best_win[1]}" if best_win else "—"
    worst_l_str = f"L{worst_loss[1]}" if worst_loss else "—"

    # Rank display
    rank_str = ""
    if cache and cache.get("rank_history"):
        latest = cache["rank_history"][-1]
        for qname, qdata in latest.get("queues", {}).items():
            if queue_filter:
                qid_map = {"Solo/Duo": 420, "Flex": 440}
                if qid_map.get(qname) != queue_filter:
                    continue
            rank_str = f"{qdata.get('tier', '')} {qdata.get('rank', '')} {qdata.get('lp', 0)} LP"

    header = f"Match History — {queue_label}, last {len(show)}"
    if rank_str:
        header += f"  |  {rank_str}"

    print(f"\n  {'='*64}")
    print(f"  {header}")
    print(f"  {'='*64}")
    print(f"  {'#':>3}  {'W/L':>4}  {'Champion':<14} {'KDA':>8}  {'CS':>5}  {'CS/m':>5}  {'Dmg':>6}  {'Min':>5}  {'Role':>7}")
    print(f"  {'─'*64}")

    for i, g in enumerate(show, 1):
        result = "W" if g.get("win") else "L"
        champ = g.get("champion", "?")[:14]
        kda = f"{g.get('kills',0)}/{g.get('deaths',0)}/{g.get('assists',0)}"
        cs = g.get("cs_final", 0) or 0
        cs_m = g.get("cs_per_min", 0) or 0
        dmg = g.get("damage", 0) or 0
        dur = g.get("duration_min", 0) or 0
        role = g.get("role", "?")

        # Format damage
        if dmg >= 1000:
            dmg_str = f"{dmg/1000:.1f}k"
        else:
            dmg_str = str(dmg)

        print(f"  {i:>3}  {result:>4}  {champ:<14} {kda:>8}  {cs:>5}  {cs_m:>5.1f}  {dmg_str:>6}  {dur:>5.1f}  {role:>7}")

    # Footer
    print(f"  {'─'*64}")
    print(f"  Record: {wins}W {losses}L ({wr:.0f}%)  |  Streak: {streak_str}  |  Best: {best_w_str}  Worst: {worst_l_str}")

    # Per-champion summary if showing enough games
    champ_stats = defaultdict(lambda: {"w": 0, "l": 0})
    for g in show:
        c = g.get("champion", "?")
        if g.get("win"):
            champ_stats[c]["w"] += 1
        else:
            champ_stats[c]["l"] += 1

    if len(show) >= 10 and len(champ_stats) > 1:
        champs_sorted = sorted(champ_stats.items(), key=lambda x: x[1]["w"] + x[1]["l"], reverse=True)[:8]
        champ_line = "  ".join(f"{c} {s['w']}/{s['w']+s['l']}" for c, s in champs_sorted)
        print(f"  By champ: {champ_line}")

    print()