"""
Aggregate Analysis - FaceCheck Engine Architecture

Synthesis-native analysis across multiple games.
Replaces legacy run_analysis for print_worst, print_best, print_pool.
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from facecheck_engine_base import EngineOutput
from facecheck_engine_cache import load_engine_outputs, save_engine_outputs
from facecheck_engine_death import run_death_engine
from facecheck_engine_economy import run_economy_engine
from facecheck_engine_combat import run_combat_engine
from facecheck_engine_durability import run_durability_engine
from facecheck_engine_vision import run_vision_engine
from facecheck_engine_objective import run_objective_engine
from facecheck_engine_draft import run_draft_engine
from facecheck_synthesis import SynthesisLayer, MultiEngineOutput, Verdict
from facecheck_similarity import SimilarityEngine
from facecheck_player_model import get_or_create_player_model


def _winrate(games: List[Dict]) -> Optional[float]:
    if not games:
        return None
    return round(sum(1 for g in games if g["win"]) / len(games) * 100, 1)


def _split_by_result(games: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    return [g for g in games if g["win"]], [g for g in games if not g["win"]]


def _robust_avg(values: list) -> Optional[float]:
    import statistics
    values = [v for v in values if v is not None]
    if not values:
        return None
    if len(values) < 3:
        return round(statistics.median(values), 2)
    return round(statistics.mean(values), 2)


def synthesize_games(games: List[Dict], player_id: str) -> List[Tuple[Dict, Verdict]]:
    """
    Run full synthesis pipeline on all games.
    Returns list of (game, verdict) pairs — one per game that produced a verdict.
    Uses engine cache to avoid re-running 7 engines.
    """
    if len(games) < 3:
        return []

    # Load or compute engine outputs
    engines = load_engine_outputs(player_id, games)
    if engines is None:
        death_output = run_death_engine(games=games, player_id=player_id)
        economy_output = run_economy_engine(games=games, player_id=player_id)
        combat_output = run_combat_engine(games=games, player_id=player_id)
        durability_output = run_durability_engine(games=games, player_id=player_id)
        vision_output = run_vision_engine(games=games, player_id=player_id)
        objective_output = run_objective_engine(games=games, player_id=player_id)
        draft_output = run_draft_engine(games=games, player_id=player_id)
        engines = MultiEngineOutput(
            death=death_output, economy=economy_output, combat=combat_output,
            durability=durability_output, vision=vision_output,
            objective=objective_output, draft=draft_output,
        )
        save_engine_outputs(player_id, games, engines)

    # Build player model + similarity
    player_model = get_or_create_player_model(player_id, games)
    similarity_output = None
    cluster_membership = {}
    try:
        sim_engine = SimilarityEngine()
        sim_result = sim_engine.analyze(games)
        if sim_result and sim_result.fingerprints:
            similarity_output = sim_result
            cluster_result = sim_engine.cluster()
            if cluster_result and cluster_result.clusters:
                for cluster in cluster_result.clusters:
                    for fp in cluster.games:
                        cluster_membership[fp.match_id] = cluster.cluster_id
            try:
                sim_engine.discover_patterns()
            except Exception:
                pass
    except Exception:
        pass

    # Synthesize each game
    synthesis = SynthesisLayer(player_model, similarity_output=similarity_output,
                               cluster_membership=cluster_membership)
    results = []
    for game in games:
        verdict = synthesis.analyze_single_game(game, engines)
        if verdict:
            results.append((game, verdict))

    return results


def worst_patterns(pairs: List[Tuple[Dict, Verdict]]) -> Dict:
    """
    Mine verdicts from losses for common patterns.
    Returns structured data for display:
      - mechanisms: [{mechanism, count, pct, lessons, evidence}]
      - items: [{item, wr, games}] worst first-item builds
      - champions: [{champion, wr, games}] worst champions
      - bottom_line: str summary
    """
    losses = [(g, v) for g, v in pairs if not g.get("win", False)]
    if not losses:
        return {"mechanisms": [], "items": [], "champions": [], "bottom_line": "No losses to analyze."}

    # Group loss verdicts by mechanism
    mech_counts = defaultdict(list)
    for g, v in losses:
        mechanism = v.mechanism or "unspecified"
        mech_counts[mechanism].append((g, v))

    mechanisms = []
    for mech, mv in sorted(mech_counts.items(), key=lambda x: -len(x[1])):
        lessons = set()
        evidence_keywords = set()
        for g, v in mv:
            for lesson in v.lessons:
                lessons.add(lesson.text)
            for ev in v.primary_evidence:
                evidence_keywords.add(ev.description)
        mechanisms.append({
            "mechanism": mech,
            "count": len(mv),
            "pct": round(len(mv) / len(losses) * 100, 1),
            "lessons": list(lessons)[:3],
            "evidence": list(evidence_keywords)[:2],
        })

    # Worst first items (only from losses)
    item_games = defaultdict(list)
    for g, v in losses:
        item = g.get("first_item")
        if item:
            item_games[item].append(g)

    # Need all games (wins + losses) for item winrate
    all_games = [g for g, v in pairs]
    all_item_games = defaultdict(list)
    for g in all_games:
        item = g.get("first_item")
        if item:
            all_item_games[item].append(g)

    items = []
    for item, ig in all_item_games.items():
        if len(ig) >= 3:
            wr = _winrate(ig)
            if wr is not None and wr < 45:
                items.append({"item": item, "wr": wr, "games": len(ig)})
    items.sort(key=lambda x: x["wr"])

    # Worst champions
    all_champ_games = defaultdict(list)
    for g in all_games:
        all_champ_games[g["champion"]].append(g)

    champions = []
    for champ, cg in all_champ_games.items():
        if len(cg) >= 5:
            wr = _winrate(cg)
            if wr is not None and wr < 45:
                champions.append({"champion": champ, "wr": wr, "games": len(cg)})
    champions.sort(key=lambda x: x["wr"])

    # Bottom line
    bottom_lines = []
    if items:
        worst_item = items[0]
        bottom_lines.append(f"Build: {worst_item['item']} at {worst_item['wr']}% WR. This is a known losing start. Change it first.")
    if champions:
        worst_champ = champions[0]
        bottom_lines.append(f"Champion: {worst_champ['champion']} at {worst_champ['wr']}% WR across {worst_champ['games']} games. The data does not support this pick.")
    if mechanisms:
        top_mech = mechanisms[0]
        bottom_lines.append(f"Primary issue: {top_mech['mechanism']} ({top_mech['pct']}% of losses). {top_mech['lessons'][0] if top_mech['lessons'] else 'Address this before anything else.'}")
    if not bottom_lines:
        total_losses = len(losses)
        total_games = len(pairs)
        wr = _winrate(all_games)
        bottom_lines.append(f"No dominant weakness found at {wr}% WR. Focus on consistency — the small edges compound.")

    return {
        "mechanisms": mechanisms,
        "items": items,
        "champions": champions,
        "bottom_line": "\n".join(bottom_lines),
    }


def best_patterns(pairs: List[Tuple[Dict, Verdict]]) -> Dict:
    """
    Mine verdicts from wins for common patterns.
    Returns structured data for display:
      - mechanisms: [{mechanism, count, pct, lessons, evidence}]
      - items: [{item, wr, games}] best first-item builds
      - champions: [{champion, wr, games}] best champions
      - bottom_line: str summary
    """
    wins = [(g, v) for g, v in pairs if g.get("win", False)]
    if not wins:
        return {"mechanisms": [], "items": [], "champions": [], "bottom_line": "No wins to analyze."}

    # Group win verdicts by mechanism
    mech_counts = defaultdict(list)
    for g, v in wins:
        mechanism = v.mechanism or "unspecified"
        mech_counts[mechanism].append((g, v))

    mechanisms = []
    for mech, mv in sorted(mech_counts.items(), key=lambda x: -len(x[1])):
        lessons = set()
        evidence_keywords = set()
        for g, v in mv:
            for lesson in v.lessons:
                lessons.add(lesson.text)
            for ev in v.primary_evidence:
                evidence_keywords.add(ev.description)
        mechanisms.append({
            "mechanism": mech,
            "count": len(mv),
            "pct": round(len(mv) / len(wins) * 100, 1),
            "lessons": list(lessons)[:3],
            "evidence": list(evidence_keywords)[:2],
        })

    # Best items
    all_games = [g for g, v in pairs]
    item_games = defaultdict(list)
    for g in all_games:
        item = g.get("first_item")
        if item:
            item_games[item].append(g)

    items = []
    for item, ig in item_games.items():
        if len(ig) >= 3:
            wr = _winrate(ig)
            if wr is not None and wr >= 55:
                items.append({"item": item, "wr": wr, "games": len(ig)})
    items.sort(key=lambda x: x["wr"], reverse=True)

    # Best champions
    champ_games = defaultdict(list)
    for g in all_games:
        champ_games[g["champion"]].append(g)

    champions = []
    for champ, cg in champ_games.items():
        if len(cg) >= 5:
            wr = _winrate(cg)
            if wr is not None and wr >= 55:
                champions.append({"champion": champ, "wr": wr, "games": len(cg)})
    champions.sort(key=lambda x: x["wr"], reverse=True)

    # Bottom line
    bottom_lines = []
    if items:
        best_item = items[0]
        bottom_lines.append(f"Build: {best_item['item']} at {best_item['wr']}% WR. This is your winning item. Do not deviate.")
    if champions:
        best_champ = champions[0]
        bottom_lines.append(f"Champion: {best_champ['champion']} at {best_champ['wr']}% WR. When you want to climb, play this.")
    if mechanisms:
        top_mech = mechanisms[0]
        bottom_lines.append(f"Win pattern: {top_mech['mechanism']} ({top_mech['pct']}% of wins). {top_mech['lessons'][0] if top_mech['lessons'] else 'Keep building on this.'}")
    if not bottom_lines:
        wr = _winrate(all_games)
        bottom_lines.append(f"Consistent performance at {wr}% WR. No single dominant pattern — keep playing your game.")

    return {
        "mechanisms": mechanisms,
        "items": items,
        "champions": champions,
        "bottom_line": "\n".join(bottom_lines),
    }


# ─────────────────────────────────────────────
# AGGREGATE DISPLAY FUNCTIONS
# ─────────────────────────────────────────────

def _print_basic_worst(games, champion, wins, losses, wr):
    """Raw-stats fallback when synthesis is unavailable."""
    first_item_games = defaultdict(list)
    for g in games:
        if g.get("first_item"):
            first_item_games[g["first_item"]].append(g)
    worst_items = []
    for item, ig in first_item_games.items():
        if len(ig) >= 3:
            wr_item = _winrate(ig)
            if wr_item is not None and wr_item < 45:
                worst_items.append((item, wr_item, len(ig)))
    worst_items.sort(key=lambda x: x[1])

    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    worst_champs = []
    for champ, cg in champ_games.items():
        if len(cg) >= 5:
            wr_c = _winrate(cg)
            if wr_c is not None and wr_c < 45:
                worst_champs.append((champ, wr_c, len(cg)))
    worst_champs.sort(key=lambda x: x[1])

    if worst_items:
        print(f"  ── STOP BUILDING THESE ──────────────────────────────────────")
        for item, wr_item, n in worst_items:
            print(f"  {item}: {wr_item}% winrate across {n} games.")
        print()

    if worst_champs and not champion:
        print(f"  ── STOP PLAYING THESE ───────────────────────────────────────")
        for champ, wr_c, n in worst_champs:
            print(f"  {champ}: {wr_c}% winrate across {n} games.")
        print()

    print(f"\n  ── BOTTOM LINE ──────────────────────────────────────────────")
    if worst_items:
        print(f"  Build: {worst_items[0][0]} at {worst_items[0][1]}% WR.")
    if worst_champs and not champion:
        print(f"  Champion: {worst_champs[0][0]} at {worst_champs[0][1]}% WR.")
    if not worst_items and not worst_champs:
        print(f"  No dominant weakness found at {wr}% WR. Focus on consistency.")


def _print_basic_best(games, champion, wins, losses, wr):
    """Raw-stats fallback when synthesis is unavailable."""
    first_item_games = defaultdict(list)
    for g in games:
        if g.get("first_item"):
            first_item_games[g["first_item"]].append(g)
    best_items = []
    for item, ig in first_item_games.items():
        if len(ig) >= 3:
            wr_item = _winrate(ig)
            if wr_item is not None and wr_item >= 55:
                best_items.append((item, wr_item, len(ig)))
    best_items.sort(key=lambda x: x[1], reverse=True)

    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    best_champs = []
    for champ, cg in champ_games.items():
        if len(cg) >= 5:
            wr_c = _winrate(cg)
            if wr_c is not None and wr_c >= 55:
                best_champs.append((champ, wr_c, len(cg)))
    best_champs.sort(key=lambda x: x[1], reverse=True)

    if best_items:
        print(f"  ── KEEP BUILDING THESE ──────────────────────────────────────")
        for item, wr_item, n in best_items:
            print(f"  {item}: {wr_item}% winrate across {n} games.")
        print()

    if best_champs and not champion:
        print(f"  ── KEEP PLAYING THESE ───────────────────────────────────────")
        for champ, wr_c, n in best_champs:
            print(f"  {champ}: {wr_c}% winrate across {n} games.")
        print()

    print(f"\n  ── BOTTOM LINE ──────────────────────────────────────────────")
    if best_items:
        print(f"  Build: {best_items[0][0]} at {best_items[0][1]}% WR.")
    if best_champs:
        print(f"  Champion: {best_champs[0][0]} at {best_champs[0][1]}% WR.")
    if not best_items and not best_champs:
        print(f"  No dominant strength found at {wr}% WR.")


def print_worst(games, champion=None, player_id=None):
    label = f"FACECHECK WORST — {champion}" if champion else "FACECHECK WORST"
    wins, losses = _split_by_result(games)
    wr = _winrate(games) or 0

    print(f"\n  {'='*60}")
    print(f"  {label}")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    print(f"  {'='*60}")
    print(f"\n  Here is what is costing you games. No softening.\n")

    # Run synthesis across all games
    if player_id and len(games) >= 3:
        pairs = synthesize_games(games, player_id)
        data = worst_patterns(pairs)

        if data["items"]:
            print(f"  ── STOP BUILDING THESE ──────────────────────────────────────")
            for item_info in data["items"]:
                print(f"  {item_info['item']}: {item_info['wr']}% winrate across {item_info['games']} games. This item is actively costing you.")
            print()

        if data["champions"] and not champion:
            print(f"  ── STOP PLAYING THESE ───────────────────────────────────────")
            for champ_info in data["champions"]:
                print(f"  {champ_info['champion']}: {champ_info['wr']}% winrate across {champ_info['games']} games. The data does not support this pick.")
            print()

        if data["mechanisms"]:
            print(f"  ── YOUR WORST PATTERNS ──────────────────────────────────────")
            for mech in data["mechanisms"][:6]:
                print(f"  {mech['mechanism'].replace('_', ' ').title()}: {mech['pct']}% of losses ({mech['count']} games)")
                if mech["lessons"]:
                    print(f"    → {mech['lessons'][0]}")
            print()

        print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
        for line in data["bottom_line"].split("\n"):
            print(f"  {line}")
    else:
        # Not enough data or synthesis unavailable — show basic stats
        _print_basic_worst(games, champion, wins, losses, wr)
    print()


def print_best(games, champion=None, player_id=None):
    label = f"FACECHECK BEST — {champion}" if champion else "FACECHECK BEST"
    wins, losses = _split_by_result(games)
    wr = _winrate(games) or 0

    print(f"\n  {'='*60}")
    print(f"  {label}")
    print(f"  {'='*60}")
    print(f"  {len(games)} games  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    print(f"  {'='*60}")
    print(f"\n  Here is what is working for you. Keep doing this.\n")

    if player_id and len(games) >= 3:
        pairs = synthesize_games(games, player_id)
        data = best_patterns(pairs)

        if data["items"]:
            print(f"  ── KEEP BUILDING THESE ──────────────────────────────────────")
            for item_info in data["items"]:
                print(f"  {item_info['item']}: {item_info['wr']}% winrate across {item_info['games']} games. This is a winning pattern.")
            print()

        if data["champions"] and not champion:
            print(f"  ── KEEP PLAYING THESE ───────────────────────────────────────")
            for champ_info in data["champions"]:
                print(f"  {champ_info['champion']}: {champ_info['wr']}% winrate across {champ_info['games']} games. This champion works for you.")
            print()

        if data["mechanisms"]:
            print(f"  ── WHAT YOUR WINNING GAMES HAVE IN COMMON ───────────────────")
            for mech in data["mechanisms"][:5]:
                print(f"  {mech['mechanism'].replace('_', ' ').title()}: {mech['pct']}% of wins ({mech['count']} games)")
                if mech["lessons"]:
                    print(f"    → {mech['lessons'][0]}")
            print()

        print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
        for line in data["bottom_line"].split("\n"):
            print(f"  {line}")
    else:
        _print_basic_best(games, champion, wins, losses, wr)
    print()


def print_pool(games, min_games=3):
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)

    rows = []
    for champ, cg in champ_games.items():
        if len(cg) < min_games:
            continue
        wr = _winrate(cg)
        if wr is None:
            continue
        recent = cg[:5]
        recent_wr = _winrate(recent)
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