"""
Vision Engine - FaceCheck Engine Architecture

Domain: map control and vision.
Extracts vision score, wards placed/killed, control wards, enemy vision.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from typing import List, Dict, Optional
from datetime import datetime

from facecheck_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache


class VisionEngine:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.nodes: List[EngineNode] = []
        self.signatures: List[EngineSignature] = []
        self.node_counter = 0

    def _make_node_id(self, prefix: str) -> str:
        self.node_counter += 1
        return f"{prefix}_{self.node_counter}"

    def analyze(self, games: List[Dict]) -> EngineOutput:
        self.nodes = []
        self.signatures = []
        self.node_counter = 0
        for game in games:
            self._extract_game_nodes(game)
        self._detect_signatures(games)
        distributions = self._build_distributions(games)
        correlation_space = self._build_correlation_space(games)
        return EngineOutput(
            engine_name="vision",
            timestamp=datetime.now(),
            distributions=distributions,
            nodes=self.nodes,
            signatures=self.signatures,
            correlation_space=correlation_space,
            confidence=self._calculate_confidence(games),
            source_games=[g.get("match_id", "") for g in games],
            raw_metrics=self._extract_raw_metrics(games)
        )

    def _extract_game_nodes(self, game: Dict):
        match_id = game.get("match_id", "unknown")
        duration = game.get("duration_min", 30)
        win = game.get("win", False)

        for metric, node_type in [
            ("vision", "vision_score"),
            ("vision_per_min", "vision_per_min"),
            ("wards_placed", "wards_placed"),
            ("wards_killed", "wards_killed"),
            ("control_wards", "control_wards"),
        ]:
            value = game.get(metric, 0)
            if value:
                self.nodes.append(EngineNode(
                    node_id=self._make_node_id(f"{node_type}_{match_id}"),
                    timestamp_min=duration / 2,
                    node_type=node_type,
                    value=value,
                    context={
                        "match_id": match_id,
                        metric: value,
                        "win": win,
                    }
                ))

        # Enemy vision from all_players
        enemy_vision = 0
        enemy_wards_placed = 0
        enemy_control_wards = 0
        for p in game.get("all_players", []):
            if p.get("team") == "enemy":
                enemy_vision += p.get("vision", 0)
                enemy_wards_placed += p.get("wards_placed", 0)
                enemy_control_wards += p.get("control_wards", 0)

        if enemy_vision > 0:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"enemy_vision_{match_id}"),
                timestamp_min=duration / 2,
                node_type="enemy_vision",
                value=enemy_vision,
                context={
                    "match_id": match_id,
                    "enemy_vision": enemy_vision,
                    "enemy_wards_placed": enemy_wards_placed,
                    "enemy_control_wards": enemy_control_wards,
                    "win": win,
                }
            ))

    def _detect_signatures(self, games: List[Dict]):
        """
        Detect structural vision patterns only.
        No evaluative thresholds — only factual cross-field profiles.
        """
        signatures = []

        for game in games:
            match_id = game.get("match_id", "")
            win = game.get("win", False)
            duration = game.get("duration_min", 30)
            vision = game.get("vision", 0) or 0
            vpm = game.get("vision_per_min", 0) or 0
            wp = game.get("wards_placed", 0) or 0
            wk = game.get("wards_killed", 0) or 0
            cw = game.get("control_wards", 0) or 0

            # ── Structural Pattern 1: Vision Profile ──
            if vision > 0 or vpm > 0:
                features = {
                    "vision_score": vision,
                    "vision_per_min": vpm,
                    "wards_placed": wp,
                    "wards_killed": wk,
                    "control_wards": cw,
                    "game_duration": duration,
                    "win": win,
                }
                if wp > 0 and wk > 0:
                    features["active_ward_play"] = True

                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"vis_sig_{match_id}"),
                    signature_type="vision_profile",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features=features,
                    confidence=0.8
                ))

            # ── Structural Pattern 2: Enemy Vision Contrast ──
            enemy_vision = 0
            enemy_wards = 0
            for p in game.get("all_players", []):
                if p.get("team") == "enemy":
                    enemy_vision += p.get("vision", 0) or 0
                    enemy_wards += p.get("wards_placed", 0) or 0

            if enemy_vision > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"vis_sig_{match_id}"),
                    signature_type="enemy_vision_contrast",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "my_vision": vision,
                        "enemy_team_vision": enemy_vision,
                        "vision_differential": vision - enemy_vision,
                        "my_wards_placed": wp,
                        "enemy_team_wards_placed": enemy_wards,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.75
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Dict]) -> Dict[str, Distribution]:
        distributions = {}
        for metric, label in [
            ("vision", "vision_score"),
            ("vision_per_min", "vision_per_min"),
            ("wards_placed", "wards_placed"),
            ("wards_killed", "wards_killed"),
            ("control_wards", "control_wards"),
        ]:
            vals = [g.get(metric, 0) for g in games if g.get(metric)]
            if vals:
                distributions[label] = Distribution.from_values(vals)
        return distributions

    def _build_correlation_space(self, games: List[Dict]) -> Dict[str, List[float]]:
        return {
            "vision": [g.get("vision", 0) or 0 for g in games],
            "vision_per_min": [g.get("vision_per_min", 0) or 0 for g in games],
            "wards_placed": [g.get("wards_placed", 0) or 0 for g in games],
            "wards_killed": [g.get("wards_killed", 0) or 0 for g in games],
            "control_wards": [g.get("control_wards", 0) or 0 for g in games],
        }

    def _calculate_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        factors = [min(len(games) / 20, 1.0)]
        complete = sum(1 for g in games if g.get("vision")) / len(games)
        factors.append(complete)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Dict]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_vision_data": len([g for g in games if g.get("vision")]),
            "games_with_ward_kill_data": len([g for g in games if g.get("wards_killed")]),
            "total_vision_recorded": sum(g.get("vision", 0) for g in games),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_vision_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = VisionEngine(player_id)
        return engine.analyze(games)
    cache_path = cache_path or "C:\\Facecheck\\facecheck_cache.json"
    return run_engine_from_cache(VisionEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_vision_engine()
    if output:
        print(f"Vision Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")
