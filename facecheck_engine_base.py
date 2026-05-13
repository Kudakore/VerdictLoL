"""
Engine Base - FaceCheck Engine Architecture

Shared base classes for all domain-pure extraction engines.
No engine-specific logic here — just the data structures.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import statistics


@dataclass
class Distribution:
    """Rich distributional data, not just average."""
    values: List[float]
    mean: float
    median: float
    std_dev: float
    percentiles: Dict[int, float]
    min: float
    max: float
    sample_size: int

    @classmethod
    def from_values(cls, values: List[float]) -> "Distribution":
        if not values:
            return cls([], 0, 0, 0, {}, 0, 0, 0)
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return cls(
            values=sorted_vals,
            mean=statistics.mean(sorted_vals),
            median=statistics.median(sorted_vals),
            std_dev=statistics.stdev(sorted_vals) if n > 1 else 0,
            percentiles={
                10: sorted_vals[n // 10] if n >= 10 else sorted_vals[0],
                25: sorted_vals[n // 4] if n >= 4 else sorted_vals[0],
                50: sorted_vals[n // 2],
                75: sorted_vals[3 * n // 4] if n >= 4 else sorted_vals[-1],
                90: sorted_vals[9 * n // 10] if n >= 10 else sorted_vals[-1],
                95: sorted_vals[95 * n // 100] if n >= 20 else sorted_vals[-1],
            },
            min=sorted_vals[0],
            max=sorted_vals[-1],
            sample_size=n
        )


@dataclass
class EngineNode:
    """A point in time with context and relationships."""
    node_id: str
    timestamp_min: float
    node_type: str
    value: any
    context: Dict


@dataclass
class EngineSignature:
    """Identifiable pattern in engine data."""
    signature_id: str
    signature_type: str
    nodes: List[str]
    start_min: float
    end_min: float
    features: Dict
    confidence: float


@dataclass
class EngineOutput:
    """Standard output format for all engines."""
    engine_name: str
    timestamp: datetime
    distributions: Dict[str, Distribution]
    nodes: List[EngineNode]
    signatures: List[EngineSignature]
    correlation_space: Dict[str, List[float]]
    confidence: float
    source_games: List[str]
    raw_metrics: Dict


def run_engine_from_cache(engine_class, cache_path: str = "C:\\Facecheck\\facecheck_cache.json",
                          games=None, player_id=None) -> Optional[EngineOutput]:
    """
    Run any engine class, either from explicit data or from cache.

    If games and player_id are provided, uses them directly (no file read).
    Otherwise, loads from cache_path (backward compatible).
    """
    if games is not None and player_id is not None:
        engine = engine_class(player_id)
        return engine.analyze(games)

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    games = cache.get("games", [])
    player_id = cache.get("puuid", "")
    if not games:
        return None
    engine = engine_class(player_id)
    return engine.analyze(games)
