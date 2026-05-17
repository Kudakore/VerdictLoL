"""
Aggregate Analysis - Verdict Engine Architecture

Synthesis-native analysis across multiple games.
Replaces legacy run_analysis for print_worst, print_best, print_pool.
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from verdict_engine_base import EngineOutput
from verdict_engine_cache import load_engine_outputs, save_engine_outputs
from verdict_engine_death import run_death_engine
from verdict_engine_economy import run_economy_engine
from verdict_engine_combat import run_combat_engine
from verdict_engine_durability import run_durability_engine
from verdict_engine_vision import run_vision_engine
from verdict_engine_objective import run_objective_engine
from verdict_engine_draft import run_draft_engine
from verdict_synthesis import SynthesisLayer, MultiEngineOutput, Verdict
from verdict_similarity import SimilarityEngine
from verdict_player_model import get_or_create_player_model


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


def mine_observations(pairs: List[Tuple[Dict, Verdict]], result_filter=None) -> List[Dict]:
    """
    Mine observations across verdicts for aggregate patterns.
    result_filter: "loss" for worst, "win" for best, None for all.
    Returns list of dicts: [{obs_type, label, count, pct, avg_score, wr, priority, statements}]
    """
    if result_filter == "loss":
        pairs = [(g, v) for g, v in pairs if not g.get("win", False)]
    elif result_filter == "win":
        pairs = [(g, v) for g, v in pairs if g.get("win", False)]

    obs_counts = defaultdict(list)
    for g, v in pairs:
        for obs in v.observations:
            if obs.score < 0.5:
                continue  # skip baseline fallbacks — not actionable patterns
            obs_counts[obs.obs_type].append((g, obs))

    total = len(pairs)
    patterns = []
    for obs_type, game_obs_list in obs_counts.items():
        if len(game_obs_list) < 2:
            continue
        label = game_obs_list[0][1].label
        priority = game_obs_list[0][1].priority
        games = [g for g, _ in game_obs_list]
        wins = sum(1 for g in games if g.get("win", False))
        avg_score = sum(obs.score for _, obs in game_obs_list) / len(game_obs_list)
        statements = list(dict.fromkeys(obs.statement for _, obs in game_obs_list))[:3]

        patterns.append({
            "obs_type": obs_type,
            "label": label,
            "count": len(game_obs_list),
            "pct": round(len(game_obs_list) / total * 100, 1) if total > 0 else 0,
            "avg_score": round(avg_score, 2),
            "wr": round(wins / len(game_obs_list) * 100, 1),
            "priority": priority,
            "statements": statements,
        })

    patterns.sort(key=lambda x: x["count"], reverse=True)
    return patterns


def _compute_observation_deltas(my_pairs, ref_pairs):
    """Compare observation rates between two players. Sorted by biggest absolute delta."""
    my_obs = mine_observations(my_pairs)
    ref_obs = mine_observations(ref_pairs)

    all_types = set(o["obs_type"] for o in my_obs) | set(o["obs_type"] for o in ref_obs)
    deltas = []
    for obs_type in all_types:
        my_match = next((o for o in my_obs if o["obs_type"] == obs_type), None)
        ref_match = next((o for o in ref_obs if o["obs_type"] == obs_type), None)
        my_pct = my_match["pct"] if my_match else 0
        ref_pct = ref_match["pct"] if ref_match else 0
        deltas.append({
            "obs_type": obs_type,
            "label": (my_match or ref_match)["label"],
            "priority": (my_match or ref_match)["priority"],
            "my_pct": my_pct,
            "ref_pct": ref_pct,
            "delta_pp": round(my_pct - ref_pct, 1),
            "my_count": my_match["count"] if my_match else 0,
            "ref_count": ref_match["count"] if ref_match else 0,
        })
    deltas.sort(key=lambda x: abs(x["delta_pp"]), reverse=True)
    return deltas


def _compute_distribution_deltas(my_engines, ref_engines):
    """Compare distribution stats between two players' engine outputs."""
    deltas = []
    dist_pairs = [
        ("deaths_per_game", "death", "Deaths/game"),
        ("damage_per_min", "combat", "DPM"),
        ("kill_participation", "combat", "Kill participation"),
        ("total_heal", "durability", "Healing"),
        ("damage_mitigated", "durability", "Mitigation"),
        ("cc_time", "durability", "CC time"),
        ("wards_killed", "vision", "Wards killed"),
    ]
    for dist_key, engine_attr, label in dist_pairs:
        my_output = getattr(my_engines, engine_attr)
        ref_output = getattr(ref_engines, engine_attr)
        if not my_output or not ref_output:
            continue
        my_dist = my_output.distributions.get(dist_key)
        ref_dist = ref_output.distributions.get(dist_key)
        if not my_dist or not ref_dist:
            continue
        deltas.append({
            "label": label,
            "my_median": my_dist.median,
            "ref_median": ref_dist.median,
            "my_p25": my_dist.percentiles.get(25, my_dist.median * 0.75),
            "ref_p25": ref_dist.percentiles.get(25, ref_dist.median * 0.75),
            "my_p75": my_dist.percentiles.get(75, my_dist.median * 1.25),
            "ref_p75": ref_dist.percentiles.get(75, ref_dist.median * 1.25),
            "delta_median": round(my_dist.median - ref_dist.median, 1),
            "delta_pct": round((my_dist.median / ref_dist.median - 1) * 100, 0) if ref_dist.median else 0,
        })
    return deltas


