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