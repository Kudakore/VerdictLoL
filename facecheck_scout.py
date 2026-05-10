"""
FaceCheck Scout — run full diagnosis on any player by Name#TAG
Fetches their recent ranked games live and runs the analysis engine.
No timeline data (too slow) — uses match endpoint only.
"""

import requests
import json
import sys
import time
import re
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────
# CONFIG — reads API key from facecheck_data.py automatically
# ─────────────────────────────────────────────────────────────────

import os
sys.path.insert(0, "C:\\Scripts")
from facecheck_game import print_matchups

try:
    import facecheck_data as fd
    API_KEY = fd.API_KEY
    REGION  = fd.REGION
    PLATFORM = fd.PLATFORM
except Exception as e:
    print(f"Error loading facecheck_data config: {e}")
    sys.exit(1)

HEADERS = {"X-Riot-Token": API_KEY}
QUEUE_FILTERS = [420, 440]
QUEUE_NAMES   = {420: "Ranked Solo/Duo", 440: "Ranked Flex"}

_last_call = 0

def rl_get(url, delay=0.5):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_call = time.time()
    r = requests.get(url, headers=HEADERS, timeout=10)
    return r

# ─────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────

def get_puuid_by_riot_id(game_name, tag_line):
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    r = rl_get(url)
    if r.status_code != 200:
        print(f"  Error fetching account: HTTP {r.status_code}")
        return None
    return r.json().get("puuid")

def get_match_ids(puuid, count=20):
    ids = []
    for qid in QUEUE_FILTERS:
        url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={qid}&count={count}"
        r = rl_get(url)
        if r.status_code == 200:
            ids.extend(r.json())
    return sorted(list(dict.fromkeys(ids)), reverse=True)

