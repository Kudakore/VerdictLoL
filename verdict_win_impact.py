"""
Win Impact Engine - Verdict Engine Architecture

Domain: quantitative impact analysis.
Measures how much each problem signal hurts or helps win rate.

Runs across ALL games in batch — not per-game extraction.
Impact statistics require the full distribution, so this cannot run on a single game.

The key output per problem signal:
- games_affected: how many games had this pattern
- win_rate: win rate when pattern was present
- baseline: overall win rate
- delta: the key number (win_rate - baseline)
- compensating_factors: what winning games WITH this problem had in common
- classification: loss_guarantor / recoverable / neutral / lever

Assessment belongs in synthesis — this engine quantifies, not explains.
Win Impact does NOT determine why something hurts or helps — only how much.
"""

import json
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# Classification thresholds
LOSS_GUARANTOR_DELTA = -0.15   # -15% — problem alone predicts loss
LEVER_DELTA = 0.15             # +15% — pattern predicts winning
NEUTRAL_BAND = 0.15            # delta within ±15% is neutral


@dataclass
class CompensatingFactor:
    """A factor that improved outcomes when combined with the problem signal."""
    factor_key: str             # e.g., "dragon_control", "cs_lead_15"
    factor_label: str           # human-readable: "Dragon Control", "CS Lead at 15"
    games_with_both: int
    win_rate_with_both: float
    delta_vs_problem: float     # improvement over problem-only win rate
    delta_vs_baseline: float   # improvement over overall baseline


@dataclass
class WinImpactSignature:
    """Impact statistics for a single problem signal type."""
    signature_type: str          # e.g., "death_cluster", "cs_deficit", "early_deaths"
    games_affected: int         # count of games where this pattern occurred
    total_games: int            # total games analyzed
    win_rate_when_present: float
    baseline_win_rate: float
    delta: float                # win_rate_when_present - baseline (the key number)
    compensating_factors: List[CompensatingFactor]
    classification: str         # "loss_guarantor" | "recoverable" | "neutral" | "lever"
    confidence: float           # based on sample size (games_affected)


