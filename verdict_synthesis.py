"""
Synthesis Layer - Verdict Engine Architecture

Correlates engine outputs, matches patterns, generates verdicts.
The synthesis layer owns the narrative — not just findings, but verdicts.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import statistics

from verdict_engine_base import EngineOutput, EngineSignature
from verdict_player_model import PlayerModel, PatternMemory, PlayerBaseline
from verdict_game_model import Game
from verdict_similarity import (
    SimilarityEngine, SimilarityOutput, SimilarityResult,
    GameFingerprint, ClusterResult, DiscoveredSignal, PatternResult
)


@dataclass
class MultiEngineOutput:
    """Container for multiple engine outputs."""
    death: Optional[EngineOutput] = None
    economy: Optional[EngineOutput] = None
    combat: Optional[EngineOutput] = None
    durability: Optional[EngineOutput] = None
    vision: Optional[EngineOutput] = None
    objective: Optional[EngineOutput] = None
    draft: Optional[EngineOutput] = None

    def to_dict(self) -> Dict:
        return {
            "death": self.death.to_dict() if self.death else None,
            "economy": self.economy.to_dict() if self.economy else None,
            "combat": self.combat.to_dict() if self.combat else None,
            "durability": self.durability.to_dict() if self.durability else None,
            "vision": self.vision.to_dict() if self.vision else None,
            "objective": self.objective.to_dict() if self.objective else None,
            "draft": self.draft.to_dict() if self.draft else None,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MultiEngineOutput":
        from verdict_engine_base import EngineOutput
        return cls(
            death=EngineOutput.from_dict(d["death"]) if d.get("death") else None,
            economy=EngineOutput.from_dict(d["economy"]) if d.get("economy") else None,
            combat=EngineOutput.from_dict(d["combat"]) if d.get("combat") else None,
            durability=EngineOutput.from_dict(d["durability"]) if d.get("durability") else None,
            vision=EngineOutput.from_dict(d["vision"]) if d.get("vision") else None,
            objective=EngineOutput.from_dict(d["objective"]) if d.get("objective") else None,
            draft=EngineOutput.from_dict(d["draft"]) if d.get("draft") else None,
        )


@dataclass
class Evidence:
    """Supporting evidence for a verdict."""
    evidence_type: str  # "stat", "pattern", "correlation"
    description: str
    value: any
    context: str  # How this relates to the verdict


@dataclass
class Lesson:
    """Actionable lesson derived from the verdict."""
    lesson_type: str  # "immediate", "practice", "mindset"
    text: str
    priority: str  # "high", "medium", "low"


@dataclass
class Observation:
    """A compositional narrative unit produced by an observation producer.
    Multiple observations are collected, scored, and composed into a verdict."""
    obs_type: str       # e.g. "death_cluster", "inefficient_combat"
    label: str          # short label, e.g. "death cluster"
    statement: str      # full sentence for this observation
    score: float        # priority score (0.0–1.0), higher = more important
    data: dict          # supporting data for rendering
    priority: str       # "critical", "high", "medium", "low"


@dataclass
class Verdict:
    """A synthesis verdict about a game or pattern."""
    verdict_id: str
    timestamp: datetime
    verdict_type: str  # "fractal_analysis", "pattern_match", "anomaly"

    # The core verdict
    statement: str  # One sentence verdict
    confidence: float  # 0-1

    # Supporting structure
    summary: str  # 1-2 sentence expansion
    explanation: str  # Deeper explanation
    primary_evidence: List[Evidence] = field(default_factory=list)
    lessons: List[Lesson] = field(default_factory=list)

    # Pattern matching
    matched_patterns: List[str] = field(default_factory=list)  # Pattern IDs that matched
    divergences: List[str] = field(default_factory=list)  # Where this game diverged from pattern

    # Reasoning layer (Phase 1)
    similar_games: List[str] = field(default_factory=list)  # match_ids of structurally similar games
    cluster_label: str = ""                                   # Behavioral cluster label for this game
    counterfactual_insight: str = ""                         # Counterfactual delta from SimilarityEngine
    mechanism: str = ""                                      # Named mechanism of the loss/win
    pattern_insight: str = ""                               # Co-occurring pattern info (Phase 2)

    # Compositional observations (Phase E)
    observations: list = field(default_factory=list)  # List[Observation], scored and sorted

    # Drill-down (optional)
    drill_down_available: bool = False
    drill_down_prompt: str = ""


class SynthesisLayer:
    """
    Synthesizes engine outputs and player model into verdicts.

    Core responsibility: Find meaning in the data.
    Phase 1 upgrade: reasoning queries against SimilarityEngine output.
    """

    def __init__(self, player_model: PlayerModel,
                 similarity_output: Optional[SimilarityOutput] = None,
                 cluster_membership: Optional[Dict[str, int]] = None):
        self.player_model = player_model
        self.similarity_output = similarity_output
        self.cluster_membership = cluster_membership or {}

    # ─────────────────────────────────────────────
    # OBSERVATION PRODUCERS (Phase E)
    # ─────────────────────────────────────────────

    def observe_death_cluster(self, game, signatures, baseline, engines):
        """Death cluster: multiple deaths within a short window."""
        win = game.win
        if win:
            return None
        death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
        death_chains = self._get_signatures_by_type(signatures, "death_chain")
        if not death_clusters:
            return None
        cluster = death_clusters[0]
        gap = cluster.features.get("gap_minutes", 0)
        size = cluster.features.get("cluster_size", 2)
        severity_bonus = min(0.25, (size / max(game.deaths, 1)) * 0.2)
        if death_chains:
            chain_length = death_chains[0].features.get("chain_length", size)
            severity_bonus = min(0.2, (chain_length - 2) * 0.1)
            return Observation(
                obs_type="death_chain", label="death chain",
                statement=f"Death chain: {size} deaths in {gap:.0f} minutes with accelerating frequency. {size}x death spiral in {gap:.0f}min window.",
                score=0.7 + severity_bonus, data={"cluster_size": size, "gap_minutes": gap},
                priority="critical"
            )
        return Observation(
            obs_type="death_cluster", label="death cluster",
            statement=f"Death cluster: {size} deaths within {gap:.0f} minutes. {size} deaths in {gap:.0f}min — {(size/max(game.deaths,1))*100:.0f}% of total deaths concentrated.",
            score=0.7 + severity_bonus, data={"cluster_size": size, "gap_minutes": gap},
            priority="critical"
        )

    def observe_death_chain(self, game, signatures, baseline, engines):
        """Death chain: deaths with shrinking gaps (accelerating)."""
        win = game.win
        if win:
            return None
        death_chains = self._get_signatures_by_type(signatures, "death_chain")
        # Only fires if there wasn't also a death_cluster (which already covers chain)
        death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
        if death_clusters:
            return None  # observe_death_cluster handles this
        if not death_chains:
            return None
        chain = death_chains[0]
        length = chain.features.get("chain_length", 3)
        severity_bonus = min(0.2, (length - 2) * 0.1)
        return Observation(
            obs_type="death_chain", label="death chain",
            statement=f"Death chain: {length} deaths with shrinking gaps between them. Gap narrowed with each death.",
            score=0.7 + severity_bonus, data={"chain_length": length},
            priority="critical"
        )

    def observe_efficient_combat(self, game, signatures, baseline, engines):
        """Win with low deaths and high damage — efficient carry."""
        win = game.win
        if not win:
            return None
        combat = self._get_profile_features(signatures, "combat_profile")
        deaths = combat.get("deaths", game.deaths)
        damage = combat.get("damage", game.damage)
        dpm = combat.get("dpm", game.damage_per_min)
        kp = combat.get("kp_pct", game.kp_pct)
        champion = game.champion
        if damage <= 0:
            return None
        death_dist = engines.death.distributions.get("deaths_per_game") if engines.death else None
        damage_dist = engines.combat.distributions.get("damage_per_min") if engines.combat else None
        death_band = self._assess_against_distribution(deaths, death_dist) if death_dist else "unknown"
        dpm_band = self._assess_against_distribution(dpm, damage_dist) if damage_dist else "unknown"
        if death_band in ("bottom_25", "bottom_10") and dpm_band in ("top_25", "top_10"):
            return Observation(
                obs_type="efficient_combat", label="efficient combat",
                statement=f"Efficient combat profile: {dpm:.0f} DPM ({dpm_band} quartile), {kp:.0f}% KP with only {deaths} deaths ({death_band} quartile). {dpm:.0f} DPM per {deaths} death.",
                score=0.7, data={"dpm": dpm, "kp": kp, "deaths": deaths, "death_band": death_band, "dpm_band": dpm_band},
                priority="high"
            )
        return None

    def observe_inefficient_combat(self, game, signatures, baseline, engines):
        """Loss with high deaths and low damage — inefficient combat."""
        win = game.win
        if win:
            return None
        combat = self._get_profile_features(signatures, "combat_profile")
        deaths = combat.get("deaths", game.deaths)
        damage = combat.get("damage", game.damage)
        champion = game.champion
        if deaths <= 0:
            return None
        death_dist = engines.death.distributions.get("deaths_per_game") if engines.death else None
        damage_dist = engines.combat.distributions.get("total_damage") if engines.combat else None
        death_band = self._assess_against_distribution(deaths, death_dist) if death_dist else "unknown"
        damage_band = self._assess_against_distribution(damage, damage_dist) if damage_dist else "unknown"
        if death_band in ("top_25", "top_10") and damage_band in ("bottom_25", "bottom_10"):
            return Observation(
                obs_type="inefficient_combat", label="inefficient combat",
                statement=f"Inefficient combat: {deaths} deaths (top quartile) with {damage//1000}k damage (bottom quartile). {damage//deaths//1000:.1f}k damage per death.",
                score=0.75, data={"deaths": deaths, "damage": damage, "death_band": death_band, "damage_band": damage_band},
                priority="high"
            )
        return None

    def observe_champion_repetition(self, game, signatures, baseline, engines):
        """Multiple games on same champion — familiarity structural factor."""
        win = game.win
        if not win:
            return None
        champion = game.champion
        champ_repetition = self._get_signatures_by_type(signatures, "champion_repetition")
        if not champ_repetition:
            return None
        streak = champ_repetition[0].features.get("games_on_champ", 3)
        wr = champ_repetition[0].features.get("champ_wr", 0.5)
        return Observation(
            obs_type="champion_repetition", label="champion repetition",
            statement=f"Champion repetition: {streak} games on {champion} ({wr:.0%} WR). Win rate across those {streak} games.",
            score=0.6, data={"games_on_champ": streak, "champ_wr": wr},
            priority="medium"
        )

    def observe_countered(self, game, signatures, baseline, engines):
        """Picked after enemy same-role (had matchup info) but lost anyway."""
        win = game.win
        if win:
            return None
        counter_relation = self._get_signatures_by_type(signatures, "counter_pick_relation")
        if not counter_relation:
            return None
        relation = counter_relation[0].features.get("relation", "")
        if relation != "counter":
            return None
        enemy_champ = game.enemy.champion if game.enemy else "unknown"
        return Observation(
            obs_type="countered", label="countered in draft",
            statement=f"Countered in draft: picked after enemy {enemy_champ} same-role but lost despite having matchup info.",
            score=0.55, data={"champion": game.champion, "enemy_champion": enemy_champ, "relation": relation},
            priority="medium"
        )

    def observe_blind_pick(self, game, signatures, baseline, engines):
        """Picked before enemy same-role (drafted blind) and lost."""
        win = game.win
        if win:
            return None
        counter_relation = self._get_signatures_by_type(signatures, "counter_pick_relation")
        if not counter_relation:
            return None
        relation = counter_relation[0].features.get("relation", "")
        if relation != "blind":
            return None
        enemy_champ = game.enemy.champion if game.enemy else "unknown"
        return Observation(
            obs_type="blind_pick", label="blind pick",
            statement=f"Blind pick: drafted before enemy same-role with no matchup info.",
            score=0.45, data={"champion": game.champion, "enemy_champion": enemy_champ, "relation": relation},
            priority="low"
        )

    def observe_death_assessment(self, game, signatures, baseline, engines):
        """Death count in extreme percentile bands."""
        win = game.win
        death_assessment = baseline.get("deaths_per_game", "typical")
        combat = self._get_profile_features(signatures, "combat_profile")
        deaths = combat.get("deaths", game.deaths)
        if death_assessment == "critical" and not win:
            return Observation(
                obs_type="critical_deaths", label="critical death count",
                statement=f"Death count ({deaths}) in bottom 10% of your history. {deaths} deaths — top 10% death rate for you.",
                score=0.65, data={"deaths": deaths, "assessment": death_assessment},
                priority="high"
            )
        if death_assessment in ("excellent", "above_average") and win:
            return Observation(
                obs_type="excellent_survival", label="excellent survival",
                statement=f"Death count ({deaths}) well below your typical — {death_assessment} survival rate.",
                score=0.6, data={"deaths": deaths, "assessment": death_assessment},
                priority="medium"
            )
        return None

    def observe_economy_pattern(self, game, signatures, baseline, engines):
        """CS and gold patterns using personal baselines."""
        cs_10 = game.cs_10
        cs_15 = game.cs_15
        gold_lead_15 = game.gold_lead_15
        win = game.win

        # CS deficit on loss — uses economy engine distribution
        if not win and cs_10 is not None:
            cs_10_dist = engines.economy.distributions.get("cs_at_10") if engines.economy else None
            if cs_10_dist:
                cs_10_band = self._assess_against_distribution(cs_10, cs_10_dist)
                if cs_10_band == "bottom_10":
                    p25 = cs_10_dist.percentiles.get(25, cs_10_dist.mean * 0.75)
                    severity = min(1.0, (p25 - cs_10) / max(p25, 1)) if cs_10 < p25 else 0
                    return Observation(
                        obs_type="cs_deficit_early", label="early CS deficit",
                        statement=f"Early CS deficit: {cs_10} CS at 10 minutes (bottom 10%). laning weakness.",
                        score=0.6 + 0.1 * severity, data={"cs_10": cs_10, "band": cs_10_band},
                        priority="high"
                    )
                elif cs_10_band == "bottom_25":
                    return Observation(
                        obs_type="cs_deficit_early", label="early CS deficit",
                        statement=f"Below-average CS: {cs_10} at 10 minutes (bottom 25%).",
                        score=0.5, data={"cs_10": cs_10, "band": cs_10_band},
                        priority="medium"
                    )

        # Gold deficit at 15
        if not win and gold_lead_15 is not None and gold_lead_15 < -1000:
            return Observation(
                obs_type="gold_deficit", label="gold deficit",
                statement=f"Gold deficit at 15: {gold_lead_15:+,} gold behind at 15 minutes.",
                score=0.65, data={"gold_lead_15": gold_lead_15},
                priority="high"
            )

        # CS efficiency on win — both cs_10 and cs_15 in top quartiles
        if win and cs_10 is not None and cs_15 is not None:
            cs_10_dist = engines.economy.distributions.get("cs_at_10") if engines.economy else None
            if cs_10_dist:
                cs_10_band = self._assess_against_distribution(cs_10, cs_10_dist)
                cs_15_dist = engines.economy.distributions.get("cs_at_15") if engines.economy else None
                cs_15_band = self._assess_against_distribution(cs_15, cs_15_dist) if cs_15_dist else "unknown"
                if cs_10_band in ("top_10", "top_25") and cs_15_band in ("top_10", "top_25"):
                    return Observation(
                        obs_type="cs_efficiency", label="CS efficiency",
                        statement=f"CS efficiency: {cs_10} at 10, {cs_15} at 15 (top quartile). Strong laning.",
                        score=0.55, data={"cs_10": cs_10, "cs_15": cs_15, "cs_10_band": cs_10_band, "cs_15_band": cs_15_band},
                        priority="medium"
                    )

        return None

    def observe_vision_control(self, game, signatures, baseline, engines):
        """Vision score patterns using personal baselines."""
        vision = self._get_profile_features(signatures, "vision_profile")
        vscore = vision.get("vision_score", game.vision)
        wk = vision.get("wards_killed", 0)
        win = game.win

        if not win and vscore > 0:
            vision_dist = engines.vision.distributions.get("vision_score") if engines.vision else None
            if vision_dist:
                vscore_band = self._assess_against_distribution(vscore, vision_dist)
                if vscore_band == "bottom_10":
                    return Observation(
                        obs_type="vision_deficit", label="critical vision deficit",
                        statement=f"Critical vision deficit: {vscore} vision score (bottom 10%). Minimal map control.",
                        score=0.7, data={"vision_score": vscore, "band": vscore_band},
                        priority="high"
                    )
                elif vscore_band == "bottom_25":
                    return Observation(
                        obs_type="low_vision", label="low vision",
                        statement=f"Low vision: {vscore} vision score (bottom 25%). Limited map awareness.",
                        score=0.5, data={"vision_score": vscore, "band": vscore_band},
                        priority="medium"
                    )

        if win and wk > 0:
            wk_dist = engines.vision.distributions.get("wards_killed") if engines.vision else None
            if wk_dist:
                wk_band = self._assess_against_distribution(wk, wk_dist)
                if wk_band in ("top_10", "top_25"):
                    return Observation(
                        obs_type="vision_denial", label="vision denial",
                        statement=f"Vision denial: {wk} enemy wards cleared ({wk_band} quartile). Map control advantage.",
                        score=0.5, data={"wards_killed": wk, "band": wk_band},
                        priority="medium"
                    )

        return None

    def observe_objective_control(self, game, signatures, baseline, engines):
        """Objective patterns — dragons, turrets, barons."""
        win = game.win
        duration = game.duration_min
        my_team = game.my_team
        turret_kills = game.turret_kills

        if not win and duration > 15 and my_team and my_team.dragon_kills == 0:
            return Observation(
                obs_type="no_dragon", label="no dragon control",
                statement=f"No dragons taken in a {duration:.0f}-minute loss. Objective control gap.",
                score=0.6, data={"duration_min": duration, "dragon_kills": 0},
                priority="high"
            )

        if win and my_team and my_team.dragon_kills >= 3:
            dragons = my_team.dragon_kills
            return Observation(
                obs_type="dragon_control", label="dragon control",
                statement=f"Dragon control: {dragons} dragons taken (strong objective play).",
                score=0.5, data={"dragon_kills": dragons},
                priority="medium"
            )

        if not win and duration > 20 and turret_kills == 0:
            return Observation(
                obs_type="no_turret_pressure", label="no turret pressure",
                statement=f"No turret kills in a {duration:.0f}-minute loss. No lane pressure converted.",
                score=0.55, data={"duration_min": duration, "turret_kills": 0},
                priority="medium"
            )

        return None

    def observe_kill_participation(self, game, signatures, baseline, engines):
        """Kill participation patterns using personal baselines."""
        kp_pct = game.kp_pct
        if kp_pct <= 0:
            return None

        win = game.win
        combat = self._get_profile_features(signatures, "combat_profile")
        kills = combat.get("kills", game.kills)
        assists = combat.get("assists", game.assists)

        kp_dist = engines.combat.distributions.get("kill_participation") if engines.combat else None
        if not kp_dist:
            return None

        kp_band = self._assess_against_distribution(kp_pct, kp_dist)

        if not win and kp_band == "bottom_10":
            return Observation(
                obs_type="low_kp", label="low kill participation",
                statement=f"Absent from fights: {kp_pct:.0f}% kill participation (bottom 10%). {kills} kills, {assists} assists.",
                score=0.7, data={"kp_pct": kp_pct, "band": kp_band, "kills": kills, "assists": assists},
                priority="high"
            )

        if win and kp_band == "top_10":
            return Observation(
                obs_type="high_kp", label="carry presence",
                statement=f"Carry presence: {kp_pct:.0f}% kill participation (top 10%). {kills} kills, {assists} assists.",
                score=0.5, data={"kp_pct": kp_pct, "band": kp_band, "kills": kills, "assists": assists},
                priority="medium"
            )

        return None

    OBSERVATION_PRODUCERS = [
        observe_death_cluster,
        observe_death_chain,
        observe_efficient_combat,
        observe_inefficient_combat,
        observe_champion_repetition,
        observe_countered,
        observe_blind_pick,
        observe_death_assessment,
        observe_economy_pattern,
        observe_vision_control,
        observe_objective_control,
        observe_kill_participation,
    ]

    def collect_observations(self, game, signatures, baseline, engines):
        """Run all observation producers, collect and sort by score."""
        observations = []
        for producer in self.OBSERVATION_PRODUCERS:
            obs = producer(self, game, signatures, baseline, engines)
            if obs is not None:
                observations.append(obs)
        return sorted(observations, key=lambda o: o.score, reverse=True)

    # ── Reasoning Query API ──────────────────────────────────────

    def _get_game_cluster(self, match_id: str) -> Optional[ClusterResult]:
        """Look up which behavioral cluster this game belongs to."""
        if not self.similarity_output or match_id not in self.cluster_membership:
            return None
        cluster_id = self.cluster_membership[match_id]
        for cluster in getattr(self.similarity_output, 'clusters', []):
            if cluster.cluster_id == cluster_id:
                return cluster
        return None

    def _get_similar_games(self, fp: GameFingerprint, k: int = 5,
                           prefer_loss: bool = True) -> List[SimilarityResult]:
        """
        Find K most similar games by fingerprint.
        If prefer_loss=True, bias toward games with the same result.
        """
        if not self.similarity_output:
            return []
        all_fps = self.similarity_output.fingerprints
        target_idx = None
        for i, f in enumerate(all_fps):
            if f.match_id == fp.match_id:
                target_idx = i
                break
        if target_idx is None:
            return []
        # Build distance-sorted list
        scored = []
        for i, f in enumerate(all_fps):
            if i == target_idx:
                continue
            dist = self._fp_distance(fp, f)
            scored.append((dist, f))
        scored.sort(key=lambda x: x[0])
        results = []
        for dist, f in scored[:k * 2]:
            results.append(SimilarityResult(
                match_id=f.match_id,
                champion=f.champion,
                win=f.win,
                distance=round(dist, 4),
                fingerprint=f
            ))
        # Filter by prefer_loss if we have enough results
        if prefer_loss:
            filtered = [r for r in results if r.win == fp.win]
            if len(filtered) >= k:
                return filtered[:k]
        return results[:k]

    def _fp_distance(self, a: GameFingerprint, b: GameFingerprint) -> float:
        """Euclidean distance in 5-D fingerprint space."""
        import math
        return math.sqrt(
            (a.aggression - b.aggression) ** 2 +
            (a.efficiency - b.efficiency) ** 2 +
            (a.objective_race - b.objective_race) ** 2 +
            (a.collapse - b.collapse) ** 2 +
            (a.vision - b.vision) ** 2
        )

    def _get_counterfactual_insight(self, game: Game) -> str:
        """
        Build a counterfactual insight string from signal deltas.
        Uses the same signals as discover_signals() to tell the story
        of what happened vs what could have been.
        """
        if not self.similarity_output:
            return ""
        engine = SimilarityEngine()
        engine.games = self.similarity_output.fingerprints
        # Build minimal engine state for matched comparison
        signals = []
        signal_defs = [
            ("8+ deaths", lambda g: g.deaths >= 8),
            ("5+ deaths", lambda g: g.deaths >= 5),
            ("low vision", lambda g: g.vision < 30),
            ("gold deficit early", lambda g: (g.gold_lead_15 or 0) <= -500),
        ]
        best_insight = ""
        best_abs_delta = 0.0
        for name, fn in signal_defs:
            if not fn(game):
                continue
            # Run matched comparison for this signal
            result = self._run_matched_comparison(fn)
            if result and abs(result.delta) > best_abs_delta and abs(result.delta) > 0.08:
                best_abs_delta = abs(result.delta)
                direction = "increased" if result.delta < 0 else "decreased"
                best_insight = (
                    f"Games without {name} won {abs(result.delta):.0%} more often "
                    f"({result.win_rate_matched_comparison:.0%} vs {result.win_rate_with_signal:.0%})."
                )
        return best_insight

    def _run_matched_comparison(self, signal_fn) -> Optional[object]:
        """
        Run matched comparison using the fingerprint corpus.
        Returns a minimal result object with delta, win_rate_with_signal, win_rate_matched.
        """
        if not self.similarity_output:
            return None
        games = self.similarity_output.games
        if not games:
            return None
        fps = self.similarity_output.fingerprints
        games_with = []
        games_without = []
        for i, g in enumerate(games):
            if signal_fn(g):
                games_with.append(i)
            else:
                games_without.append(i)
        if len(games_with) < 5 or len(games_without) < 5:
            return None
        # Build matched set
        matched_with = set()
        for idx in games_with:
            target_fp = fps[idx]
            scored = []
            for j in games_without:
                if j == idx:
                    continue
                scored.append((self._fp_distance(target_fp, fps[j]), j))
            scored.sort(key=lambda x: x[0])
            for _, j in scored[:30]:
                matched_with.add(j)
        if not matched_with:
            return None
        wins_with = sum(1 for i in games_with if games[i].win)
        wins_matched = sum(1 for i in matched_with if games[i].win)
        wr_with = wins_with / len(games_with)
        wr_matched = wins_matched / len(matched_with)
        delta = wr_with - wr_matched
        class _Result:
            def __init__(self, delta, wr_with, wr_matched):
                self.delta = delta
                self.win_rate_with_signal = wr_with
                self.win_rate_matched_comparison = wr_matched
        return _Result(delta, wr_with, wr_matched)

    def _get_mechanism(self, game: Game, cluster: Optional[ClusterResult]) -> str:
        """
        Name the specific mechanism of the loss or win.
        Uses cluster centroid delta — compares the game's fingerprint
        to the cluster centroid directly. No hardcoded thresholds.
        """
        if not cluster or not self.similarity_output:
            return ""
        if cluster.total_games < 10:
            return ""  # not enough data for reliable centroid comparison

        centroid = cluster.mean_fingerprint
        match_id = game.match_id

        # Find this game's fingerprint
        game_fp = None
        for fp in self.similarity_output.fingerprints:
            if fp.match_id == match_id:
                game_fp = fp
                break
        if not game_fp:
            return ""

        win = game.win
        deaths = game.deaths
        gold_lead_15 = game.gold_lead_15 or 0
        lks = game.largest_killing_spree

        # Compute fingerprint deltas: (dimension, game_value, centroid_value, delta)
        fp_deltas = [
            ("efficiency", game_fp.efficiency, centroid.efficiency),
            ("aggression", game_fp.aggression, centroid.aggression),
            ("vision", game_fp.vision, centroid.vision),
            ("collapse", game_fp.collapse, centroid.collapse),
            ("objective_race", game_fp.objective_race, centroid.objective_race),
        ]

        # Non-fingerprint deltas
        non_fp_deltas = [
            ("deaths", deaths, None),   # None = no centroid for raw field
            ("gold_lead_15", gold_lead_15, None),
            ("largest_killing_spree", lks, None),
        ]

        parts = []
        if cluster.win_rate <= 0.35:
            # Loss: report dimensions where this game is BELOW the cluster centroid
            for dim, game_val, centroid_val in fp_deltas:
                delta = game_val - centroid_val
                if delta < -0.05:  # game is meaningfully below centroid
                    if dim == "efficiency":
                        parts.append(f"eff {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "aggression":
                        parts.append(f"agg {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "vision":
                        parts.append(f"vis {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "collapse":
                        parts.append(f"collapse {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "objective_race":
                        parts.append(f"obj {game_val:.2f} vs {centroid_val:.2f} cluster")
            # Non-fingerprint: deaths and gold deficit
            if deaths >= centroid.efficiency * 10 + 4:  # rough heuristic from cluster
                parts.append(f"{deaths} deaths")
            if gold_lead_15 < -500:
                parts.append(f"gold deficit {gold_lead_15}")
            if lks <= 2:
                parts.append("no snowball")
            if parts:
                return " + ".join(parts) + " — cluster loss mechanism"
            return f"cluster losing type ({cluster.win_rate:.0%} WR)"

        elif cluster.win_rate >= 0.60:
            # Win: report dimensions where this game is ABOVE the cluster centroid
            for dim, game_val, centroid_val in fp_deltas:
                delta = game_val - centroid_val
                if delta > 0.05:  # game is meaningfully above centroid
                    if dim == "efficiency":
                        parts.append(f"eff {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "aggression":
                        parts.append(f"agg {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "vision":
                        parts.append(f"vis {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "collapse":
                        parts.append(f"collapse {game_val:.2f} vs {centroid_val:.2f} cluster")
                    elif dim == "objective_race":
                        parts.append(f"obj {game_val:.2f} vs {centroid_val:.2f} cluster")
            if deaths <= 4:
                parts.append("controlled deaths")
            if gold_lead_15 > 500:
                parts.append(f"gold lead {gold_lead_15}")
            if parts:
                return " + ".join(parts) + " — cluster win mechanism"
            return f"cluster winning type ({cluster.win_rate:.0%} WR)"

        return ""

    def _get_pattern_insight(self, game: Game) -> str:
        """
        Check which co-occurring patterns fired in this game.
        Uses the patterns discovered by discover_patterns() stored in
        similarity_output.patterns. Returns a string describing which
        (if any) superadditive patterns fired.
        """
        if not self.similarity_output or not self.similarity_output.patterns:
            return ""
        patterns = self.similarity_output.patterns
        if not patterns:
            return ""

        match_id = game.match_id
        if not match_id:
            return ""

        # Get the signal queries to evaluate which signals fired in this game
        from verdict_similarity import _build_signal_queries
        queries = _build_signal_queries()
        signal_map = {q.name: q for q in queries}

        # Determine which signals fired in this game
        signals_fired = set()
        for q in queries:
            try:
                if q.signal_fn(game):
                    signals_fired.add(q.name)
            except Exception:
                pass

        if not signals_fired:
            return ""

        # Check top patterns (by co-occurrence count) for matches
        # Superadditive patterns get priority
        superadditive_fired = []
        non_super_fired = []

        for p in patterns:
            if p.signal_1 in signals_fired and p.signal_2 in signals_fired:
                if p.superadditive:
                    superadditive_fired.append(p)
                elif p.pair_delta < -0.08:  # reliably harmful conjunction
                    non_super_fired.append(p)

        if not superadditive_fired and not non_super_fired:
            return ""

        parts = []
        if superadditive_fired:
            for p in superadditive_fired[:1]:  # show top superadditive only
                delta_pct = abs(p.pair_delta) * 100
                parts.append(
                    f"superadditive: {p.signal_1} + {p.signal_2} "
                    f"cost {delta_pct:.0f}% WR (conf={p.pair_confidence:.0%})"
                )
        if non_super_fired:
            for p in non_super_fired[:1]:
                delta_pct = abs(p.pair_delta) * 100
                parts.append(
                    f"conjunction: {p.signal_1} + {p.signal_2} "
                    f"({p.co_occurrence_count} losing games, delta={delta_pct:.0f}%)"
                )

        return " | ".join(parts) if parts else ""

    def analyze_single_game(self, game: Game, engines: MultiEngineOutput) -> Verdict:
        """
        Fractal analysis: analyze one game through the lens of ALL games.
        Now with multi-engine correlation (temporal + combat).
        """
        verdict_id = f"verdict_{game.match_id}"
        timestamp = datetime.now()

        # Get signatures from all available engines
        all_signatures = []
        for engine_attr in ["death", "economy", "combat", "durability", "vision", "objective", "draft"]:
            engine_output = getattr(engines, engine_attr)
            if engine_output:
                all_signatures += self._get_engine_signatures(engine_output, game.match_id)

        # Assess game against personal baselines
        baseline_assessments = self.player_model.assess_game(game)

        # ── Phase 1: Reasoning Layer ────────────────────────────
        # Look up cluster membership, similar games, mechanism
        match_id = game.match_id
        cluster = self._get_game_cluster(match_id)
        cluster_label = cluster.behavioral_label if cluster else ""
        mechanism = self._get_mechanism(game, cluster)
        counterfactual_insight = self._get_counterfactual_insight(game)
        pattern_insight = self._get_pattern_insight(game)
        similar_games = []
        if self.similarity_output:
            for fp in self.similarity_output.fingerprints:
                if fp.match_id == match_id:
                    similar = self._get_similar_games(fp, k=3, prefer_loss=True)
                    similar_games = [r.match_id for r in similar]
                    break

        # Build the verdict statement with compositional observations
        observations = self.collect_observations(game, all_signatures, baseline_assessments, engines)
        if observations:
            statement = observations[0].statement
            confidence = observations[0].score
        else:
            result = "win" if game.win else "loss"
            champion = game.champion
            statement = f"{champion} {result}: No dominant structural patterns detected."
            confidence = 0.5

        # Build supporting evidence
        evidence = self._build_evidence_multi(game, all_signatures, baseline_assessments, engines)

        # Derive lessons with combat context
        lessons = self._derive_lessons_multi(game, all_signatures, baseline_assessments, engines)

        # Find matched patterns from player model
        matched_patterns = self._match_player_patterns(game, baseline_assessments)

        # Identify divergences
        divergences = self._identify_divergences_multi(game, baseline_assessments, engines)

        return Verdict(
            verdict_id=verdict_id,
            timestamp=timestamp,
            verdict_type="fractal_analysis",
            statement=statement,
            confidence=confidence,
            summary=self._build_summary_multi(game, engines),
            explanation=self._build_explanation_multi(game, all_signatures, matched_patterns, engines),
            primary_evidence=evidence,
            lessons=lessons,
            matched_patterns=matched_patterns,
            divergences=divergences,
            similar_games=similar_games,
            cluster_label=cluster_label,
            counterfactual_insight=counterfactual_insight,
            mechanism=mechanism,
            pattern_insight=pattern_insight,
            drill_down_available=True,
            drill_down_prompt="Run 'face game <id> --deep' for full node analysis",
            observations=observations
        )

    def _get_engine_signatures(self, engine_output: EngineOutput, match_id: str) -> List[EngineSignature]:
        """Get signatures for a specific game by matching signature ID to match_id."""
        return [s for s in engine_output.signatures if match_id in s.signature_id]

    # ── ENGINE DATA HELPERS ──

    def _get_profile_features(self, signatures: List[EngineSignature], signature_type: str) -> Dict:
        """Extract features dict from the first matching profile signature."""
        for s in signatures:
            if s.signature_type == signature_type:
                return s.features
        return {}

    def _get_signatures_by_type(self, signatures: List[EngineSignature], signature_type: str) -> List[EngineSignature]:
        """Get all signatures of a given type."""
        return [s for s in signatures if s.signature_type == signature_type]

    def _assess_against_distribution(self, value: float, distribution) -> str:
        """Assess a value against an engine distribution. Returns percentile band."""
        if not distribution or value is None:
            return "unknown"
        p10 = distribution.percentiles.get(10, distribution.mean * 0.5)
        p25 = distribution.percentiles.get(25, distribution.mean * 0.75)
        p75 = distribution.percentiles.get(75, distribution.mean * 1.25)
        p90 = distribution.percentiles.get(90, distribution.mean * 1.5)
        if value <= p10:
            return "bottom_10"
        elif value <= p25:
            return "bottom_25"
        elif value >= p90:
            return "top_10"
        elif value >= p75:
            return "top_25"
        return "middle"

    def _match_player_patterns(self, game: Game, assessments: Dict[str, str]) -> List[str]:
        """Match game to player model patterns."""
        matched = []

        # Check pattern matches
        deaths = game.deaths
        baseline = self.player_model.get_baseline("deaths_per_game")
        if baseline and deaths >= baseline.p90:
            matched.append("high_death_game")

        cs_10 = game.cs_10
        early_deaths = game.early_deaths
        cs_baseline = self.player_model.get_baseline("cs_at_10")
        if early_deaths > 0 and cs_10 and cs_baseline and cs_10 >= cs_baseline.p75:
            matched.append("cs_recovery_after_early_death")

        gold_lead = game.gold_lead_15
        if gold_lead and gold_lead > 1000:
            matched.append("strong_laning_phase")

        return matched

    # ─────────────────────────────────────────────
    # MULTI-ENGINE METHODS
    # ─────────────────────────────────────────────

    def _build_evidence_multi(self, game: Game, signatures: List[EngineSignature],
                              assessments: Dict[str, str], engines: MultiEngineOutput) -> List[Evidence]:
        """Build evidence from engine outputs and distributions."""
        evidence = []
        win = game.win
        duration = game.duration_min

        combat = self._get_profile_features(signatures, "combat_profile")
        durability = self._get_profile_features(signatures, "durability_profile")
        vision = self._get_profile_features(signatures, "vision_profile")

        # ── Death evidence ──
        if engines.death:
            death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
            death_chains = self._get_signatures_by_type(signatures, "death_chain")
            if death_clusters:
                cluster = death_clusters[0]
                evidence.append(Evidence(
                    evidence_type="pattern",
                    description="Death cluster detected",
                    value=f"{cluster.features.get('cluster_size', 0)} deaths in {cluster.features.get('gap_minutes', 0):.0f} min",
                    context=f"Temporal concentration of death events"
                ))
            if death_chains:
                chain = death_chains[0]
                evidence.append(Evidence(
                    evidence_type="pattern",
                    description="Death chain detected",
                    value=f"{chain.features.get('chain_length', 0)} deaths with accelerating frequency",
                    context="Death rate increased over time"
                ))

            death_dist = engines.death.distributions.get("deaths_per_game")
            if death_dist:
                deaths = combat.get("deaths", game.deaths)
                band = self._assess_against_distribution(deaths, death_dist)
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Death count",
                    value=str(deaths),
                    context=f"Your distribution: {band} (mean: {death_dist.mean:.1f})"
                ))

        # ── Combat evidence ──
        if engines.combat and combat:
            dpm = combat.get("dpm", 0)
            kp = combat.get("kp_pct", 0)
            deaths = combat.get("deaths", 0)
            damage = combat.get("damage", 0)

            dpm_dist = engines.combat.distributions.get("damage_per_min")
            if dpm and dpm_dist:
                band = self._assess_against_distribution(dpm, dpm_dist)
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Damage per minute",
                    value=f"{dpm:.0f}",
                    context=f"Your distribution: {band} (mean: {dpm_dist.mean:.0f})"
                ))

            kp_dist = engines.combat.distributions.get("kill_participation")
            if kp and kp_dist:
                band = self._assess_against_distribution(kp, kp_dist)
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Kill participation",
                    value=f"{kp:.0f}%",
                    context=f"Your distribution: {band} (mean: {kp_dist.mean:.0f}%)"
                ))

            evidence.append(Evidence(
                evidence_type="stat",
                description="Combat profile",
                value=f"{damage//1000}k dmg, {deaths} deaths, {kp:.0f}% KP",
                context="Cross-field combat structural snapshot"
            ))

        # ── Durability evidence ──
        if engines.durability and durability:
            heal = durability.get("total_heal", 0)
            mit = durability.get("damage_mitigated", 0)
            cc = durability.get("cc_time", 0)
            shield = durability.get("damage_shielded", 0)

            if heal > 0:
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Total healing",
                    value=f"{heal//1000}k",
                    context="Self-sustain metric"
                ))
            if mit > 0:
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Damage mitigated",
                    value=f"{mit//1000}k",
                    context="Damage reduction metric"
                ))
            if cc > 0:
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="CC time dealt",
                    value=f"{cc:.0f}s",
                    context="Crowd control output"
                ))
            if shield > 0:
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Damage shielded on teammates",
                    value=f"{shield//1000}k",
                    context="Support protection metric"
                ))

        # ── Vision evidence ──
        if engines.vision and vision:
            vscore = vision.get("vision_score", 0)
            vpm = vision.get("vision_per_min", 0)
            wk = vision.get("wards_killed", 0)
            wp = vision.get("wards_placed", 0)
            cw = vision.get("control_wards", 0)

            evidence.append(Evidence(
                evidence_type="stat",
                description="Vision profile",
                value=f"Score {vscore} ({vpm}/min), {wp} placed, {wk} killed, {cw} control",
                context="Map control structural snapshot"
            ))

        # ── Draft evidence ──
        if engines.draft:
            pick_pos = self._get_signatures_by_type(signatures, "pick_position")
            side = self._get_signatures_by_type(signatures, "side_assignment")
            counter = self._get_signatures_by_type(signatures, "counter_pick_relation")

            if pick_pos:
                po = pick_pos[0].features.get("pick_order", 0)
                pos = pick_pos[0].features.get("position_label", "unknown")
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Draft position",
                    value=f"Pick {po} ({pos})",
                    context="Draft structural position"
                ))
            if side:
                s = side[0].features.get("side", "unknown")
                evidence.append(Evidence(
                    evidence_type="stat",
                    description="Draft side",
                    value=s.capitalize(),
                    context="Map side assignment"
                ))
            if counter:
                rel = counter[0].features.get("relation", "unknown")
                evidence.append(Evidence(
                    evidence_type="pattern",
                    description="Counter-pick relation",
                    value=rel.capitalize(),
                    context="Pick order relative to enemy same-role"
                ))

        # ── General pattern evidence ──
        for sig in signatures[:3]:
            if sig.signature_type not in ["combat_profile", "durability_profile", "vision_profile"]:
                evidence.append(Evidence(
                    evidence_type="pattern",
                    description=sig.signature_type.replace("_", " ").title(),
                    value=f"{sig.start_min:.0f}-{sig.end_min:.0f} min",
                    context=f"Confidence: {sig.confidence:.0%}"
                ))

        return evidence

    def _derive_lessons_multi(self, game: Game, signatures: List[EngineSignature],
                             assessments: Dict[str, str], engines: MultiEngineOutput) -> List[Lesson]:
        """Derive lessons from structural patterns in engine outputs."""
        lessons = []
        win = game.win

        combat = self._get_profile_features(signatures, "combat_profile")
        durability = self._get_profile_features(signatures, "durability_profile")
        vision = self._get_profile_features(signatures, "vision_profile")

        death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
        death_chains = self._get_signatures_by_type(signatures, "death_chain")
        death_phase_conc = self._get_signatures_by_type(signatures, "death_phase_concentration")

        champ_repetition = self._get_signatures_by_type(signatures, "champion_repetition")
        counter_relation = self._get_signatures_by_type(signatures, "counter_pick_relation")
        pick_position = self._get_signatures_by_type(signatures, "pick_position")

        deaths = combat.get("deaths", game.deaths)
        damage = combat.get("damage", game.damage)
        dpm = combat.get("dpm", game.damage_per_min)
        kp = combat.get("kp_pct", game.kp_pct)

        # ── Death structural lessons ──
        if death_chains:
            chain = death_chains[0]
            length = chain.features.get("chain_length", 3)
            lessons.append(Lesson(
                lesson_type="immediate",
                text=f"Death chain: {length} deaths with accelerating frequency. Gap between deaths shrank each time.",
                priority="high"
            ))
        elif death_clusters:
            cluster = death_clusters[0]
            size = cluster.features.get("cluster_size", 2)
            gap = cluster.features.get("gap_minutes", 0)
            lessons.append(Lesson(
                lesson_type="immediate",
                text=f"Death cluster: {size} deaths within {gap:.0f} minutes. After the first death, play defensively for the next {gap:.0f} minutes.",
                priority="high"
            ))

        if death_phase_conc:
            phase = death_phase_conc[0].features.get("concentrated_phase", "unknown")
            lessons.append(Lesson(
                lesson_type="practice",
                text=f"Deaths concentrated in {phase} phase. {deaths} deaths in {phase} game — review those decisions.",
                priority="medium"
            ))

        # ── Combat/durability lessons — distribution-band-driven ──
        if engines.combat and engines.death and engines.durability:
            death_dist = engines.death.distributions.get("deaths_per_game")
            damage_dist = engines.combat.distributions.get("total_damage")
            heal_dist = engines.durability.distributions.get("total_heal")
            mit_dist = engines.durability.distributions.get("damage_mitigated")
            cc_dist = engines.durability.distributions.get("cc_time")
            wk_dist = engines.vision.distributions.get("wards_killed") if engines.vision else None

            death_band = self._assess_against_distribution(deaths, death_dist) if death_dist else "unknown"
            damage_band = self._assess_against_distribution(damage, damage_dist) if damage_dist else "unknown"

            # High deaths + low damage + loss
            if not win and death_band in ("top_25", "top_10") and damage_band in ("bottom_25", "bottom_10"):
                lessons.append(Lesson(
                    lesson_type="immediate",
                    text=f"High deaths ({deaths}, {death_band} quartile) with low damage ({damage//1000}k, {damage_band} quartile). {damage//max(deaths,1)//1000:.1f}k damage per death — need more impact or fewer deaths.",
                    priority="critical"
                ))

            # High DPM + low deaths + win
            dpm_dist = engines.combat.distributions.get("damage_per_min")
            dpm_band = self._assess_against_distribution(dpm, dpm_dist) if dpm_dist else "unknown"
            if win and dpm_band in ("top_25", "top_10") and death_band in ("bottom_25", "bottom_10"):
                lessons.append(Lesson(
                    lesson_type="mindset",
                    text=f"Efficient combat: {dpm:.0f} DPM ({dpm_band} quartile) with {deaths} deaths ({death_band} quartile). {dpm:.0f} DPM per death — peak efficiency.",
                    priority="high"
                ))

            # High healing + win
            heal_band = self._assess_against_distribution(durability.get("total_heal", 0), heal_dist) if heal_dist else "unknown"
            if win and heal_band in ("top_25", "top_10"):
                heal_val = durability.get("total_heal", 0)
                lessons.append(Lesson(
                    lesson_type="mindset",
                    text=f"High self-sustain: {heal_val//1000}k healing ({heal_band} quartile). Sustained {heal_val//max(deaths,1)//1000:.0f}k healing per death.",
                    priority="medium"
                ))

            # High mitigation + low damage + loss
            mit_band = self._assess_against_distribution(durability.get("damage_mitigated", 0), mit_dist) if mit_dist else "unknown"
            if not win and mit_band in ("top_25", "top_10") and damage_band in ("bottom_25", "bottom_10"):
                mit_val = durability.get("damage_mitigated", 0)
                lessons.append(Lesson(
                    lesson_type="practice",
                    text=f"High mitigation ({mit_val//1000}k, {mit_band} quartile) but low damage ({damage//1000}k, {damage_band} quartile). Soaking damage without converting to kills.",
                    priority="high"
                ))

            # High CC + win
            cc_band = self._assess_against_distribution(durability.get("cc_time", 0), cc_dist) if cc_dist else "unknown"
            if win and cc_band in ("top_25", "top_10"):
                cc_val = durability.get("cc_time", 0)
                lessons.append(Lesson(
                    lesson_type="practice",
                    text=f"{cc_val:.0f}s CC ({cc_band} quartile) enabled {kp:.0f}% kill participation. CC-to-kill conversion.",
                    priority="medium"
                ))

            # Vision denial + win
            wk_val = vision.get("wards_killed", 0)
            if wk_dist and wk_val > 0:
                wk_band = self._assess_against_distribution(wk_val, wk_dist)
                if win and wk_band in ("top_25", "top_10"):
                    lessons.append(Lesson(
                        lesson_type="practice",
                        text=f"Cleared {wk_val} enemy wards ({wk_band} quartile). Vision control denied {wk_val} ward positions.",
                        priority="medium"
                    ))

        # ── Draft structural lessons ──
        if engines.draft:
            # Derive WR distribution for champion repetition across ALL games
            if champ_repetition:
                champ = champ_repetition[0].features.get("champion", game.champion)
                games_on = champ_repetition[0].features.get("games_on_champ", 3)
                wr = champ_repetition[0].features.get("champ_wr", 0.5)
                # engines.draft.source_games is List[str] (match_ids), not game dicts.
                # The champion_repetition signature already captures all-champion performance data.
                # games_on >= 3 means the signature exists. wr is the win rate across those games.
                # WR thresholds are personal: compare champ WR to player's overall WR.
                if games_on >= 3:
                    # Compute player's overall WR from similarity_output games
                    overall_baseline = 0.50  # fallback
                    if self.similarity_output and self.similarity_output.games:
                        total = len(self.similarity_output.games)
                        if total >= 10:
                            overall_baseline = sum(
                                1 for g in self.similarity_output.games if g.win
                            ) / total
                    if wr > overall_baseline + 0.12:
                        delta = wr - overall_baseline
                        lessons.append(Lesson(
                            lesson_type="draft",
                            text=f"Comfort on {champ}: {games_on} games at {wr:.0%} WR vs {overall_baseline:.0%} overall (+{delta:.0%}). Strong pick — {delta:.0%} above your baseline.",
                            priority="medium"
                        ))
                    elif wr < overall_baseline - 0.10:
                        delta = overall_baseline - wr
                        lessons.append(Lesson(
                            lesson_type="draft",
                            text=f"{champ}: {games_on} games at {wr:.0%} WR vs {overall_baseline:.0%} overall ({delta:.0%} below baseline). Underperforming by {delta:.0%}.",
                            priority="medium"
                        ))

            if counter_relation and win:
                lessons.append(Lesson(
                    lesson_type="draft",
                    text="Counter-pick position in draft. Picked after enemy same-role — had matchup info but didn't convert.",
                    priority="low"
                ))

            if pick_position:
                pos = pick_position[0].features.get("position_label", "unknown")
                if pos == "early":
                    lessons.append(Lesson(
                        lesson_type="draft",
                        text="Early pick: drafted blind — no matchup info available at pick time.",
                        priority="low"
                    ))
                elif pos == "late":
                    lessons.append(Lesson(
                        lesson_type="draft",
                        text="Late pick: drafted with matchup info — could counter-pick or dodge bad matchups.",
                        priority="low"
                    ))

        # ── General structural lessons ──
        if deaths <= 3 and win:
            lessons.append(Lesson(
                lesson_type="mindset",
                text=f"Low death count ({deaths}) with win. {deaths} deaths — controlled survival pattern.",
                priority="medium"
            ))

        return lessons

    def _build_summary_multi(self, game: Game, engines: MultiEngineOutput) -> str:
        """Build summary from structural patterns in engine outputs."""
        parts = []
        win = game.win
        champion = game.champion

        # Collect signatures for this game
        signatures = []
        for engine_attr in ["death", "economy", "combat", "durability", "vision", "objective", "draft"]:
            engine_output = getattr(engines, engine_attr)
            if engine_output:
                signatures += self._get_engine_signatures(engine_output, game.match_id)

        combat = self._get_profile_features(signatures, "combat_profile")
        durability = self._get_profile_features(signatures, "durability_profile")
        vision = self._get_profile_features(signatures, "vision_profile")

        death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
        death_chains = self._get_signatures_by_type(signatures, "death_chain")

        # Death structural summary
        # Use distribution bands, not magic numbers
        deaths = combat.get("deaths", game.deaths)
        death_dist = engines.death.distributions.get("deaths_per_game") if engines.death else None
        death_band = self._assess_against_distribution(deaths, death_dist) if death_dist else "unknown"
        if death_chains:
            chain = death_chains[0]
            parts.append(f"Death chain: {chain.features.get('chain_length', 0)} deaths with accelerating frequency.")
        elif death_clusters:
            cluster = death_clusters[0]
            parts.append(f"Death cluster: {cluster.features.get('cluster_size', 0)} deaths within {cluster.features.get('gap_minutes', 0):.0f} minutes.")
        elif death_band in ("top_10", "top_25"):
            parts.append(f"High death count: {deaths} ({death_band.replace('_', ' ')}).")
        elif death_band in ("bottom_10", "bottom_25"):
            parts.append(f"Low death count: {deaths} ({death_band.replace('_', ' ')}).")

        # Combat structural summary
        if engines.combat and combat:
            dpm = combat.get("dpm", 0)
            kp = combat.get("kp_pct", 0)
            dpm_dist = engines.combat.distributions.get("damage_per_min")
            if dpm and dpm_dist:
                band = self._assess_against_distribution(dpm, dpm_dist)
                if band in ("top_10", "top_25"):
                    parts.append(f"High DPM ({dpm:.0f}) — {band.replace('_', ' ')} of your history.")
                elif band in ("bottom_10", "bottom_25"):
                    parts.append(f"Low DPM ({dpm:.0f}) — {band.replace('_', ' ')} of your history.")

        # Economy structural summary
        if engines.economy:
            cs_10 = game.cs_10
            cs_15 = game.cs_15
            gold_lead = game.gold_lead_15
            if cs_10 is not None and cs_15 is not None:
                delta = cs_15 - cs_10
                slope = delta / 5
                direction = "accelerating" if slope > 2 else ("decelerating" if slope < -2 else "flat")
                parts.append(f"CS slope 10→15: {direction} ({cs_10} → {cs_15}).")
            if gold_lead is not None:
                parts.append(f"Gold at 15: {gold_lead:+,}.")

        # Durability structural summary
        if engines.durability and durability:
            heal = durability.get("total_heal", 0)
            mit = durability.get("damage_mitigated", 0)
            cc = durability.get("cc_time", 0)
            heal_dist = engines.durability.distributions.get("total_heal")
            mit_dist = engines.durability.distributions.get("damage_mitigated")
            cc_dist = engines.durability.distributions.get("cc_time")
            heal_band = self._assess_against_distribution(heal, heal_dist) if heal_dist else "unknown"
            mit_band = self._assess_against_distribution(mit, mit_dist) if mit_dist else "unknown"
            cc_band = self._assess_against_distribution(cc, cc_dist) if cc_dist else "unknown"
            if heal_band in ("top_10", "top_25") and heal > 0:
                parts.append(f"High healing: {heal//1000}k ({heal_band}).")
            if mit_band in ("top_10", "top_25") and mit > 0:
                parts.append(f"High mitigation: {mit//1000}k ({mit_band}).")
            if cc_band in ("top_10", "top_25") and cc > 0:
                parts.append(f"High CC output: {cc:.0f}s ({cc_band}).")

        # Vision structural summary
        if engines.vision and vision:
            vscore = vision.get("vision_score", 0)
            wk = vision.get("wards_killed", 0)
            wk_dist = engines.vision.distributions.get("wards_killed") if engines.vision else None
            wk_band = self._assess_against_distribution(wk, wk_dist) if wk_dist else "unknown"
            if wk_band in ("top_10", "top_25") and wk > 0:
                parts.append(f"Vision activity: {wk} enemy wards cleared ({wk_band}).")
            elif vscore > 0:
                parts.append(f"Vision score: {vscore}.")

        # Draft structural summary
        if engines.draft:
            pick_pos = self._get_signatures_by_type(signatures, "pick_position")
            side = self._get_signatures_by_type(signatures, "side_assignment")
            if pick_pos:
                po = pick_pos[0].features.get("pick_order", 0)
                pos = pick_pos[0].features.get("position_label", "unknown")
                parts.append(f"Draft: {pos} pick ({po}).")
            if side:
                s = side[0].features.get("side", "unknown")
                parts.append(f"Side: {s.capitalize()}.")

        return " ".join(parts) if parts else f"{'Win' if win else 'Loss'} on {champion}."


    def _build_explanation_multi(self, game: Game, signatures: List[EngineSignature],
                                matched_patterns: List[str], engines: MultiEngineOutput) -> str:
        """Build explanation from structural patterns and engine distributions."""
        parts = []

        # Explain matched patterns
        if matched_patterns:
            parts.append("This game matched your known patterns:")
            for pattern_id in matched_patterns[:3]:
                pattern = self.player_model.get_pattern(pattern_id)
                if pattern:
                    parts.append(f"  - {pattern_id}: {pattern.occurrence_count}x recorded, {pattern.win_rate():.0%} win rate")

        # Explain structural signatures
        sig_types = {}
        for sig in signatures:
            sig_types[sig.signature_type] = sig_types.get(sig.signature_type, 0) + 1
        if sig_types:
            parts.append(f"\nStructural signatures: {', '.join(f'{k} ({v})' for k, v in sig_types.items())}")

        # Engine distribution context
        if engines.combat:
            combat = self._get_profile_features(signatures, "combat_profile")
            dpm = combat.get("dpm", 0)
            kp = combat.get("kp_pct", 0)
            dpm_dist = engines.combat.distributions.get("damage_per_min")
            kp_dist = engines.combat.distributions.get("kill_participation")
            if dpm and dpm_dist and kp and kp_dist:
                dpm_band = self._assess_against_distribution(dpm, dpm_dist)
                parts.append(f"\nCombat: {dpm:.0f} DPM ({dpm_band.replace('_', ' ')}, avg: {dpm_dist.mean:.0f}), {kp:.0f}% KP (avg: {kp_dist.mean:.0f})")

        if engines.death:
            death_dist = engines.death.distributions.get("deaths_per_game")
            deaths = game.deaths
            if death_dist:
                band = self._assess_against_distribution(deaths, death_dist)
                parts.append(f"Deaths: {deaths} ({band.replace('_', ' ')}, avg: {death_dist.mean:.1f})")

        if engines.economy:
            cs_dist = engines.economy.distributions.get("cs_at_10")
            cs_10 = game.cs_10
            if cs_10 and cs_dist:
                band = self._assess_against_distribution(cs_10, cs_dist)
                parts.append(f"CS@10: {cs_10} ({band.replace('_', ' ')}, avg: {cs_dist.mean:.0f})")

        if engines.vision:
            vision = self._get_profile_features(signatures, "vision_profile")
            vscore = vision.get("vision_score", 0)
            if vscore > 0:
                parts.append(f"Vision: score {vscore}")

        if engines.durability:
            durability = self._get_profile_features(signatures, "durability_profile")
            heal = durability.get("total_heal", 0)
            mit = durability.get("damage_mitigated", 0)
            cc = durability.get("cc_time", 0)
            if heal or mit or cc:
                support_parts = []
                if heal:
                    support_parts.append(f"heal {heal//1000}k")
                if mit:
                    support_parts.append(f"mitigated {mit//1000}k")
                if cc:
                    support_parts.append(f"CC {cc:.0f}s")
                parts.append(f"Durability: {', '.join(support_parts)}")

        return "\n".join(parts) if parts else "No significant structural patterns detected in this game."

    def _identify_divergences_multi(self, game: Game, assessments: Dict[str, str],
                                   engines: MultiEngineOutput) -> List[str]:
        """Identify divergences from structural patterns and distributions."""
        divergences = []
        win = game.win

        # Collect signatures
        signatures = []
        for engine_attr in ["death", "economy", "combat", "durability", "vision", "objective", "draft"]:
            engine_output = getattr(engines, engine_attr)
            if engine_output:
                signatures += self._get_engine_signatures(engine_output, game.match_id)

        combat = self._get_profile_features(signatures, "combat_profile")
        durability = self._get_profile_features(signatures, "durability_profile")

        deaths = combat.get("deaths", game.deaths)
        damage = combat.get("damage", game.damage)
        dpm = combat.get("dpm", game.damage_per_min)

        # Win with high deaths (unusual) — death in top 25%, win
        death_dist = engines.death.distributions.get("deaths_per_game") if engines.death else None
        death_band = self._assess_against_distribution(deaths, death_dist) if death_dist else "unknown"
        if win and death_band in ("top_25", "top_10"):
            if engines.combat and dpm > 0:
                dpm_dist = engines.combat.distributions.get("damage_per_min")
                dpm_band = self._assess_against_distribution(dpm, dpm_dist) if dpm_dist else "unknown"
                if dpm_band in ("top_25", "top_10"):
                    divergences.append(f"Won despite high deaths — {dpm:.0f} DPM offset {deaths} deaths")
                else:
                    divergences.append(f"Won despite high deaths ({deaths}) — team carried")
            else:
                divergences.append(f"Won despite high deaths ({deaths})")

        # Loss with low deaths but low damage (invisible impact)
        if not win and death_band in ("bottom_25", "bottom_10"):
            if engines.combat and dpm > 0:
                dpm_dist = engines.combat.distributions.get("damage_per_min")
                dpm_band = self._assess_against_distribution(dpm, dpm_dist) if dpm_dist else "unknown"
                if dpm_band in ("bottom_25", "bottom_10"):
                    divergences.append(f"Lost with low deaths ({deaths}) and low DPM ({dpm:.0f}) — no impact")
                else:
                    divergences.append(f"Lost with low deaths ({deaths}) but {dpm:.0f} DPM — couldn't convert survival")
            else:
                divergences.append(f"Lost with low deaths ({deaths})")

        # Early deaths but good CS (recovery structural pattern)
        if game.early_deaths > 0 and assessments.get("cs_at_10") == "excellent":
            divergences.append(f"CS maintained despite {game.early_deaths} early deaths")

        # High damage but loss — DPM in top 25%, loss
        if not win and engines.combat and dpm > 0:
            dpm_dist = engines.combat.distributions.get("damage_per_min")
            dpm_band = self._assess_against_distribution(dpm, dpm_dist) if dpm_dist else "unknown"
            if dpm_band in ("top_25", "top_10"):
                divergences.append(f"High DPM ({dpm:.0f}) but loss — team couldn't convert {dpm:.0f} DPM into a win")

        # High survival metrics but loss — heal/mit/CC in top 25%, loss
        if not win and engines.durability:
            heal = durability.get("total_heal", 0)
            mit = durability.get("damage_mitigated", 0)
            cc = durability.get("cc_time", 0)
            heal_dist = engines.durability.distributions.get("total_heal")
            mit_dist = engines.durability.distributions.get("damage_mitigated")
            cc_dist = engines.durability.distributions.get("cc_time")
            heal_band = self._assess_against_distribution(heal, heal_dist) if heal_dist else "unknown"
            mit_band = self._assess_against_distribution(mit, mit_dist) if mit_dist else "unknown"
            cc_band = self._assess_against_distribution(cc, cc_dist) if cc_dist else "unknown"
            if heal_band in ("top_25", "top_10") and heal > 0:
                divergences.append(f"High healing ({heal//1000}k) but loss — outlasted without converting to kills")
            if mit_band in ("top_25", "top_10") and mit > 0:
                divergences.append(f"High mitigation ({mit//1000}k) but loss — soaked damage without creating pressure")
            if cc_band in ("top_25", "top_10") and cc > 0:
                divergences.append(f"High CC ({cc:.0f}s) but loss — CC didn't convert to kills")

        return divergences


def run_synthesis(game: Game, engines: MultiEngineOutput,
                  player_model: PlayerModel) -> Optional[Verdict]:
    """
    Convenience function to synthesize a verdict for a game with multi-engine support.
    """
    if not game:
        return None

    synthesis = SynthesisLayer(player_model)
    return synthesis.analyze_single_game(game, engines)


if __name__ == "__main__":
    # Test synthesis
    from verdict_engine_death import run_death_engine
    from verdict_engine_economy import run_economy_engine
    from verdict_engine_combat import run_combat_engine
    from verdict_engine_durability import run_durability_engine
    from verdict_engine_vision import run_vision_engine
    from verdict_engine_objective import run_objective_engine
    from verdict_engine_draft import run_draft_engine

    # Run engines using convenience functions (loads from cache)
    death_output = run_death_engine()
    economy_output = run_economy_engine()
    combat_output = run_combat_engine()
    durability_output = run_durability_engine()
    vision_output = run_vision_engine()
    objective_output = run_objective_engine()
    draft_output = run_draft_engine()

    if not death_output:
        print("No cache found. Run 'face fetch' first.")
        exit(1)

    # Load cache for games and player_id
    import json
    from verdict_paths import CACHE_PATH
    try:
        with open(CACHE_PATH, 'r') as f:
            cache = json.load(f)
        games = cache.get("games", [])
        player_id = cache.get("puuid", "test_player")
    except FileNotFoundError:
        print("No cache found. Run 'face fetch' first.")
        exit(1)

    if not games:
        print("No games in cache.")
        exit(1)

    latest_game = games[0]

    engines = MultiEngineOutput(
        death=death_output, economy=economy_output, combat=combat_output,
        durability=durability_output, vision=vision_output,
        objective=objective_output, draft=draft_output,
    )

    # Load player model
    from verdict_player_model import get_or_create_player_model
    player_model = get_or_create_player_model(player_id, games)

    # Run synthesis
    verdict = run_synthesis(latest_game, engines, player_model)

    if verdict:
        print(f"=== VERDICT for {latest_game.champion} {'WIN' if latest_game.win else 'LOSS'} ===\\n")
        print(f"STATEMENT: {verdict.statement}\\n")
        print(f"CONFIDENCE: {verdict.confidence:.0%}\\n")
        print(f"SUMMARY: {verdict.summary}\\n")
        print("EVIDENCE:")
        for e in verdict.primary_evidence:
            print(f"  • {e.description}: {e.value} ({e.context})")
        print(f"\\nMATCHED PATTERNS: {', '.join(verdict.matched_patterns) if verdict.matched_patterns else 'None'}")
        print(f"DIVERGENCES: {', '.join(verdict.divergences) if verdict.divergences else 'None'}")
        print("\\nLESSONS:")
        for lesson in verdict.lessons:
            print(f"  [{lesson.priority.upper()}] {lesson.text}")
    else:
        print("Could not generate verdict.")