def get_match(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    r = rl_get(url, delay=0.4)
    if r.status_code == 200:
        return r.json()
    return None

def build_scout_record(match, puuid):
    """Lightweight record from match data only (no timeline)."""
    info = match["info"]
    my_stats = next((p for p in info["participants"] if p["puuid"] == puuid), None)
    if not my_stats:
        return None

    my_team_id = my_stats["teamId"]
    my_role    = my_stats.get("teamPosition", "")
    duration   = info["gameDuration"] / 60

    enemy = next(
        (p for p in info["participants"]
         if p["teamId"] != my_team_id and p.get("teamPosition") == my_role),
        None
    )

    cs    = my_stats["totalMinionsKilled"] + my_stats["neutralMinionsKilled"]
    dmg   = my_stats["totalDamageDealtToChampions"]
    gold  = my_stats["goldEarned"]
    vis   = my_stats["visionScore"]

    # Final items (no component filtering without item data — just list them)
    items = [my_stats.get(f"item{i}", 0) for i in range(6)]
    items = [i for i in items if i != 0]

    # Team objectives
    my_obj = {}
    en_obj = {}
    for team in info.get("teams", []):
        obj = team.get("objectives", {})
        target = my_obj if team["teamId"] == my_team_id else en_obj
        target["dragon_kills"]  = obj.get("dragon",  {}).get("kills", 0)
        target["baron_kills"]   = obj.get("baron",   {}).get("kills", 0)
        target["tower_kills"]   = obj.get("tower",   {}).get("kills", 0)
        target["first_blood"]   = obj.get("champion",{}).get("first", False)
        target["first_dragon"]  = obj.get("dragon",  {}).get("first", False)

    my_team_kills  = sum(p["kills"]  for p in info["participants"] if p["teamId"] == my_team_id)
    my_team_deaths = sum(p["deaths"] for p in info["participants"] if p["teamId"] == my_team_id)

    return {
        "match_id":       match["metadata"]["matchId"],
        "queue":          QUEUE_NAMES.get(info["queueId"], f"Queue {info['queueId']}"),
        "queue_id":       info["queueId"],
        "win":            my_stats["win"],
        "champion":       my_stats["championName"],
        "role":           my_role,
        "duration_min":   round(duration, 1),
        "kills":          my_stats["kills"],
        "deaths":         my_stats["deaths"],
        "assists":        my_stats["assists"],
        "cs_final":       cs,
        "cs_per_min":     round(cs / duration, 1) if duration > 0 else 0,
        "damage":         dmg,
        "damage_per_min": round(dmg / duration, 0) if duration > 0 else 0,
        "vision":         vis,
        "vision_per_min": round(vis / duration, 2) if duration > 0 else 0,
        "gold":           gold,
        "gold_per_min":   round(gold / duration, 0) if duration > 0 else 0,
        # Stubs for fields analysis modules expect
        "cs_10":          None,
        "cs_15":          None,
        "early_deaths":   0,
        "gold_15":        None,
        "gold_lead_15":   None,
        "killed_by_enemy_jungler": 0,
        "control_wards":  my_stats.get("detectorWardsPlaced", 0),
        "wards_placed":   my_stats.get("wardsPlaced", 0),
        "first_blood_kill": my_stats.get("firstBloodKill", False),
        "turret_kills":   my_stats.get("turretKills", 0),
        "largest_killing_spree": my_stats.get("largestKillingSpree", 0),
        "first_item":     None,
        "build_order":    [],
        "final_items":    items,
        "pick_order":     None,
        "enemy_pick_order": None,
        "enemy": {
            "champion": enemy["championName"],
            "kills":    enemy["kills"],
            "deaths":   enemy["deaths"],
            "assists":  enemy["assists"],
            "cs":       enemy["totalMinionsKilled"] + enemy["neutralMinionsKilled"],
            "damage":   enemy["totalDamageDealtToChampions"],
            "gold":     enemy["goldEarned"],
            "win":      enemy["win"],
        } if enemy else None,
        "my_team": {
            "kills":        my_team_kills,
            "deaths":       my_team_deaths,
            **my_obj,
        },
        "enemy_team": en_obj,
        "all_players": [],
    }

# ─────────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────────

def fmt_k(n):
    if n is None: return "N/A"
    return f"{int(n):,}"

def analyze_role_distribution(games):
    """Return role distribution as list of (role, count, pct, wr)."""
    role_games = defaultdict(list)
    for g in games:
        role = g.get("role", "UNKNOWN")
        if role:
            role_games[role].append(g)

    if len(role_games) <= 1:
        return []  # Single role, don't show

    total = len(games)
    result = []
    for role, gs in sorted(role_games.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(gs)
        pct = round(count / total * 100, 1)
        wr = round(sum(1 for g in gs if g["win"]) / count * 100, 1) if gs else 0
        result.append((role, count, pct, wr))
    return result


def analyze_cs_by_role(games):
    """Return CS metrics per role. Key for jungle camp efficiency."""
    role_cs = defaultdict(lambda: {"my_cs": [], "enemy_cs": [], "diff": []})

    for g in games:
        role = g.get("role")
        if not role:
            continue

        my_cs = g.get("cs_final", 0)
        enemy = g.get("enemy", {})
        enemy_cs = enemy.get("cs", 0) if isinstance(enemy, dict) else 0

        role_cs[role]["my_cs"].append(my_cs)
        role_cs[role]["enemy_cs"].append(enemy_cs)
        role_cs[role]["diff"].append(my_cs - enemy_cs)

    result = {}
    for role, data in role_cs.items():
        if len(data["my_cs"]) >= 3:
            from facecheck_analysis import robust_avg
            result[role] = {
                "games": len(data["my_cs"]),
                "my_cs_avg": robust_avg(data["my_cs"]),
                "enemy_cs_avg": robust_avg(data["enemy_cs"]),
                "diff_avg": robust_avg(data["diff"]),
            }
    return result


def print_slim_scout(riot_id, games, findings, extra=None):
    """Slim scout output — champion pool, role distribution, CS efficiency, recent form."""
    if extra is None:
        extra = {}
    from facecheck_analysis import winrate

    wins = [g for g in games if g["win"]]
    losses = [g for g in games if not g["win"]]
    wr = round(len(wins) / len(games) * 100, 1) if games else 0

    # Streak detection
    games_sorted = sorted(games, key=lambda g: g.get("match_id", ""), reverse=True)
    streak_type = None
    streak_len = 0
    for g in games_sorted:
        if streak_type is None:
            streak_type = "W" if g["win"] else "L"
            streak_len = 1
        elif (g["win"] and streak_type == "W") or (not g["win"] and streak_type == "L"):
            streak_len += 1
        else:
            break
    streak_str = f" | {streak_len}-Game {'Win' if streak_type == 'W' else 'Loss'} Streak" if streak_len >= 3 else ""

    print(f"\n  {'='*62}")
    print(f"  FACECHECK SCOUT — {riot_id}")
    print(f"  {'='*62}")
    rank = extra.get("rank", "")
    if rank:
        print(f"  Rank: {rank}")
        print(f"  {'─'*62}")
    print(f"  {len(games)} games | {len(wins)}W {len(losses)}L | {wr}% WR{streak_str}")
    print(f"  {'='*62}\n")

    # ── CHAMPION POOL ─────────────────────────────────────────────
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)

    champ_summary = sorted(
        [(c, len(gs), round(sum(1 for g in gs if g["win"]) / len(gs) * 100, 1))
         for c, gs in champ_games.items()],
        key=lambda x: x[1], reverse=True  # Sort by games played
    )[:5]  # Top 5 only

    if champ_summary:
        print(f"  CHAMPION POOL")
        print(f"  {'─'*58}")
        for champ, n, cwr in champ_summary:
            indicator = "↑" if cwr >= 55 else ("↓" if cwr <= 40 else "→")
            primary = "★" if n == champ_summary[0][1] else " "
            print(f"  {primary} {champ:<15} {n:>2}g  {cwr:>5}% WR  {indicator}")
        print()

    # ── ROLE DISTRIBUTION ──────────────────────────────────────────
    role_dist = analyze_role_distribution(games)
    if role_dist:
        print(f"  ROLE DISTRIBUTION")
        print(f"  {'─'*58}")
        for role, count, pct, role_wr in role_dist:
            bar = "█" * int(pct / 5)  # 20 chars = 100%
            print(f"  {role:<10} {bar:<20} {pct:>5}% ({count}g, {role_wr}% WR)")
        print()

    # ── CS EFFICIENCY (JUNGLE ONLY) ───────────────────────────────
    cs_by_role = analyze_cs_by_role(games)
    # Only show camp clearing analysis for jungle mains
    if cs_by_role and "JUNGLE" in cs_by_role:
        jungle_data = cs_by_role["JUNGLE"]
        # Only show if majority of games are jungle
        total_games = len(games)
        jungle_games = jungle_data["games"]
        if jungle_games / total_games >= 0.5:
            print(f"  CS EFFICIENCY — When Playing Jungle")
            print(f"  {'─'*58}")
            print(f"  {'Games':<8} {'Your CS':<12} {'Enemy CS':<12} {'Diff':<10} {'Status'}")
            print(f"  {'─'*58}")
            diff = jungle_data["diff_avg"]
            diff_str = f"+{diff:.0f}" if diff and diff > 0 else f"{diff:.0f}" if diff else "N/A"
            status = "▲ Farming" if diff and diff > 20 else ("▼ Behind" if diff and diff < -20 else "→ Even")
            print(f"  {jungle_data['games']:<8} {jungle_data['my_cs_avg']:<12.0f} {jungle_data['enemy_cs_avg']:<12.0f} {diff_str:<10} {status}")
            print(f"\n  Note: CS = camps cleared. High CS junglers control the map through")
            print(f"  efficient clearing. Low CS = gank-heavy, counter-jungle vulnerable.")
            print()

    # ── RECENT FORM ────────────────────────────────────────────────
    recent = games_sorted[:10]
    if recent:
        recent_wins = sum(1 for g in recent if g["win"])
        recent_wr = round(recent_wins / len(recent) * 100, 1)
        baseline = wr
        trend = recent_wr - baseline
        trend_str = f"+{trend:.0f}%" if trend > 0 else f"{trend:.0f}%"

        print(f"  RECENT FORM (Last {len(recent)} Games)")
        print(f"  {'─'*58}")
        print(f"  Record: {recent_wins}W {len(recent)-recent_wins}L | WR: {recent_wr}% | Trend: {trend_str} vs baseline")

        # Show last 5 results as W/L indicators
        last5 = ["W" if g["win"] else "L" for g in recent[:5]]
        print(f"  Last 5: {' '.join(last5)}")

        # Recent CS trend
        recent_cs = [g.get("cs_final", 0) for g in recent if g.get("cs_final")]
        if recent_cs:
            from facecheck_analysis import robust_avg
            recent_cs_avg = robust_avg(recent_cs)
            print(f"  Recent CS avg: {recent_cs_avg:.0f}/game")
        print()

    # ── TOP FINDINGS ─────────────────────────────────────────────
    primary = [f for f in findings if f.get("control_level") == "direct" and f.get("confidence_label") in ("CRITICAL", "CLEAR")]
    primary.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    if primary:
        print(f"  KEY INSIGHTS")
        print(f"  {'─'*58}")
        for f in primary[:3]:
            atype = f.get("action_type", "").upper().replace("_", " ")
            title = f.get("title", f["type"])
            print(f"  • [{atype}] {title}")
        print()

    # ── RECENT GAMES TABLE ─────────────────────────────────────────
    print(f"  RECENT GAMES")
    print(f"  {'─'*58}")
    print(f"  {'#':<4} {'Champion':<14} {'Result':<6} {'KDA':<10} {'Role':<8} {'CS':<5} {'Gold':<8} {'Queue':<15}")
    print(f"  {'─'*58}")
    for i, g in enumerate(games_sorted[:10], 1):
        result = "WIN" if g["win"] else "LOSS"
        kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
        role = g.get("role", "")[:7]
        gold = fmt_k(g.get("gold", 0))
        queue_short = g.get("queue", "").replace("Ranked ", "")[:14]
        print(f"  {i:<4} {g['champion']:<14} {result:<6} {kda:<10} {role:<8} {g.get('cs_final', 0):<5} {gold:<8} {queue_short:<15}")
    print()


def print_scout_diagnosis(riot_id, games, findings):
    """Full verbose scout output (deprecated, use print_slim_scout)."""
    print_slim_scout(riot_id, games, findings)


def print_slim_matchups(games):
    """Show only worst 3 matchups — slim version for scout."""
    from collections import defaultdict
    from facecheck_analysis import robust_avg

    games_e = [g for g in games if g.get("enemy")]
    if not games_e:
        return

    enemy_profiles = defaultdict(lambda: {
        "games": [], "wins": [], "losses": [],
        "cs_diff": [], "damage_diff": [], "kill_diff": [],
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

        p["cs_diff"].append(cs_diff)
        p["damage_diff"].append(dmg_diff)
        p["kill_diff"].append(kill_diff)
        p["killed_by"].append(g.get("killed_by_enemy_jungler", 0))

        if g["win"]:
            p["wins"].append(g)
        else:
            p["losses"].append(g)

    def avg(lst):
        lst = [v for v in lst if v is not None]
        return round(sum(lst) / len(lst), 1) if lst else 0

    profiles = []
    for ec, p in enemy_profiles.items():
        if len(p["games"]) < 3:
            continue
        wr = round(len(p["wins"]) / len(p["games"]) * 100, 1)
        profiles.append({
            "champion": ec, "games": len(p["games"]),
            "wins": len(p["wins"]), "losses": len(p["losses"]), "wr": wr,
            "cs_diff": avg(p["cs_diff"]), "dmg_diff": avg(p["damage_diff"]),
            "kill_diff": avg(p["kill_diff"]), "killed_by": avg(p["killed_by"]),
        })

    if not profiles:
        return

    # Sort by winrate ascending (worst first), take top 3
    profiles.sort(key=lambda x: x["wr"])
    worst = profiles[:3]

    print(f"\n  {'─'*58}")
    print(f"  WORST MATCHUPS")
    print(f"  {'─'*58}")
    print(f"  {'Champion':<14} {'Record':<10} {'WR':<7} {'CS Diff':<10} {'Note'}")
    print(f"  {'─'*58}")

    for p in worst:
        ec = p["champion"]
        note = ""
        if p["cs_diff"] > 0 and p["wr"] <= 40:
            note = "Farm ahead, lose fights"
        elif p["cs_diff"] < -20:
            note = "Getting out-farmed"
        elif p["killed_by"] >= 1.5:
            note = "They're finding you"
        elif p["dmg_diff"] < -3000:
            note = "Out-dueled in skirmishes"
        else:
            note = "Consistent losses"

        cs_str = f"{p['cs_diff']:+.0f}"
        print(f"  {ec:<14} {p['wins']}W {p['losses']}L     {p['wr']:<6}% {cs_str:<10} {note}")
    print()


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

ROLE_ALIASES = {
    "jungle": "JUNGLE", "jg": "JUNGLE", "jng": "JUNGLE",
    "top": "TOP",
    "mid": "MIDDLE", "middle": "MIDDLE",
    "bot": "BOTTOM", "bottom": "BOTTOM", "adc": "BOTTOM", "carry": "BOTTOM",
    "support": "UTILITY", "sup": "UTILITY", "supp": "UTILITY",
}

def run_scout(riot_id, count=20, role_filter=None):
    if "#" not in riot_id:
        print(f"  Invalid format. Use: Name#TAG  (e.g. Kuda#MIST)")
        sys.exit(1)

    game_name, tag_line = riot_id.split("#", 1)

    print(f"\n  Scouting {riot_id}...")
    print(f"  Fetching account data...")
    puuid = get_puuid_by_riot_id(game_name, tag_line)
    if not puuid:
        print(f"  Player not found: {riot_id}")
        sys.exit(1)

    # Fetch rank
    rank_snapshot = fd.get_rank_snapshot(puuid)
    rank_str = fd.get_current_rank_string([rank_snapshot]) if rank_snapshot else ""

    print(f"  Fetching match IDs...")
    match_ids = get_match_ids(puuid, count=count)
    if not match_ids:
        print(f"  No ranked games found for {riot_id}")
        sys.exit(1)

    print(f"  Fetching {len(match_ids)} games (rate limited)...\n")
    games = []
    for i, mid in enumerate(match_ids, 1):
        sys.stdout.write(f"\r  [{i}/{len(match_ids)}] {mid}")
        sys.stdout.flush()
        match = get_match(mid)
        if match:
            record = build_scout_record(match, puuid)
            if record:
                games.append(record)

    print(f"\n  {len(games)} games loaded.\n")

    if not games:
        print("  No valid game records built.")
        sys.exit(1)

    if role_filter:
        games = [g for g in games if g.get("role", "").upper() == role_filter]
        if not games:
            print(f"  No games found for role: {role_filter}")
            return

    from facecheck_analysis import run_analysis
    findings = run_analysis(games)

    # Confidence downgrade for findings that rely on timeline data
    # Now derived from finding metadata instead of hardcoded set
    for f in findings:
        if f.get("requires_timeline", False):
            if f["confidence_label"] == "CRITICAL":
                f["confidence_label"] = "CLEAR"
            elif f["confidence_label"] == "CLEAR":
                f["confidence_label"] = "NOTABLE"

    role_label = f" — {role_filter} LANE" if role_filter else ""
    display_id = f"{riot_id}{role_label}"
    print_slim_scout(display_id, games, findings, extra={"rank": rank_str})
    if len(games) >= 10:
        print_slim_matchups(games)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: facecheck scout Name#TAG [role] [count]")
        print("Example: facecheck scout Faker#T1 jungle 20")
        sys.exit(1)

    role_filter = None
    riot_id_parts = []
    count = 20
    for arg in args:
        if arg.isdigit():
            count = int(arg)
        else:
            normalized = ROLE_ALIASES.get(arg.lower())
            if normalized:
                role_filter = normalized
            else:
                riot_id_parts.append(arg)

    riot_id = " ".join(riot_id_parts)
    if not riot_id:
        print("Usage: facecheck scout Name#TAG [role] [count]")
        sys.exit(1)

    run_scout(riot_id, count=count, role_filter=role_filter)