class WinImpactEngine:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.games = []
        self.signatures: List[WinImpactSignature] = []
        self.baseline_win_rate: float = 0.0

    def analyze(self, games) -> "WinImpactOutput":
        """
        Analyze all games for problem signal impact.
        For each signature type found in the games, compute:
        - Win rate when signal is present vs absent
        - Compensating factors from winning subset
        - Classification
        """
        self.games = games
        self.signatures = []

        wins = sum(1 for g in games if g.win)
        self.baseline_win_rate = wins / len(games) if games else 0.5

        # Group games by which problem signals they contain
        signal_games = self._group_games_by_signals(games)

        for sig_type, game_indices in signal_games.items():
            impact = self._compute_signal_impact(sig_type, game_indices)
            if impact:
                self.signatures.append(impact)

        # Sort by delta (most harmful first)
        self.signatures.sort(key=lambda x: x.delta)

        return WinImpactOutput(
            player_id=self.player_id,
            timestamp=datetime.now(),
            baseline_win_rate=self.baseline_win_rate,
            total_games=len(games),
            signatures=self.signatures,
            confidence=self._compute_confidence()
        )

    def _group_games_by_signals(self, games) -> Dict[str, List[int]]:
        """
        Go through all games and tag which problem signals each one has.
        Returns: {signal_type: [game_index, ...]}
        """
        signal_map: Dict[str, List[int]] = {}

        for i, game in enumerate(games):
            sigs = self._extract_game_signatures(game)

            for sig_type in sigs:
                if sig_type not in signal_map:
                    signal_map[sig_type] = []
                signal_map[sig_type].append(i)

        return signal_map

    def _extract_game_signatures(self, game) -> List[str]:
        """
        Extract problem signal types present in a single game.
        Uses structural data available in the game record.
        """
        signals = []

        # ── Death-based signals ───────────────────────────
        deaths = game.deaths
        death_minutes = game.death_minutes

        # Early deaths (before 10 min)
        if game.early_deaths >= 2:
            signals.append("early_deaths")

        # Death cluster: 2+ deaths within 4 minutes
        if len(death_minutes) >= 2:
            for j in range(1, len(death_minutes)):
                if death_minutes[j] - death_minutes[j - 1] <= 4:
                    signals.append("death_cluster")
                    break

        # High death count
        if deaths >= 8:
            signals.append("high_deaths")
        elif deaths <= 2:
            signals.append("low_deaths")

        # Death chain: 3+ deaths with shrinking gaps
        if len(death_minutes) >= 3:
            gaps = [death_minutes[j] - death_minutes[j - 1] for j in range(1, len(death_minutes))]
            for k in range(1, len(gaps)):
                if gaps[k] < gaps[k - 1]:
                    signals.append("death_chain")
                    break

        # ── CS-based signals ───────────────────────────────
        cs_10 = game.cs_10 or 0
        cs_15 = game.cs_15 or 0

        if cs_10 < 35:
            signals.append("cs_deficit_early")
        if cs_15 < 80:
            signals.append("cs_deficit_mid")

        # ── Economy signals ────────────────────────────────
        gold_lead_15 = game.gold_lead_15 or 0
        if gold_lead_15 < -500:
            signals.append("gold_deficit")
        elif gold_lead_15 > 500:
            signals.append("gold_lead")

        # ── Combat signals ───────────────────────────────
        damage = game.damage
        kp_pct = game.kp_pct

        if damage > 0 and kp_pct < 40:
            signals.append("low_kill_participation")

        # ── Vision signals ────────────────────────────────
        vision = game.vision
        if vision > 0 and vision < 30:
            signals.append("low_vision")

        # ── Objective signals ─────────────────────────────
        turret_kills = game.turret_kills

        if game.my_team.dragon_kills == 0 and game.duration_min > 15:
            signals.append("no_dragon")

        if turret_kills == 0 and game.duration_min > 20:
            signals.append("no_turrets")

        # ── Draft signals ────────────────────────────────
        side = game.side
        if side == "blue":
            signals.append("blue_side")
        elif side == "red":
            signals.append("red_side")

        return signals

    def _compute_signal_impact(self, sig_type: str, game_indices: List[int]) -> Optional[WinImpactSignature]:
        """Compute impact stats for a single signal type."""
        if len(game_indices) < 3:
            return None  # need minimum sample size

        # Win rate when signal is present
        wins_with_signal = sum(1 for i in game_indices if self.games[i].win)
        win_rate_present = wins_with_signal / len(game_indices)

        delta = win_rate_present - self.baseline_win_rate

        # Find compensating factors in the winning subset
        winning_indices = [i for i in game_indices if self.games[i].win]
        compensating_factors = self._find_compensating_factors(sig_type, winning_indices)

        # Classify
        classification = self._classify(delta, compensating_factors)

        return WinImpactSignature(
            signature_type=sig_type,
            games_affected=len(game_indices),
            total_games=len(self.games),
            win_rate_when_present=round(win_rate_present, 3),
            baseline_win_rate=round(self.baseline_win_rate, 3),
            delta=round(delta, 3),
            compensating_factors=compensating_factors,
            classification=classification,
            confidence=min(len(game_indices) / 30, 0.95)
        )

    def _find_compensating_factors(self, problem_sig: str, winning_games: List[int]) -> List[CompensatingFactor]:
        """
        For games where this problem signal occurred AND we won,
        find what else was true that might explain the recovery.
        """
        if len(winning_games) < 2:
            return []

        factors = []
        problem_games = set(winning_games)

        # Test various compensating factors
        candidate_factors = [
            ("dragon_control", lambda g: g.my_team.dragon_kills > 0),
            ("herald_control", lambda g: g.my_team.rift_herald_kills > 0),
            ("turret_push", lambda g: g.turret_kills > 0),
            ("vision_presence", lambda g: g.vision >= 40),
            ("cs_recovery", lambda g: (g.cs_15 or 0) >= 80),
            ("gold_comeback", lambda g: (g.gold_lead_15 or 0) > 0),
            ("low_deaths", lambda g: g.deaths <= 4),
            ("high_damage", lambda g: g.damage >= 15000),
            ("kill_participation", lambda g: g.kp_pct >= 60),
        ]

        for factor_key, factor_fn in candidate_factors:
            # How many winning games had this factor?
            games_with_factor = [i for i in problem_games if factor_fn(self.games[i])]

            if len(games_with_factor) >= 2:
                wr_with_factor = sum(1 for i in games_with_factor if self.games[i].win) / len(games_with_factor)
                delta_vs_problem = wr_with_factor - (sum(1 for i in problem_games if self.games[i].win) / len(problem_games))
                delta_vs_baseline = wr_with_factor - self.baseline_win_rate

                if delta_vs_problem > 0.05:  # at least +5% improvement
                    factor_label = factor_key.replace("_", " ").title()
                    factors.append(CompensatingFactor(
                        factor_key=factor_key,
                        factor_label=factor_label,
                        games_with_both=len(games_with_factor),
                        win_rate_with_both=round(wr_with_factor, 3),
                        delta_vs_problem=round(delta_vs_problem, 3),
                        delta_vs_baseline=round(delta_vs_baseline, 3)
                    ))

        # Sort by improvement
        factors.sort(key=lambda x: x.delta_vs_problem, reverse=True)
        return factors[:5]  # top 5 only

    def _classify(self, delta: float, compensating_factors: List[CompensatingFactor]) -> str:
        """Classify the problem signal impact."""
        if delta < -0.10 and not compensating_factors:
            return "loss_guarantor"
        elif delta < -0.05 and compensating_factors:
            return "recoverable"
        elif delta > 0.10:
            return "lever"
        else:
            return "neutral"

    def _compute_confidence(self) -> float:
        if not self.games:
            return 0.0
        return min(len(self.games) / 50, 0.95)


