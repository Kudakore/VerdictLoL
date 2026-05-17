"""
Death Engine - Verdict Engine Architecture

Domain: survival and tempo.
Extracts death timing, clusters, chains, gaps, phase concentration, survival profiles.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from collections import defaultdict
from typing import List, Dict, Optional
from datetime import datetime

from verdict_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache


class DeathEngine:
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

        self._link_nodes_within_games()
        self._detect_signatures(games)
        distributions = self._build_distributions(games)
        correlation_space = self._build_correlation_space(games)

        return EngineOutput(
            engine_name="death",
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

        # Death nodes
        death_minutes = game.get("death_minutes", [])
        for i, death_min in enumerate(death_minutes):
            node = EngineNode(
                node_id=self._make_node_id(f"death_{match_id}"),
                timestamp_min=death_min,
                node_type="death",
                value=death_min,
                context={
                    "match_id": match_id,
                    "death_number": i + 1,
                    "total_deaths": len(death_minutes),
                    "game_duration": duration,
                    "win": game.get("win", False),
                    "champion": game.get("champion", ""),
                    "early": death_min <= 10,
                }
            )
            self.nodes.append(node)

        # Survival checkpoint (longest living)
        longest_living = game.get("longest_living", 0)
        if longest_living:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"survival_{match_id}"),
                timestamp_min=duration,
                node_type="survival_checkpoint",
                value=longest_living,
                context={
                    "match_id": match_id,
                    "longest_living_sec": longest_living,
                    "longest_living_min": longest_living / 60,
                    "game_duration": duration,
                    "win": game.get("win", False),
                }
            ))

        # Time spent dead
        time_spent_dead = game.get("time_spent_dead", 0)
        if time_spent_dead:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"tsd_{match_id}"),
                timestamp_min=duration,
                node_type="time_spent_dead",
                value=time_spent_dead,
                context={
                    "match_id": match_id,
                    "time_spent_dead_sec": time_spent_dead,
                    "time_spent_dead_min": time_spent_dead / 60,
                    "game_duration": duration,
                    "win": game.get("win", False),
                }
            ))

    def _link_nodes_within_games(self):
        """Establish chronological neighbor relationships between nodes within each game."""
        by_game = defaultdict(list)
        for node in self.nodes:
            by_game[node.context.get("match_id", "")].append(node)

        for match_id, game_nodes in by_game.items():
            sorted_nodes = sorted(game_nodes, key=lambda n: n.timestamp_min)
            for i, node in enumerate(sorted_nodes):
                neighbors = {}
                if i > 0:
                    neighbors["prev_node"] = sorted_nodes[i - 1].node_id
                if i < len(sorted_nodes) - 1:
                    neighbors["next_node"] = sorted_nodes[i + 1].node_id
                node.context.update(neighbors)

    def _detect_signatures(self, games: List[Dict]):
        """
        Detect structural death patterns only.
        No evaluative thresholds — only temporal and structural facts.
        """
        signatures = []
        by_game = defaultdict(list)
        for node in self.nodes:
            by_game[node.context.get("match_id", "")].append(node)

        for match_id, nodes in by_game.items():
            game = next((g for g in games if g.get("match_id") == match_id), {})
            sorted_nodes = sorted(nodes, key=lambda n: n.timestamp_min)
            death_nodes = [n for n in sorted_nodes if n.node_type == "death"]
            duration = game.get("duration_min", 30)
            win = game.get("win", False)

            if not death_nodes:
                continue

            # ── Structural Pattern 1: Death Clusters ──
            # 2+ deaths within 4 minutes of each other
            if len(death_nodes) >= 2:
                clusters = []
                current = [death_nodes[0]]
                for i in range(1, len(death_nodes)):
                    gap = death_nodes[i].timestamp_min - death_nodes[i - 1].timestamp_min
                    if gap <= 4:
                        current.append(death_nodes[i])
                    else:
                        if len(current) >= 2:
                            clusters.append(current)
                        current = [death_nodes[i]]
                if len(current) >= 2:
                    clusters.append(current)

                for cluster in clusters:
                    signatures.append(EngineSignature(
                        signature_id=self._make_node_id(f"sig_{match_id}"),
                        signature_type="death_cluster",
                        nodes=[n.node_id for n in cluster],
                        start_min=cluster[0].timestamp_min,
                        end_min=cluster[-1].timestamp_min,
                        features={
                            "cluster_size": len(cluster),
                            "gap_minutes": cluster[-1].timestamp_min - cluster[0].timestamp_min,
                            "death_positions": [n.timestamp_min for n in cluster],
                            "total_deaths": len(death_nodes),
                            "game_duration": duration,
                            "win": win,
                        },
                        confidence=min(0.5 + 0.1 * len(cluster), 0.95)
                    ))

            # ── Structural Pattern 2: Death Chain ──
            # 3+ deaths with monotonically decreasing gaps (accelerating death rate)
            if len(death_nodes) >= 3:
                gaps = []
                for i in range(1, len(death_nodes)):
                    gaps.append(death_nodes[i].timestamp_min - death_nodes[i - 1].timestamp_min)

                chain_start = 0
                for i in range(1, len(gaps)):
                    if gaps[i] < gaps[i - 1]:
                        if i - chain_start >= 2:
                            chain_nodes = death_nodes[chain_start:i + 1]
                            signatures.append(EngineSignature(
                                signature_id=self._make_node_id(f"sig_{match_id}"),
                                signature_type="death_chain",
                                nodes=[n.node_id for n in chain_nodes],
                                start_min=chain_nodes[0].timestamp_min,
                                end_min=chain_nodes[-1].timestamp_min,
                                features={
                                    "chain_length": len(chain_nodes),
                                    "initial_gap": gaps[chain_start],
                                    "final_gap": gaps[i - 1],
                                    "gap_sequence": gaps[chain_start:i],
                                    "total_deaths": len(death_nodes),
                                    "game_duration": duration,
                                    "win": win,
                                },
                                confidence=min(0.6 + 0.1 * len(chain_nodes), 0.95)
                            ))
                            chain_start = i
                    else:
                        chain_start = i

            # ── Structural Pattern 3: Extreme Survival Gap ──
            # Longest interval between consecutive deaths > 15 minutes
            if len(death_nodes) >= 2:
                max_gap = 0
                max_gap_idx = 0
                for i in range(1, len(death_nodes)):
                    gap = death_nodes[i].timestamp_min - death_nodes[i - 1].timestamp_min
                    if gap > max_gap:
                        max_gap = gap
                        max_gap_idx = i

                if max_gap > 15:
                    signatures.append(EngineSignature(
                        signature_id=self._make_node_id(f"sig_{match_id}"),
                        signature_type="survival_gap",
                        nodes=[death_nodes[max_gap_idx - 1].node_id, death_nodes[max_gap_idx].node_id],
                        start_min=death_nodes[max_gap_idx - 1].timestamp_min,
                        end_min=death_nodes[max_gap_idx].timestamp_min,
                        features={
                            "gap_minutes": max_gap,
                            "gap_relative_to_duration": max_gap / duration,
                            "deaths_before_gap": max_gap_idx,
                            "deaths_after_gap": len(death_nodes) - max_gap_idx,
                            "total_deaths": len(death_nodes),
                            "game_duration": duration,
                            "win": win,
                        },
                        confidence=min(0.6 + 0.05 * max_gap, 0.95)
                    ))

            # ── Structural Pattern 4: Death Phase Concentration ──
            # 60%+ of deaths concentrated in a single game phase
            early_deaths = len([n for n in death_nodes if n.timestamp_min <= 10])
            mid_deaths = len([n for n in death_nodes if 10 < n.timestamp_min <= 20])
            late_deaths = len([n for n in death_nodes if n.timestamp_min > 20])
            total = len(death_nodes)

            for phase, count in [("early", early_deaths), ("mid", mid_deaths), ("late", late_deaths)]:
                if count >= 3 and count / total >= 0.6:
                    signatures.append(EngineSignature(
                        signature_id=self._make_node_id(f"sig_{match_id}"),
                        signature_type="death_phase_concentration",
                        nodes=[n.node_id for n in death_nodes],
                        start_min=0,
                        end_min=duration,
                        features={
                            "concentrated_phase": phase,
                            "phase_death_count": count,
                            "phase_ratio": count / total,
                            "early_deaths": early_deaths,
                            "mid_deaths": mid_deaths,
                            "late_deaths": late_deaths,
                            "total_deaths": total,
                            "game_duration": duration,
                            "win": win,
                        },
                        confidence=min(0.5 + 0.15 * (count / total), 0.95)
                    ))
                    break

            # ── Structural Pattern 5: Survival Profile ──
            # Aggregate survival metrics for the game
            survival_nodes = [n for n in sorted_nodes if n.node_type == "time_spent_dead"]
            longest_nodes = [n for n in sorted_nodes if n.node_type == "survival_checkpoint"]

            if survival_nodes or longest_nodes:
                tsd = survival_nodes[0].value if survival_nodes else 0
                ll = longest_nodes[0].value if longest_nodes else 0
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"sig_{match_id}"),
                    signature_type="survival_profile",
                    nodes=[n.node_id for n in survival_nodes + longest_nodes],
                    start_min=0,
                    end_min=duration,
                    features={
                        "time_spent_dead_sec": tsd,
                        "time_spent_dead_min": round(tsd / 60, 1) if tsd else 0,
                        "longest_living_sec": ll,
                        "longest_living_min": round(ll / 60, 1) if ll else 0,
                        "death_count": len(death_nodes),
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.7 if (tsd and ll) else 0.5
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Dict]) -> Dict[str, Distribution]:
        distributions = {}

        all_death_minutes = []
        for game in games:
            all_death_minutes.extend(game.get("death_minutes", []))
        if all_death_minutes:
            distributions["death_timing"] = Distribution.from_values(all_death_minutes)

        deaths_per_game = [g.get("deaths", 0) for g in games]
        distributions["deaths_per_game"] = Distribution.from_values(deaths_per_game)

        early_deaths = [g.get("early_deaths", 0) for g in games]
        distributions["early_deaths"] = Distribution.from_values(early_deaths)

        longest_living_vals = [g.get("longest_living", 0) for g in games if g.get("longest_living")]
        if any(longest_living_vals):
            distributions["longest_living"] = Distribution.from_values(longest_living_vals)

        time_spent_dead_vals = [g.get("time_spent_dead", 0) for g in games if g.get("time_spent_dead")]
        if any(time_spent_dead_vals):
            distributions["time_spent_dead"] = Distribution.from_values(time_spent_dead_vals)

        return distributions

    def _build_correlation_space(self, games: List[Dict]) -> Dict[str, List[float]]:
        space = {}
        space["death_count"] = [g.get("deaths", 0) for g in games]
        space["death_minute_avg"] = [
            statistics.mean(g.get("death_minutes", [0])) if g.get("death_minutes") else 0
            for g in games
        ]
        space["early_deaths"] = [g.get("early_deaths", 0) for g in games]
        space["longest_living"] = [g.get("longest_living", 0) or 0 for g in games]
        space["time_spent_dead"] = [g.get("time_spent_dead", 0) or 0 for g in games]
        return space

    def _calculate_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        factors = []
        n = len(games)
        factors.append(min(n / 20, 1.0))
        completeness = sum(1 for g in games if g.get("death_minutes")) / n
        factors.append(completeness)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Dict]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_death_data": len([g for g in games if g.get("death_minutes")]),
            "games_with_longest_living": len([g for g in games if g.get("longest_living")]),
            "games_with_time_spent_dead": len([g for g in games if g.get("time_spent_dead")]),
            "total_deaths_recorded": sum(len(g.get("death_minutes", [])) for g in games),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_death_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = DeathEngine(player_id)
        return engine.analyze(games)
    cache_path = cache_path or "C:\\Facecheck\\verdict_cache.json"
    return run_engine_from_cache(DeathEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_death_engine()
    if output:
        print(f"Death Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")
