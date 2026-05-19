"""
Combat Engine - Verdict Engine Architecture

Domain: damage and kills.
Extracts total damage, DPM, KP, multi-kills, sprees, bounty, spell casts.
Pure structural extractor — no evaluative thresholds, no "good/bad" judgments.
Signatures describe structural patterns only. Assessment belongs in synthesis.
"""

import json
import statistics
from typing import List, Dict, Optional
from datetime import datetime

from verdict_engine_base import Distribution, EngineNode, EngineSignature, EngineOutput, run_engine_from_cache
from verdict_game_model import Game


class CombatEngine:
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
            engine_name="combat",
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
        damage = game.damage
        gold = game.gold
        deaths = game.deaths

        # Damage efficiency node
        if damage > 0:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"dmg_{match_id}"),
                timestamp_min=duration / 2,
                node_type="damage_efficiency",
                value=damage / max(gold, 1),
                context={
                    "match_id": match_id,
                    "damage": damage,
                    "gold": gold,
                    "deaths": deaths,
                    "win": win,
                    "champion": game.champion,
                    "kp": game.kp_pct,
                }
            ))

        # Kill participation node
        kp = game.kp_pct
        if kp:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"kp_{match_id}"),
                timestamp_min=duration / 2,
                node_type="kill_participation",
                value=kp,
                context={
                    "match_id": match_id,
                    "kp_pct": kp,
                    "win": win,
                }
            ))

        # DPM node
        dpm = game.damage_per_min
        if dpm:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"dpm_{match_id}"),
                timestamp_min=duration / 2,
                node_type="damage_per_min",
                value=dpm,
                context={
                    "match_id": match_id,
                    "dpm": dpm,
                    "win": win,
                }
            ))

        # Multi-kill node
        multi = game.double_kills + game.triple_kills + game.quadra_kills + game.penta_kills
        if multi > 0 or game.largest_killing_spree > 0:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"multi_{match_id}"),
                timestamp_min=duration / 2,
                node_type="multi_kill",
                value=multi,
                context={
                    "match_id": match_id,
                    "double_kills": game.double_kills,
                    "triple_kills": game.triple_kills,
                    "quadra_kills": game.quadra_kills,
                    "penta_kills": game.penta_kills,
                    "largest_killing_spree": game.largest_killing_spree,
                    "win": win,
                }
            ))

        # Bounty node
        bounty = game.bounty_level
        if bounty:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"bounty_{match_id}"),
                timestamp_min=duration / 2,
                node_type="bounty",
                value=bounty,
                context={
                    "match_id": match_id,
                    "bounty_level": bounty,
                    "win": win,
                }
            ))

        # Spell casts node
        spell_casts = game.spell1_casts + game.spell2_casts + game.spell3_casts + game.spell4_casts
        if spell_casts > 0:
            self.nodes.append(EngineNode(
                node_id=self._make_node_id(f"spells_{match_id}"),
                timestamp_min=duration / 2,
                node_type="spell_casts",
                value=spell_casts,
                context={
                    "match_id": match_id,
                    "spell_casts": spell_casts,
                    "win": win,
                }
            ))

    def _detect_signatures(self, games: List[Game]):
        """
        Detect structural combat patterns only.
        No evaluative thresholds — only factual cross-field profiles and event flags.
        """
        signatures = []

        for game in games:
            match_id = game.match_id
            win = game.win
            duration = game.duration_min
            damage = game.damage
            kp = game.kp_pct
            deaths = game.deaths
            dpm = game.damage_per_min
            gold = game.gold
            assists = game.assists
            kills = game.kills

            # ── Structural Pattern 1: Combat Profile ──
            # Cross-field structural record for every game with combat data.
            # Captures the relationship between damage, KP, and deaths as a factual unit.
            if damage > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"combat_sig_{match_id}"),
                    signature_type="combat_profile",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "damage": damage,
                        "dpm": dpm,
                        "kp_pct": kp,
                        "deaths": deaths,
                        "kills": kills,
                        "assists": assists,
                        "damage_per_gold": round(damage / max(gold, 1), 2),
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.8
                ))

            # ── Structural Pattern 2: Multi-Kill Event ──
            multi = game.double_kills + game.triple_kills + game.quadra_kills + game.penta_kills
            if multi > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"combat_sig_{match_id}"),
                    signature_type="multi_kill_event",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "multi_kill_total": multi,
                        "double_kills": game.double_kills,
                        "triple_kills": game.triple_kills,
                        "quadra_kills": game.quadra_kills,
                        "penta_kills": game.penta_kills,
                        "largest_spree": game.largest_killing_spree,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.85
                ))

            # ── Structural Pattern 3: Killing Spree Event ──
            spree = game.largest_killing_spree
            if spree >= 3:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"combat_sig_{match_id}"),
                    signature_type="killing_spree_event",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "largest_spree": spree,
                        "kills": kills,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.8
                ))

            # ── Structural Pattern 4: Bounty Event ──
            bounty = game.bounty_level
            if bounty > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"combat_sig_{match_id}"),
                    signature_type="bounty_acquired",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "bounty_level": bounty,
                        "kills": kills,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.7
                ))

            # ── Structural Pattern 5: Spell Cast Intensity ──
            spell_casts = game.spell1_casts + game.spell2_casts + game.spell3_casts + game.spell4_casts
            if spell_casts > 0:
                signatures.append(EngineSignature(
                    signature_id=self._make_node_id(f"combat_sig_{match_id}"),
                    signature_type="spell_cast_profile",
                    nodes=[],
                    start_min=0,
                    end_min=duration,
                    features={
                        "total_spell_casts": spell_casts,
                        "casts_per_min": round(spell_casts / max(duration, 1), 1),
                        "spell1_casts": game.spell1_casts,
                        "spell2_casts": game.spell2_casts,
                        "spell3_casts": game.spell3_casts,
                        "spell4_casts": game.spell4_casts,
                        "game_duration": duration,
                        "win": win,
                    },
                    confidence=0.75
                ))

        self.signatures = signatures

    def _build_distributions(self, games: List[Game]) -> Dict[str, Distribution]:
        distributions = {}
        damages = [g.damage for g in games if g.damage]
        if damages:
            distributions["total_damage"] = Distribution.from_values(damages)
        dpms = [g.damage_per_min for g in games if g.damage_per_min]
        if dpms:
            distributions["damage_per_min"] = Distribution.from_values(dpms)
        kps = [g.kp_pct for g in games if g.kp_pct]
        if kps:
            distributions["kill_participation"] = Distribution.from_values(kps)
        dpg = [g.damage / max(g.gold, 1) for g in games]
        distributions["damage_per_gold"] = Distribution.from_values(dpg)
        dpd = [g.damage / max(g.deaths, 1) for g in games if g.deaths > 0]
        if dpd:
            distributions["damage_per_death"] = Distribution.from_values(dpd)
        sprees = [g.largest_killing_spree for g in games]
        if any(sprees):
            distributions["killing_spree"] = Distribution.from_values(sprees)
        multi = [g.double_kills + g.triple_kills + g.quadra_kills + g.penta_kills for g in games]
        if any(multi):
            distributions["multi_kills"] = Distribution.from_values(multi)
        return distributions

    def _build_correlation_space(self, games: List[Game]) -> Dict[str, List[float]]:
        return {
            "damage": [g.damage for g in games],
            "damage_per_min": [g.damage_per_min for g in games],
            "kp_pct": [g.kp_pct for g in games],
            "deaths": [g.deaths for g in games],
            "damage_per_gold": [g.damage / max(g.gold, 1) for g in games],
            "multi_kills": [g.double_kills + g.triple_kills + g.quadra_kills + g.penta_kills for g in games],
            "largest_spree": [g.largest_killing_spree for g in games],
            "bounty_level": [g.bounty_level or 0 for g in games],
            "spell_casts": [g.spell1_casts + g.spell2_casts + g.spell3_casts + g.spell4_casts for g in games],
        }

    def _calculate_confidence(self, games: List[Game]) -> float:
        if not games:
            return 0.0
        factors = [min(len(games) / 20, 1.0)]
        complete = sum(1 for g in games if g.damage and g.kp_pct) / len(games)
        factors.append(complete)
        return statistics.mean(factors)

    def _extract_raw_metrics(self, games: List[Game]) -> Dict:
        return {
            "total_games_analyzed": len(games),
            "games_with_damage_data": len([g for g in games if g.damage]),
            "games_with_kp_data": len([g for g in games if g.kp_pct]),
            "total_damage_recorded": sum(g.damage for g in games),
            "total_nodes_created": len(self.nodes),
            "total_signatures_detected": len(self.signatures),
        }


def run_combat_engine(games=None, player_id=None, cache_path=None) -> Optional[EngineOutput]:
    if games is not None and player_id is not None:
        engine = CombatEngine(player_id)
        return engine.analyze(games)
    if cache_path is None:
        from verdict_paths import CACHE_PATH
        cache_path = CACHE_PATH
    return run_engine_from_cache(CombatEngine, cache_path, games=games, player_id=player_id)


if __name__ == "__main__":
    output = run_combat_engine()
    if output:
        print(f"Combat Engine: {len(output.nodes)} nodes, {len(output.signatures)} signatures")
        for name, dist in output.distributions.items():
            print(f"  {name}: mean={dist.mean:.1f}, n={dist.sample_size}")
        types = {}
        for s in output.signatures:
            types[s.signature_type] = types.get(s.signature_type, 0) + 1
        for t, c in sorted(types.items()):
            print(f"  {t}: {c}")
    else:
        print("No data available.")