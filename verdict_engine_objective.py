"""
Objective Engine - Verdict Engine Architecture

Domain: structures and macro objectives.
Extracts turret/inhibitor kills, team objectives, objective steals, first flags.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from typing import List, Dict, Optional
from datetime import datetime

from verdict_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache
from verdict_game_model import Game


class ObjectiveEngine:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.nodes: List[EngineNode] = []
        self.signatures: List[EngineSignature] = []
        self.node_counter = 0

    def _make_node_id(self, prefix: str) -> str:
        self.node_counter += 1
        return f"{prefix}_{self.node_counter}"

    def analyze(self, games: List[Game]) -> EngineOutput:
        self.nodes = []
        self.signatures = []
        self.node_counter = 0
        for game in games:
            self._extract_game_nodes(game)
        self._detect_signatures(games)
        distributions = self._build_distributions(games)
        correlation_space = self._build_correlation_space(games)
        return EngineOutput(
            engine_name="objective",
            timestamp=datetime.now(),
            distributions=distributions,
            nodes=self.nodes,
            signatures=self.signatures,
            correlation_space=correlation_space,
            confidence=self._calculate_confidence(games),
            source_games=[g.match_id for g in games],
            raw_metrics=self._extract_raw_metrics(games)
        )

    def _extract_game_nodes(self, game: Game):
        match_id = game.match_id
        duration = game.duration_min
        win = game.win

        # Personal objective nodes
        for attr, node_type in [
            ("turret_kills", "turret_kill"),
            ("inhibitor_kills", "inhibitor_kill"),
            ("objectives_stolen", "objective_stolen"),
        ]:
            value = getattr(game, attr)
            if value:
                self.nodes.append(EngineNode(
                    node_id=self._make_node_id(f"{node_type}_{match_id}"),
                    timestamp_min=duration / 2,
                    node_type=node_type,
                    value=value,
                    context={
                        "match_id": match_id,
                        attr: value,
                        "win": win,
                    }
                ))

        # Team objective nodes
        my_team = game.my_team
        enemy_team = game.enemy_team
        for team_name, team_data in [("my", my_team), ("enemy", enemy_team)]:
            for obj_type in ["dragon_kills", "baron_kills", "tower_kills", "rift_herald_kills"]:
                count = getattr(team_data, obj_type)
                if count > 0:
                    self.nodes.append(EngineNode(
                        node_id=self._make_node_id(f"{team_name}_{obj_type}_{match_id}"),
                        timestamp_min=duration / 2,
                        node_type=f"{team_name}_objective",
                        value=count,
                        context={
                            "match_id": match_id,
                            "team": team_name,
                            "objective_type": obj_type,
                            "count": count,
                            "win": win,
                        }
                    ))

            # First flags
            for first_type in ["first_blood", "first_tower", "first_dragon", "first_baron"]:
                if getattr(team_data, first_type):
                    self.nodes.append(EngineNode(
                        node_id=self._make_node_id(f"{team_name}_{first_type}_{match_id}"),
                        timestamp_min=0,
                        node_type=f"{team_name}_first",
                        value=1,
                        context={
                            "match_id": match_id,
                            "team": team_name,
                            "first_type": first_type,
                            "win": win,
                        }
                    ))

    def _detect_signatures(self, games: List[Game]):
        """
        Detect structural objective patterns only.
        No evaluative thresholds — only factual team and personal objective records.
        """
        signatures = []

        for game in games:
            match_id = game.match_id
            win = game.win
            duration = game.duration_min
            my_team = game.my_team
            enemy_team = game.enemy_team
            turret_kills = game.turret_kills
            inhibitor_kills = game.inhibitor_kills
            objectives_stolen = game.objectives_stolen

            # ── Structural Pattern 1: Personal Objective Profile ──
            if any([turret_kills, inhibitor_kills, objectives_stolen]):
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                    signature_type="personal_objective_profile",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "turret_kills": turret_kills,
                        "inhibitor_kills": inhibitor_kills,
                        "objectives_stolen": objectives_stolen,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.8
                ))

            # ── Structural Pattern 2: Team Objective Profile ──
            features = {
                "dragon_kills": my_team.dragon_kills,
                "baron_kills": my_team.baron_kills,
                "tower_kills": my_team.tower_kills,
                "rift_herald_kills": my_team.rift_herald_kills,
                "first_blood": my_team.first_blood,
                "first_tower": my_team.first_tower,
                "first_dragon": my_team.first_dragon,
                "first_baron": my_team.first_baron,
                "game_duration": duration,
                "win": win,
            }
            signatures.append(EngineSignature(
                signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                signature_type="team_objective_profile",
                nodes=[],
                start_min=0,
                end_min=duration,
                features=features,
                confidence=0.85
            ))

            # ── Structural Pattern 3: Enemy Objective Profile ──
            signatures.append(EngineSignature(
                signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                signature_type="enemy_objective_profile",
                nodes=[],
                start_min=0,
                end_min=duration,
                features={
                    "dragon_kills": enemy_team.dragon_kills,
                    "baron_kills": enemy_team.baron_kills,
                    "tower_kills": enemy_team.tower_kills,
                    "rift_herald_kills": enemy_team.rift_herald_kills,
                    "first_blood": enemy_team.first_blood,
                    "first_tower": enemy_team.first_tower,
                    "first_dragon": enemy_team.first_dragon,
                    "first_baron": enemy_team.first_baron,
                    "game_duration": duration,
                    "win": win,
                },
                confidence=0.85
            ))

            # ── Structural Pattern 4: Objective Contrast ──
            features = {
                "dragon_differential": my_team.dragon_kills - enemy_team.dragon_kills,
                "baron_differential": my_team.baron_kills - enemy_team.baron_kills,
                "tower_differential": my_team.tower_kills - enemy_team.tower_kills,
                "rift_herald_differential": my_team.rift_herald_kills - enemy_team.rift_herald_kills,
                "game_duration": duration,
                "win": win,
            }
            signatures.append(EngineSignature(
                signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                signature_type="objective_contrast",
                nodes=[],
                start_min=0,
                end_min=duration,
                features=features,
                confidence=0.9
            ))

            # ── Structural Pattern 5: Objective Steal Event ──
            if objectives_stolen > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                    signature_type="objective_steal_event",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "objectives_stolen": objectives_stolen,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.9
                ))

            # ── Structural Pattern 6: First Objective Sequence ──
            first_flags = []
            if my_team.first_blood:
                first_flags.append("first_blood")
            if my_team.first_tower:
                first_flags.append("first_tower")
            if my_team.first_dragon:
                first_flags.append("first_dragon")
            if my_team.first_baron:
                first_flags.append("first_baron")
            if first_flags:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                    signature_type="first_objective_sequence",
                    nodes=[],
                    start_min=0,
                    end_min=15,
                    features={
                        "first_flags": first_flags,
                        "flag_count": len(first_flags),
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.75
                ))

            # ── Structural Pattern 7: Inhibitor Presence ──
            if inhibitor_kills > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"obj_sig_{match_id}"),
                    signature_type="inhibitor_presence",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "inhibitor_kills": inhibitor_kills,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.8
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Game]) -> Dict[str, Distribution]:
        distributions = {}
        for attr, label in [
            ("turret_kills", "turret_kills"),
            ("inhibitor_kills", "inhibitor_kills"),
            ("objectives_stolen", "objectives_stolen"),
        ]:
            vals = [getattr(g, attr) for g in games if getattr(g, attr)]
            if vals:
                distributions[label] = Distribution.from_values(vals)

        # Team objective distributions
        for team_attr, prefix in [("my_team", "team"), ("enemy_team", "enemy")]:
            for obj in ["dragon_kills", "baron_kills", "tower_kills", "rift_herald_kills"]:
                vals = [getattr(getattr(g, team_attr), obj) for g in games]
                if any(vals):
                    distributions[f"{prefix}_{obj}"] = Distribution.from_values(vals)

        return distributions

    def _build_correlation_space(self, games: List[Game]) -> Dict[str, List[float]]:
        space = {}
        space["turret_kills"] = [g.turret_kills or 0 for g in games]
        space["inhibitor_kills"] = [g.inhibitor_kills or 0 for g in games]
        space["objectives_stolen"] = [g.objectives_stolen or 0 for g in games]
        for team_attr, prefix in [("my_team", "team"), ("enemy_team", "enemy")]:
            for obj in ["dragon_kills", "baron_kills", "tower_kills", "rift_herald_kills"]:
                space[f"{prefix}_{obj}"] = [getattr(getattr(g, team_attr), obj) or 0 for g in games]
            for first in ["first_blood", "first_tower", "first_dragon", "first_baron"]:
                space[f"{prefix}_{first}"] = [1 if getattr(getattr(g, team_attr), first) else 0 for g in games]
        return space

    def _calculate_confidence(self, games: List[Game]) -> float:
        if not games:
            return 0.0
        factors = [min(len(games) / 20, 1.0)]
        # my_team always exists as TeamObjectives (default_factory), so always truthy
        complete = sum(1 for g in games if g.my_team or g.enemy_team) / len(games)
        factors.append(complete)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Game]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_objective_data": len([g for g in games if g.my_team]),
            "total_turret_kills": sum(g.turret_kills for g in games),
            "total_inhibitor_kills": sum(g.inhibitor_kills for g in games),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_objective_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = ObjectiveEngine(player_id)
        return engine.analyze(games)
    if cache_path is None:
        from verdict_paths import CACHE_PATH
        cache_path = CACHE_PATH
    return run_engine_from_cache(ObjectiveEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_objective_engine()
    if output:
        print(f"Objective Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")