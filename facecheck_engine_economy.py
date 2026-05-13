"""
Economy Engine - FaceCheck Engine Architecture

Domain: resources and itemization.
Extracts CS curves, gold trajectories, item timing, first clear.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from collections import defaultdict
from typing import List, Dict, Optional
from datetime import datetime

from facecheck_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache


class EconomyEngine:
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
            engine_name="economy",
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

        # CS checkpoint nodes (every 5 min from jungle_pathing)
        jp = game.get("jungle_pathing", {})
        cs_by_min = jp.get("cs_by_minute", {}) if jp else {}
        for minute in range(5, int(duration) + 1, 5):
            cs = cs_by_min.get(str(minute)) or cs_by_min.get(minute, 0)
            if cs > 0:
                self.nodes.append(EngineNode(
                    node_id=self._make_node_id(f"cs_{match_id}"),
                    timestamp_min=minute,
                    node_type="cs_checkpoint",
                    value=cs,
                    context={
                        "match_id": match_id,
                        "checkpoint": minute,
                        "cs_total": cs,
                        "cs_per_min": cs / minute if minute > 0 else 0,
                        "win": win,
                    }
                ))

        # Gold checkpoint at 15
        gold_15 = game.get("gold_15")
        if gold_15:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"gold15_{match_id}"),
                timestamp_min=15,
                node_type="gold_checkpoint",
                value=gold_15,
                context={
                    "match_id": match_id,
                    "gold_15": gold_15,
                    "gold_lead_15": game.get("gold_lead_15"),
                    "win": win,
                }
            ))

        # First clear node
        if jp and jp.get("first_clear_min"):
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"fc_{match_id}"),
                timestamp_min=jp["first_clear_min"],
                node_type="first_clear",
                value=jp["first_clear_min"],
                context={
                    "match_id": match_id,
                    "first_clear_min": jp["first_clear_min"],
                    "win": win,
                }
            ))

        # Build order node (first item as proxy for item timing)
        first_item = game.get("first_item")
        if first_item:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"item_{match_id}"),
                timestamp_min=5,  # Approximate first back
                node_type="first_item",
                value=first_item,
                context={
                    "match_id": match_id,
                    "first_item": first_item,
                    "build_order": game.get("build_order", []),
                    "win": win,
                }
            ))

        # CS@10 and CS@15 nodes (static checkpoints)
        for checkpoint, key in [(10, "cs_10"), (15, "cs_15")]:
            cs_val = game.get(key)
            if cs_val:
                self.nodes.append(EngineNode(
                    node_id=self._make_node_id(f"cs{checkpoint}_{match_id}"),
                    timestamp_min=checkpoint,
                    node_type=f"cs_at_{checkpoint}",
                    value=cs_val,
                    context={
                        "match_id": match_id,
                        "cs": cs_val,
                        "win": win,
                    }
                ))

    def _detect_signatures(self, games: List[Dict]):
        """
        Detect structural economy patterns only.
        No evaluative thresholds — only temporal and structural facts.
        """
        signatures = []

        for game in games:
            match_id = game.get("match_id", "")
            win = game.get("win", False)
            duration = game.get("duration_min", 30)
            cs_10 = game.get("cs_10")
            cs_15 = game.get("cs_15")
            gold_lead = game.get("gold_lead_15")
            jp = game.get("jungle_pathing", {}) or {}
            first_clear = jp.get("first_clear_min")
            first_item = game.get("first_item")
            build_order = game.get("build_order", [])

            # ── Structural Pattern 1: CS Checkpoint Sequence ──
            if cs_10 is not None and cs_15 is not None:
                delta = cs_15 - cs_10
                slope = delta / 5 if delta else 0
                direction = "positive" if slope > 2 else ("negative" if slope < -2 else "flat")
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="cs_checkpoint_sequence",
                    nodes=[],
                    start_min=10,
                    end_min=15,
                    features={
                        "cs_10": cs_10,
                        "cs_15": cs_15,
                        "delta_10_to_15": delta,
                        "slope_per_min": round(slope, 1),
                        "slope_direction": direction,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.85
                ))
            elif cs_10 is not None or cs_15 is not None:
                # Partial data — still record which checkpoint exists
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="cs_partial_data",
                    nodes=[],
                    start_min=10 if cs_10 is not None else 15,
                    end_min=15 if cs_15 is not None else 10,
                    features={
                        "cs_10": cs_10,
                        "cs_15": cs_15,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.5
                ))

            # ── Structural Pattern 2: Gold Checkpoint ──
            if gold_lead is not None:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="gold_checkpoint",
                    nodes=[],
                    start_min=0,
                    end_min=15,
                    features={
                        "gold_lead_15": gold_lead,
                        "gold_15": game.get("gold_15"),
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.8
                ))

            # ── Structural Pattern 3: First Clear Timing ──
            if first_clear is not None:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="first_clear_timing",
                    nodes=[],
                    start_min=0,
                    end_min=first_clear,
                    features={
                        "first_clear_min": first_clear,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.9
                ))

            # ── Structural Pattern 4: Item Purchase Sequence ──
            if first_item and build_order:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="item_purchase_sequence",
                    nodes=[],
                    start_min=0,
                    end_min=5,
                    features={
                        "first_item": first_item,
                        "build_order_length": len(build_order),
                        "build_order": build_order[:6],
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.85
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Dict]) -> Dict[str, Distribution]:
        distributions = {}

        cs_10_values = [g.get("cs_10", 0) for g in games if g.get("cs_10")]
        if cs_10_values:
            distributions["cs_at_10"] = Distribution.from_values(cs_10_values)

        cs_15_values = [g.get("cs_15", 0) for g in games if g.get("cs_15")]
        if cs_15_values:
            distributions["cs_at_15"] = Distribution.from_values(cs_15_values)

        cs_per_min = [g.get("cs_per_min", 0) for g in games if g.get("cs_per_min")]
        if cs_per_min:
            distributions["cs_per_min"] = Distribution.from_values(cs_per_min)

        gold_lead_15 = [g.get("gold_lead_15", 0) or 0 for g in games]
        if any(gold_lead_15):
            distributions["gold_lead_15"] = Distribution.from_values(gold_lead_15)

        gold_15 = [g.get("gold_15", 0) or 0 for g in games if g.get("gold_15")]
        if any(gold_15):
            distributions["gold_15"] = Distribution.from_values(gold_15)

        gpm = [g.get("gold_per_min", 0) or 0 for g in games if g.get("gold_per_min")]
        if any(gpm):
            distributions["gold_per_min"] = Distribution.from_values(gpm)

        first_clears = []
        for game in games:
            jp = game.get("jungle_pathing", {})
            if jp and jp.get("first_clear_min"):
                first_clears.append(jp["first_clear_min"])
        if first_clears:
            distributions["first_clear_timing"] = Distribution.from_values(first_clears)

        return distributions

    def _build_correlation_space(self, games: List[Dict]) -> Dict[str, List[float]]:
        space = {}
        space["cs_at_10"] = [g.get("cs_10", 0) or 0 for g in games]
        space["cs_at_15"] = [g.get("cs_15", 0) or 0 for g in games]
        space["cs_per_min"] = [g.get("cs_per_min", 0) or 0 for g in games]
        space["gold_lead_15"] = [g.get("gold_lead_15", 0) or 0 for g in games]
        space["gold_15"] = [g.get("gold_15", 0) or 0 for g in games]
        space["gold_per_min"] = [g.get("gold_per_min", 0) or 0 for g in games]
        space["first_clear_min"] = [
            (g.get("jungle_pathing", {}) or {}).get("first_clear_min", 0) or 0
            for g in games
        ]
        return space

    def _calculate_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        factors = [min(len(games) / 20, 1.0)]
        scores = []
        for g in games:
            score = 0
            if g.get("cs_10"): score += 0.3
            if g.get("cs_15"): score += 0.2
            if g.get("gold_15"): score += 0.3
            if g.get("jungle_pathing"): score += 0.2
            scores.append(score)
        factors.append(statistics.mean(scores) if scores else 0)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Dict]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_cs_data": len([g for g in games if g.get("cs_10") or g.get("cs_15")]),
            "games_with_gold_data": len([g for g in games if g.get("gold_15")]),
            "games_with_jungle_pathing": len([g for g in games if g.get("jungle_pathing")]),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_economy_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = EconomyEngine(player_id)
        return engine.analyze(games)
    cache_path = cache_path or "C:\\Facecheck\\facecheck_cache.json"
    return run_engine_from_cache(EconomyEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_economy_engine()
    if output:
        print(f"Economy Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")