def compare_players(my_pairs, ref_pairs, my_engines, ref_engines, my_games, ref_games):
    """
    Compare two players' patterns and distributions.
    Returns dict with observation_deltas, distribution_deltas, bottom_line.
    """
    observation_deltas = _compute_observation_deltas(my_pairs, ref_pairs)
    distribution_deltas = _compute_distribution_deltas(my_engines, ref_engines)

    # Bottom line: top 2-3 most actionable deltas
    bottom_lines = []
    if observation_deltas:
        top_obs = observation_deltas[0]
        direction = "more" if top_obs["delta_pp"] > 0 else "less"
        bottom_lines.append(
            f"Biggest pattern gap: {top_obs['label'].lower()} "
            f"(you {abs(top_obs['delta_pp']):.0f}pp {direction} than them)."
        )
    if distribution_deltas:
        top_dist = distribution_deltas[0]
        if top_dist["delta_pct"] >= 0:
            bottom_lines.append(
                f"Biggest stat gap: {top_dist['label']} — "
                f"you average {top_dist['my_median']:.0f} vs their {top_dist['ref_median']:.0f} "
                f"(+{top_dist['delta_pct']:.0f}%)."
            )
        else:
            bottom_lines.append(
                f"Biggest stat gap: {top_dist['label']} — "
                f"you average {top_dist['my_median']:.0f} vs their {top_dist['ref_median']:.0f} "
                f"({top_dist['delta_pct']:.0f}%)."
            )
    if len(observation_deltas) > 1:
        second = observation_deltas[1]
        if abs(second["delta_pp"]) >= 5:
            direction = "more" if second["delta_pp"] > 0 else "less"
            bottom_lines.append(
                f"Also notable: {second['label'].lower()} "
                f"({abs(second['delta_pp']):.0f}pp {direction})."
            )

    return {
        "observation_deltas": observation_deltas,
        "distribution_deltas": distribution_deltas,
        "bottom_line": "\n".join(bottom_lines) if bottom_lines else "No significant differences found.",
    }


