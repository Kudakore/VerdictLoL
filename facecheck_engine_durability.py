"""
Durability Engine - FaceCheck Engine Architecture

Domain: tankiness, sustain, and utility.
Extracts healing, damage mitigation, CC time, shields, damage taken.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from typing import List, Dict, Optional
from datetime import datetime

from facecheck_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache


class DurabilityEngine:
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
            engine_name="durability",
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
            ("total_heal", "healing"),
            ("damage_mitigated", "damage_mitigation"),
            ("cc_time", "crowd_control"),
            ("heals_on_teammates", "heals_on_teammates"),
            ("damage_shielded", "damage_shielded"),
            ("total_damage_taken", "damage_taken"),
            ("physical_damage_taken", "physical_damage_taken"),
            ("magic_damage_taken", "magic_damage_taken"),
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

    def _detect_signatures(self, games: List[Dict]):
        """
        Detect structural durability patterns only.
        No evaluative thresholds — only factual cross-field profiles.
        """
        signatures = []

        for game in games:
            match_id = game.get("match_id", "")
            win = game.get("win", False)
            duration = game.get("duration_min", 30)

            heal = game.get("total_heal", 0) or 0
            mit = game.get("damage_mitigated", 0) or 0
            cc = game.get("cc_time", 0) or 0
            shield = game.get("damage_shielded", 0) or 0
            heal_team = game.get("heals_on_teammates", 0) or 0
            dmg_taken = game.get("total_damage_taken", 0) or 0
            phys_taken = game.get("physical_damage_taken", 0) or 0
            magic_taken = game.get("magic_damage_taken", 0) or 0

            # ── Structural Pattern 1: Durability Profile ──
            # Cross-field record of all durability metrics as a factual unit.
            if any([heal, mit, cc, shield, dmg_taken]):
                features = {
                    "total_heal": heal,
                    "damage_mitigated": mit,
                    "cc_time": cc,
                    "damage_shielded": shield,
                    "heals_on_teammates": heal_team,
                    "total_damage_taken": dmg_taken,
                    "game_duration": duration,
                    "win": win,
                }
                if heal > 0 and mit > 0:
                    features["self_sustain_present"] = True
                if shield > 0 and heal_team > 0:
                    features["support_utility_present"] = True

                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"dur_sig_{match_id}"),
                    signature_type="durability_profile",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features=features,
                    confidence=0.8
                ))

            # ── Structural Pattern 2: Damage Taken Breakdown ──
            if dmg_taken > 0 and (phys_taken > 0 or magic_taken > 0):
                phys_ratio = phys_taken / dmg_taken if dmg_taken else 0
                magic_ratio = magic_taken / dmg_taken if dmg_taken else 0
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"dur_sig_{match_id}"),
                    signature_type="damage_taken_breakdown",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "total_damage_taken": dmg_taken,
                        "physical_damage_taken": phys_taken,
                        "magic_damage_taken": magic_taken,
                        "physical_ratio": round(phys_ratio, 2),
                        "magic_ratio": round(magic_ratio, 2),
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.75
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Dict]) -> Dict[str, Distribution]:
        distributions = {}
        for metric, label in [
            ("total_heal", "total_heal"),
            ("damage_mitigated", "damage_mitigated"),
            ("cc_time", "cc_time"),
            ("heals_on_teammates", "heals_on_teammates"),
            ("damage_shielded", "damage_shielded"),
            ("total_damage_taken", "damage_taken"),
            ("physical_damage_taken", "physical_damage_taken"),
            ("magic_damage_taken", "magic_damage_taken"),
        ]:
            vals = [g.get(metric, 0) for g in games if g.get(metric)]
            if vals:
                distributions[label] = Distribution.from_values(vals)
        return distributions

    def _build_correlation_space(self, games: List[Dict]) -> Dict[str, List[float]]:
        return {
            "total_heal": [g.get("total_heal", 0) or 0 for g in games],
            "damage_mitigated": [g.get("damage_mitigated", 0) or 0 for g in games],
            "cc_time": [g.get("cc_time", 0) or 0 for g in games],
            "heals_on_teammates": [g.get("heals_on_teammates", 0) or 0 for g in games],
            "damage_shielded": [g.get("damage_shielded", 0) or 0 for g in games],
            "damage_taken": [g.get("total_damage_taken", 0) or 0 for g in games],
            "physical_damage_taken": [g.get("physical_damage_taken", 0) or 0 for g in games],
            "magic_damage_taken": [g.get("magic_damage_taken", 0) or 0 for g in games],
        }

    def _calculate_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        factors = [min(len(games) / 20, 1.0)]
        complete = sum(1 for g in games if g.get("total_heal") or g.get("damage_mitigated")) / len(games)
        factors.append(complete)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Dict]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_heal_data": len([g for g in games if g.get("total_heal")]),
            "games_with_mitigation_data": len([g for g in games if g.get("damage_mitigated")]),
            "games_with_cc_data": len([g for g in games if g.get("cc_time")]),
            "total_heal_recorded": sum(g.get("total_heal", 0) for g in games),
            "total_mitigation_recorded": sum(g.get("damage_mitigated", 0) for g in games),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_durability_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = DurabilityEngine(player_id)
        return engine.analyze(games)
    cache_path = cache_path or "C:\\Facecheck\\facecheck_cache.json"
    return run_engine_from_cache(DurabilityEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_durability_engine()
    if output:
        print(f"Durability Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")
