"""
Player Model - FaceCheck Engine Architecture

Persistent player pattern storage and learning.
Accumulates and refines over time in facecheck_brain.json.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set
from datetime import datetime
import json
import os
import statistics
from collections import defaultdict


BRAIN_PATH = "C:\\Facecheck\\facecheck_brain.json"


@dataclass
class PatternMemory:
    """Accumulated pattern occurrences with evolution tracking."""
    pattern_id: str  # e.g., "early_death_spiral"
    pattern_type: str  # "harmful", "beneficial", "neutral"
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    avg_confidence: float = 0.0
    features_over_time: List[Dict] = field(default_factory=list)  # Last 10 feature snapshots
    co_occurs_with: Dict[str, int] = field(default_factory=dict)  # pattern_id -> count
    precedes: Dict[str, int] = field(default_factory=dict)  # pattern_id -> count (this pattern precedes)
    follows: Dict[str, int] = field(default_factory=dict)  # pattern_id -> count (this pattern follows)

    def record_occurrence(self, win: bool, confidence: float, features: Dict, timestamp: datetime):
        """Record a new occurrence of this pattern."""
        self.occurrence_count += 1
        if win:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.last_seen = timestamp

        # Update average confidence
        self.avg_confidence = (self.avg_confidence * (self.occurrence_count - 1) + confidence) / self.occurrence_count

        # Keep last 10 feature snapshots
        self.features_over_time.append({"timestamp": timestamp.isoformat(), **features})
        if len(self.features_over_time) > 10:
            self.features_over_time = self.features_over_time[-10:]

    def win_rate(self) -> float:
        """Win rate when this pattern occurs."""
        if self.occurrence_count == 0:
            return 0.0
        return self.win_count / self.occurrence_count

    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "occurrence_count": self.occurrence_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "avg_confidence": self.avg_confidence,
            "features_over_time": self.features_over_time,
            "co_occurs_with": self.co_occurs_with,
            "precedes": self.precedes,
            "follows": self.follows,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PatternMemory":
        return cls(
            pattern_id=data["pattern_id"],
            pattern_type=data["pattern_type"],
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            occurrence_count=data.get("occurrence_count", 0),
            win_count=data.get("win_count", 0),
            loss_count=data.get("loss_count", 0),
            avg_confidence=data.get("avg_confidence", 0.0),
            features_over_time=data.get("features_over_time", []),
            co_occurs_with=data.get("co_occurs_with", {}),
            precedes=data.get("precedes", {}),
            follows=data.get("follows", {}),
        )


@dataclass
class PlayerBaseline:
    """Personal baselines for key metrics (not generic thresholds)."""
    metric_name: str
    mean: float
    median: float
    p10: float
    p25: float
    p75: float
    p90: float
    losing_threshold: float  # P10 (you're below this = bad for you)
    winning_threshold: float  # P90 (you're above this = good for you)
    last_updated: datetime

    @classmethod
    def from_values(cls, metric_name: str, values: List[float], timestamp: datetime) -> "PlayerBaseline":
        if not values:
            return cls(metric_name, 0, 0, 0, 0, 0, 0, 0, 0, timestamp)
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mean = statistics.mean(sorted_vals)
        median = statistics.median(sorted_vals)
        p10 = sorted_vals[n // 10] if n >= 10 else sorted_vals[0]
        p25 = sorted_vals[n // 4] if n >= 4 else sorted_vals[0]
        p75 = sorted_vals[3 * n // 4] if n >= 4 else sorted_vals[-1]
        p90 = sorted_vals[9 * n // 10] if n >= 10 else sorted_vals[-1]
        return cls(
            metric_name=metric_name,
            mean=mean,
            median=median,
            p10=p10,
            p25=p25,
            p75=p75,
            p90=p90,
            losing_threshold=p10,  # Below P10 = concerning for you
            winning_threshold=p90,  # Above P90 = excellent for you
            last_updated=timestamp
        )

    def to_dict(self) -> Dict:
        return {
            "metric_name": self.metric_name,
            "mean": self.mean,
            "median": self.median,
            "p10": self.p10,
            "p25": self.p25,
            "p75": self.p75,
            "p90": self.p90,
            "losing_threshold": self.losing_threshold,
            "winning_threshold": self.winning_threshold,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PlayerBaseline":
        return cls(
            metric_name=data["metric_name"],
            mean=data["mean"],
            median=data["median"],
            p10=data["p10"],
            p25=data["p25"],
            p75=data["p75"],
            p90=data["p90"],
            losing_threshold=data["losing_threshold"],
            winning_threshold=data["winning_threshold"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )

    def assess(self, value: float) -> str:
        """Assess a value against personal baseline."""
        if value <= self.p10:
            return "critical"  # Bottom 10% for you
        elif value <= self.p25:
            return "below_average"  # Below your average
        elif value >= self.p90:
            return "excellent"  # Top 10% for you
        elif value >= self.p75:
            return "above_average"  # Above your average
        else:
            return "typical"  # Middle range


@dataclass
class CausalRelationship:
    """Learned cause-effect relationship between patterns or metrics."""
    cause: str
    effect: str
    strength: float  # 0-1 correlation strength
    confidence: float  # Statistical confidence
    sample_size: int
    first_observed: datetime
    last_observed: datetime

    def to_dict(self) -> Dict:
        return {
            "cause": self.cause,
            "effect": self.effect,
            "strength": self.strength,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "first_observed": self.first_observed.isoformat(),
            "last_observed": self.last_observed.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CausalRelationship":
        return cls(
            cause=data["cause"],
            effect=data["effect"],
            strength=data["strength"],
            confidence=data["confidence"],
            sample_size=data["sample_size"],
            first_observed=datetime.fromisoformat(data["first_observed"]),
            last_observed=datetime.fromisoformat(data["last_observed"]),
        )


class PlayerModel:
    """
    Persistent player model for FaceCheck.

    Stores:
    - Personal baselines (YOUR thresholds, not generic)
    - Pattern memory (accumulated pattern occurrences)
    - Causal web (learned relationships)
    - Engine outputs (historical engine runs)
    """

    def __init__(self, player_id: str):
        self.player_id = player_id
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.baselines: Dict[str, PlayerBaseline] = {}
        self.patterns: Dict[str, PatternMemory] = {}
        self.causality: Dict[str, CausalRelationship] = {}
        self.game_ids: Set[str] = set()  # Track which games are incorporated

    def update_from_games(self, games: List[Dict]):
        """Update baselines and patterns from new games."""
        timestamp = datetime.now()

        # Calculate baselines from all games
        self._update_baselines(games, timestamp)

        # Update pattern tracking
        self._update_pattern_counts(games, timestamp)

        self.last_updated = timestamp

    def _update_baselines(self, games: List[Dict], timestamp: datetime):
        """Calculate personal baselines from game data."""
        metrics = {
            "cs_at_10": [g.get("cs_10") for g in games if g.get("cs_10")],
            "cs_at_15": [g.get("cs_15") for g in games if g.get("cs_15")],
            "deaths_per_game": [g.get("deaths", 0) for g in games],
            "early_deaths": [g.get("early_deaths", 0) for g in games],
            "gold_lead_15": [g.get("gold_lead_15", 0) for g in games if g.get("gold_lead_15") is not None],
            "vision_per_min": [g.get("vision_per_min", 0) for g in games],
            "damage_per_min": [g.get("damage_per_min", 0) for g in games],
        }

        for metric_name, values in metrics.items():
            if values:
                self.baselines[metric_name] = PlayerBaseline.from_values(
                    metric_name, values, timestamp
                )

    def _update_pattern_counts(self, games: List[Dict], timestamp: datetime):
        """Update pattern counts from game outcomes."""
        # Phase 1: Hard-coded patterns based on simple game data
        # In Phase 3, this will integrate with Temporal Engine signatures

        for game in games:
            game_id = game.get("match_id", "")
            if game_id in self.game_ids:
                continue  # Already processed
            self.game_ids.add(game_id)

            win = game.get("win", False)

            # Pattern 1: High death count (> P90 of personal baseline)
            deaths = game.get("deaths", 0)
            baseline = self.baselines.get("deaths_per_game")
            if baseline and deaths >= baseline.p90:
                self._record_pattern(
                    "high_death_game",
                    "harmful",
                    win,
                    0.7,
                    {"deaths": deaths, "baseline_p90": baseline.p90},
                    timestamp
                )

            # Pattern 2: CS recovery (died early but CS at 10 > P75)
            early_deaths = game.get("early_deaths", 0)
            cs_10 = game.get("cs_10")
            cs_baseline = self.baselines.get("cs_at_10")
            if early_deaths > 0 and cs_10 and cs_baseline and cs_10 >= cs_baseline.p75:
                self._record_pattern(
                    "cs_recovery_after_early_death",
                    "beneficial",
                    win,
                    0.6,
                    {"early_deaths": early_deaths, "cs_10": cs_10, "p75": cs_baseline.p75},
                    timestamp
                )

            # Pattern 3: Early gold lead (won laning phase)
            gold_lead = game.get("gold_lead_15")
            if gold_lead and gold_lead > 1000:
                self._record_pattern(
                    "strong_laning_phase",
                    "beneficial",
                    win,
                    0.8,
                    {"gold_lead_15": gold_lead},
                    timestamp
                )

    def _record_pattern(self, pattern_id: str, pattern_type: str, win: bool,
                       confidence: float, features: Dict, timestamp: datetime):
        """Record a pattern occurrence."""
        if pattern_id not in self.patterns:
            self.patterns[pattern_id] = PatternMemory(
                pattern_id=pattern_id,
                pattern_type=pattern_type,
                first_seen=timestamp,
                last_seen=timestamp,
            )

        self.patterns[pattern_id].record_occurrence(win, confidence, features, timestamp)

    def get_pattern(self, pattern_id: str) -> Optional[PatternMemory]:
        """Get a specific pattern by ID."""
        return self.patterns.get(pattern_id)

    def get_baseline(self, metric: str) -> Optional[PlayerBaseline]:
        """Get baseline for a specific metric."""
        return self.baselines.get(metric)

    def assess_game(self, game: Dict) -> Dict[str, str]:
        """Assess a game against personal baselines."""
        assessments = {}

        for metric, baseline in self.baselines.items():
            value = game.get(metric.replace("_per_game", "").replace("at_", "_"))
            if value is not None:
                assessments[metric] = baseline.assess(value)

        return assessments

    def to_dict(self) -> Dict:
        """Serialize to dict for JSON storage."""
        return {
            "player_id": self.player_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "baselines": {k: v.to_dict() for k, v in self.baselines.items()},
            "patterns": {k: v.to_dict() for k, v in self.patterns.items()},
            "causality": {k: v.to_dict() for k, v in self.causality.items()},
            "game_ids": list(self.game_ids),
            "version": "1.0",  # For future migrations
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PlayerModel":
        """Deserialize from dict."""
        model = cls(data["player_id"])
        model.created_at = datetime.fromisoformat(data["created_at"])
        model.last_updated = datetime.fromisoformat(data["last_updated"])
        model.baselines = {k: PlayerBaseline.from_dict(v) for k, v in data.get("baselines", {}).items()}
        model.patterns = {k: PatternMemory.from_dict(v) for k, v in data.get("patterns", {}).items()}
        model.causality = {k: CausalRelationship.from_dict(v) for k, v in data.get("causality", {}).items()}
        model.game_ids = set(data.get("game_ids", []))
        return model

    def save(self, path: str = BRAIN_PATH):
        """Save to disk."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, player_id: str, path: str = BRAIN_PATH) -> "PlayerModel":
        """Load from disk or create new."""
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get("player_id") == player_id:
                    return cls.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass
        return cls(player_id)