@dataclass
class WinImpactOutput:
    """Full Win Impact analysis for a player."""
    player_id: str
    timestamp: datetime
    baseline_win_rate: float
    total_games: int
    signatures: List[WinImpactSignature]
    confidence: float

    def get_by_classification(self, classification: str) -> List[WinImpactSignature]:
        return [s for s in self.signatures if s.classification == classification]

    def get_problems(self) -> List[WinImpactSignature]:
        """All harmful signals (loss_guarantor + recoverable)."""
        return [s for s in self.signatures if s.classification in ("loss_guarantor", "recoverable")]

    def get_levers(self) -> List[WinImpactSignature]:
        """All beneficial signals."""
        return [s for s in self.signatures if s.classification == "lever"]


def run_win_impact_engine(games=None, player_id=None, cache_path=None) -> Optional[WinImpactOutput]:
    """Run the Win Impact engine.

    Primary interface: pass games and player_id directly.
    Fallback: load from cache if games/player_id not provided.
    """
    if games is not None and player_id is not None:
        engine = WinImpactEngine(player_id)
        return engine.analyze(games)

    if cache_path is None:
        from verdict_paths import CACHE_PATH
        cache_path = CACHE_PATH
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    games = cache.get("games", [])
    player_id = cache.get("puuid", "")
    if not games:
        return None

    engine = WinImpactEngine(player_id)
    return engine.analyze(games)


if __name__ == "__main__":
    output = run_win_impact_engine()
    if not output:
        print("No data available.")
        exit()

    print(f"Win Impact Analysis — {output.player_id[:20]}")
    print(f"Baseline WR: {output.baseline_win_rate:.1%} across {output.total_games} games")
    print(f"Confidence: {output.confidence:.0%}")
    print()

    for cls in ["loss_guarantor", "recoverable", "neutral", "lever"]:
        group = output.get_by_classification(cls)
        if not group:
            continue
        print(f"══ {cls.upper().replace('_', ' ')} ══")
        for sig in group:
            print(f"  {sig.signature_type}")
            print(f"    {sig.games_affected} games | WR: {sig.win_rate_when_present:.1%} | Δ: {sig.delta:+.1%}")
            if sig.compensating_factors:
                print(f"    Compensating factors:")
                for cf in sig.compensating_factors:
                    print(f"      {cf.factor_label}: +{cf.delta_vs_problem:.0%} ({cf.games_with_both} games)")
        print()