def synthesize_games_with_engines(games: List[Dict], player_id: str):
    """
    Run full synthesis pipeline, returning (pairs, engines).
    Useful for compare mode which needs both verdicts and engine outputs.
    """
    if len(games) < 3:
        return [], None

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

    return results, engines


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
      - observation_patterns: [{obs_type, label, count, pct, avg_score, wr, priority, statements}]
      - items: [{item, wr, games}] worst first-item builds
      - champions: [{champion, wr, games}] worst champions
      - bottom_line: str summary
    """
    losses = [(g, v) for g, v in pairs if not g.get("win", False)]
    if not losses:
        return {"observation_patterns": [], "items": [], "champions": [], "bottom_line": "No losses to analyze."}

    # Mine observation patterns from loss verdicts
    observation_patterns = mine_observations(pairs, result_filter="loss")

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
        bottom_lines.append(f"Build: {worst_item['item']} at {worst_item['wr']}% WR — {worst_item['wr']}% is below your overall win rate.")
    if champions:
        worst_champ = champions[0]
        delta = worst_champ['wr'] - wr
        bottom_lines.append(f"Champion: {worst_champ['champion']} at {worst_champ['wr']}% WR across {worst_champ['games']} games ({delta:+.0f}% vs your {wr}% overall).")
    if observation_patterns:
        top = observation_patterns[0]
        stmt = top['statements'][0] if top['statements'] else 'Address this first.'
        bottom_lines.append(f"Primary pattern: {top['label']} ({top['pct']}% of losses). {stmt}")
    if not bottom_lines:
        total_losses = len(losses)
        total_games = len(pairs)
        wr = _winrate(all_games)
        bottom_lines.append(f"No dominant weakness found at {wr}% WR. {total_losses} losses spread across multiple factors.")

    return {
        "observation_patterns": observation_patterns,
        "items": items,
        "champions": champions,
        "bottom_line": "\n".join(bottom_lines),
    }


def best_patterns(pairs: List[Tuple[Dict, Verdict]]) -> Dict:
    """
    Mine verdicts from wins for common patterns.
    Returns structured data for display:
      - observation_patterns: [{obs_type, label, count, pct, avg_score, wr, priority, statements}]
      - items: [{item, wr, games}] best first-item builds
      - champions: [{champion, wr, games}] best champions
      - bottom_line: str summary
    """
    wins = [(g, v) for g, v in pairs if g.get("win", False)]
    if not wins:
        return {"observation_patterns": [], "items": [], "champions": [], "bottom_line": "No wins to analyze."}

    # Mine observation patterns from win verdicts
    observation_patterns = mine_observations(pairs, result_filter="win")

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
    if observation_patterns:
        top = observation_patterns[0]
        stmt = top['statements'][0] if top['statements'] else 'Keep building on this.'
        bottom_lines.append(f"Win pattern: {top['label']} ({top['pct']}% of wins). {stmt}")
    if not bottom_lines:
        wr = _winrate(all_games)
        bottom_lines.append(f"Consistent performance at {wr}% WR. No single pattern dominates — multiple small factors drive wins.")

    return {
        "observation_patterns": observation_patterns,
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
        print(f"  No dominant weakness found at {wr}% WR. {len(losses)} losses spread across factors.")


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
    label = f"VERDICT WORST — {champion}" if champion else "VERDICT WORST"
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
                print(f"  {item_info['item']}: {item_info['wr']}% winrate across {item_info['games']} games — {item_info['wr']}% is {100-item_info['wr']}% losses.")
            print()

        if data["champions"] and not champion:
            print(f"  ── STOP PLAYING THESE ───────────────────────────────────────")
            for champ_info in data["champions"]:
                w = int(champ_info['games'] * champ_info['wr'] / 100)
                l = champ_info['games'] - w
                print(f"  {champ_info['champion']}: {champ_info['wr']}% winrate across {champ_info['games']} games — {l} losses, {w} wins.")
            print()

        if data["observation_patterns"]:
            print(f"  ── YOUR WORST PATTERNS ──────────────────────────────────────")
            for pat in data["observation_patterns"][:6]:
                print(f"  {pat['label'].title()}: {pat['count']} losses ({pat['pct']}%) — {pat['priority']}")
                for stmt in pat["statements"][:2]:
                    print(f"    → {stmt}")
            print()

        print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
        for line in data["bottom_line"].split("\n"):
            print(f"  {line}")
    else:
        # Not enough data or synthesis unavailable — show basic stats
        _print_basic_worst(games, champion, wins, losses, wr)
    print()


def print_best(games, champion=None, player_id=None):
    label = f"VERDICT BEST — {champion}" if champion else "VERDICT BEST"
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
                print(f"  {item_info['item']}: {item_info['wr']}% winrate across {item_info['games']} games — {item_info['wins']} wins.")
            print()

        if data["champions"] and not champion:
            print(f"  ── KEEP PLAYING THESE ───────────────────────────────────────")
            for champ_info in data["champions"]:
                w = int(champ_info['games'] * champ_info['wr'] / 100)
                l = champ_info['games'] - w
                print(f"  {champ_info['champion']}: {champ_info['wr']}% winrate across {champ_info['games']} games — {w} wins, {l} losses.")
            print()

        if data["observation_patterns"]:
            print(f"  ── WHAT YOUR WINNING GAMES HAVE IN COMMON ───────────────────")
            for pat in data["observation_patterns"][:5]:
                print(f"  {pat['label'].title()}: {pat['count']} wins ({pat['pct']}%) — {pat['priority']}")
                for stmt in pat["statements"][:2]:
                    print(f"    → {stmt}")
            print()

        print(f"  ── BOTTOM LINE ──────────────────────────────────────────────")
        for line in data["bottom_line"].split("\n"):
            print(f"  {line}")
    else:
        _print_basic_best(games, champion, wins, losses, wr)
    print()


def print_pool(games, min_games=3, player_id=None):
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
    print(f"  VERDICT POOL")
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

    # Per-champion observation enrichment
    if player_id and len(games) >= 3:
        pairs = synthesize_games(games, player_id)
        if pairs:
            champ_verdicts = defaultdict(list)
            for g, v in pairs:
                champ_verdicts[g["champion"]].append((g, v))

            obs_lines = []
            champ_lookup = {r[0]: r for r in rows}
            for champ, n, wr, trend, verdict_label in rows:
                if champ not in champ_verdicts or len(champ_verdicts[champ]) < 3:
                    continue
                cv = champ_verdicts[champ]
                losses = [(g, v) for g, v in cv if not g.get("win", False)]
                wins_list = [(g, v) for g, v in cv if g.get("win", False)]

                if wr < 50 and losses:
                    obs_counts = defaultdict(int)
                    for _, v in losses:
                        if v.observations:
                            obs_counts[v.observations[0].label] += 1
                    if obs_counts:
                        top_obs = max(obs_counts.items(), key=lambda x: x[1])
                        obs_lines.append((champ, f"loss pattern: {top_obs[0]} ({top_obs[1]}/{len(losses)} losses)"))
                elif wr >= 50 and wins_list:
                    obs_counts = defaultdict(int)
                    for _, v in wins_list:
                        if v.observations:
                            obs_counts[v.observations[0].label] += 1
                    if obs_counts:
                        top_obs = max(obs_counts.items(), key=lambda x: x[1])
                        obs_lines.append((champ, f"win pattern: {top_obs[0]} ({top_obs[1]}/{len(wins_list)} wins)"))

            if obs_lines:
                print()
                print(f"  ── CHAMPION PATTERNS ───────────────────────────────────────")
                for champ, line in obs_lines:
                    print(f"  {champ}: {line}")

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
        print(f"  Bench:      {worst[0]} — {worst[2]}% WR across {worst[1]} games.")
    print()