def get_or_create_player_model(player_id: str, games: List[Dict] = None) -> PlayerModel:
    """
    Load existing player model or create new one.
    If games provided, update the model with them.
    """
    model = PlayerModel.load(player_id)

    if games:
        model.update_from_games(games)
        model.save()

    return model


if __name__ == "__main__":
    # Test the player model
    import json

    try:
        with open("C:\\Facecheck\\facecheck_cache.json", 'r') as f:
            cache = json.load(f)
        games = cache.get("games", [])
        player_id = cache.get("puuid", "test_player")
    except FileNotFoundError:
        games = []
        player_id = "test_player"

    model = get_or_create_player_model(player_id, games)

    print(f"Player Model for {player_id[:20]}...")
    print(f"  Created: {model.created_at.strftime('%Y-%m-%d')}")
    print(f"  Last updated: {model.last_updated.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Games in memory: {len(model.game_ids)}")
    print(f"  Baselines: {len(model.baselines)}")
    print(f"  Patterns: {len(model.patterns)}")

    print("\nPersonal Baselines:")
    for name, baseline in model.baselines.items():
        print(f"  {name}: mean={baseline.mean:.1f}, losing_threshold={baseline.losing_threshold:.1f}, winning_threshold={baseline.winning_threshold:.1f}")

    print("\nPattern Memory:")
    for name, pattern in model.patterns.items():
        print(f"  {name}: {pattern.occurrence_count}x, win_rate={pattern.win_rate():.1%}, type={pattern.pattern_type}")
