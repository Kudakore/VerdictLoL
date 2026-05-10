"""
Draft Engine - FaceCheck Engine Architecture

Domain: champion select and draft position.
Extracts pick order, side, role, champion selection patterns.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from collections import defaultdict
from typing import List, Dict, Optional
from datetime import datetime

from facecheck_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput


class DraftEngine:
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
            engine_name="draft",
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
        win = game.get("win", False)

        # Pick order node
        pick_order = game.get("pick_order")
        if pick_order:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"pick_{match_id}"),
                timestamp_min=0,
                node_type="pick_order",
                value=pick_order,
                context={
                    "match_id": match_id,
                    "pick_order": pick_order,
                    "enemy_pick_order": game.get("enemy_pick_order"),
                    "side": game.get("side"),
                    "role": game.get("role"),
                    "champion": game.get("champion", ""),
                    "win": win,
                }
            ))

        # Side node
        side = game.get("side")
        if side:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"side_{match_id}"),
                timestamp_min=0,
                node_type="side",
                value=side,
                context={
                    "match_id": match_id,
                    "side": side,
                    "win": win,
                }
            ))

        # Role node
        role = game.get("role")
        if role:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"role_{match_id}"),
                timestamp_min=0,
                node_type="role",
                value=role,
                context={
                    "match_id": match_id,
                    "role": role,
                    "win": win,
                }
            ))

        # Champion node
        champion = game.get("champion")
        if champion:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"champ_{match_id}"),
                timestamp_min=0,
                node_type="champion",
                value=champion,
                context={
                    "match_id": match_id,
                    "champion": champion,
                    "win": win,
                }
            ))

    def _detect_signatures(self, games: List[Dict]):
        """
        Detect structural draft patterns only.
        No evaluative thresholds — only positional and selection facts.
        """
        signatures = []

        # Precompute champion streaks across all games
        champion_games = defaultdict(list)
        for g in games:
            champ = g.get("champion")
            if champ:
                champion_games[champ].append(g)

        for game in games:
            match_id = game.get("match_id", "")
            win = game.get("win", False)
            pick_order = game.get("pick_order")
            side = game.get("side")
            role = game.get("role")
            champion = game.get("champion", "")
            enemy_pick = game.get("enemy_pick_order")

            # ── Structural Pattern 1: Pick Position ──
            if pick_order:
                position = "early" if pick_order <= 2 else ("late" if pick_order >= 4 else "mid")
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="pick_position",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "pick_order": pick_order,
                        "position_label": position,
                        "champion": champion,
                        "win": win,
                    },
                    confidence=0.9
                ))

            # ── Structural Pattern 2: Side Assignment ──
            if side:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="side_assignment",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "side": side,
                        "champion": champion,
                        "win": win,
                    },
                    confidence=0.9
                ))

            # ── Structural Pattern 3: Counter Pick Relation ──
            if pick_order and enemy_pick:
                relation = "counter" if pick_order > enemy_pick else ("blind" if pick_order < enemy_pick else "same")
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="counter_pick_relation",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "my_pick_order": pick_order,
                        "enemy_pick_order": enemy_pick,
                        "relation": relation,
                        "champion": champion,
                        "win": win,
                    },
                    confidence=0.85
                ))

            # ── Structural Pattern 4: Role Assignment ──
            if role:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="role_assignment",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "role": role,
                        "champion": champion,
                        "win": win,
                    },
                    confidence=0.9
                ))

            # ── Structural Pattern 5: Champion Repetition ──
            # Cross-game structural pattern: 3+ games on same champion
            champ_games = champion_games.get(champion, [])
            if len(champ_games) >= 3:
                champ_wr = sum(1 for g in champ_games if g["win"]) / len(champ_games)
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="champion_repetition",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "champion": champion,
                        "games_on_champ": len(champ_games),
                        "champ_wr": round(champ_wr, 3),
                        "win": win,
                    },
                    confidence=0.7
                ))

            # ── Structural Pattern 6: Draft Sequence ──
            # Combined structural snapshot of this game's draft position
            if pick_order or side or role:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"draft_sig_{match_id}"),
                    signature_type="draft_sequence",
                    nodes=[],
                    start_min=0,
                    end_min=0,
                    features={
                        "pick_order": pick_order,
                        "side": side,
                        "role": role,
                        "champion": champion,
                        "enemy_pick_order": enemy_pick,
                        "win": win,
                    },
                    confidence=0.8
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Dict]) -> Dict[str, Distribution]:
        distributions = {}
        pick_orders = [g.get("pick_order", 0) for g in games if g.get("pick_order")]
        if pick_orders:
            distributions["pick_order"] = Distribution.from_values(pick_orders)
        return distributions

    def _build_correlation_space(self, games: List[Dict]) -> Dict[str, List[float]]:
        return {
            "pick_order": [g.get("pick_order", 0) or 0 for g in games],
            "enemy_pick_order": [g.get("enemy_pick_order", 0) or 0 for g in games],
            "side_blue": [1 if g.get("side") == "blue" else 0 for g in games],
            "side_red": [1 if g.get("side") == "red" else 0 for g in games],
            "role": [hash(g.get("role", "")) % 100 for g in games],  # Numeric proxy
            "champion_hash": [hash(g.get("champion", "")) % 1000 for g in games],
        }

    def _calculate_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        return min(len(games) / 20, 1.0)

    def _extract_raw_metrics(self, games: List[Dict]) -> Dict:
        sides = [g.get("side") for g in games if g.get("side")]
        roles = [g.get("role") for g in games if g.get("role")]
        champions = [g.get("champion") for g in games if g.get("champion")]
        return {
            "total_games_analyzed": len(games),
            "games_with_pick_order": len([g for g in games if g.get("pick_order")]),
            "games_with_side": len(sides),
            "games_with_role": len(roles),
            "unique_champions": len(set(champions)),
            "blue_games": len([s for s in sides if s == "blue"]),
            "red_games": len([s for s in sides if s == "red"]),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_draft_engine(cache_path: str = "C:\\Scripts\\facecheck_cache.json") -> Optional[EngineOutput]:
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    games = cache.get("games", [])
    player_id = cache.get("puuid", "")
    if not games:
        return None
    engine = DraftEngine(player_id)
    return engine.analyze(games)


if __name__ == "__main__":
    output = run_draft_engine()
    if output:
        print(f"Draft Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")
