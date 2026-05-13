"""
Engine Base - FaceCheck Engine Architecture

Shared base classes for all domain-pure extraction engines.
No engine-specific logic here — just the data structures.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
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

    def to_dict(self) -> Dict:
        return {
            "values": self.values,
            "mean": self.mean,
            "median": self.median,
            "std_dev": self.std_dev,
            "percentiles": {str(k): v for k, v in self.percentiles.items()},
            "min": self.min,
            "max": self.max,
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Distribution":
        return cls(
            values=d["values"],
            mean=d["mean"],
            median=d["median"],
            std_dev=d["std_dev"],
            percentiles={int(k): v for k, v in d["percentiles"].items()},
            min=d["min"],
            max=d["max"],
            sample_size=d["sample_size"],
        )


@dataclass
class EngineNode:
    """A point in time with context and relationships."""
    node_id: str
    timestamp_min: float
    node_type: str
    value: Any
    context: Dict

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "timestamp_min": self.timestamp_min,
            "node_type": self.node_type,
            "value": self.value,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "EngineNode":
        return cls(
            node_id=d["node_id"],
            timestamp_min=d["timestamp_min"],
            node_type=d["node_type"],
            value=d["value"],
            context=d["context"],
        )


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

    def to_dict(self) -> Dict:
        return {
            "signature_id": self.signature_id,
            "signature_type": self.signature_type,
            "nodes": self.nodes,
            "start_min": self.start_min,
            "end_min": self.end_min,
            "features": self.features,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "EngineSignature":
        return cls(
            signature_id=d["signature_id"],
            signature_type=d["signature_type"],
            nodes=d["nodes"],
            start_min=d["start_min"],
            end_min=d["end_min"],
            features=d["features"],
            confidence=d["confidence"],
        )


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

    def to_dict(self) -> Dict:
        return {
            "engine_name": self.engine_name,
            "timestamp": self.timestamp.isoformat(),
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
            "nodes": [n.to_dict() for n in self.nodes],
            "signatures": [s.to_dict() for s in self.signatures],
            "correlation_space": self.correlation_space,
            "confidence": self.confidence,
            "source_games": self.source_games,
            "raw_metrics": self.raw_metrics,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "EngineOutput":
        return cls(
            engine_name=d["engine_name"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            distributions={k: Distribution.from_dict(v) for k, v in d["distributions"].items()},
            nodes=[EngineNode.from_dict(n) for n in d["nodes"]],
            signatures=[EngineSignature.from_dict(s) for s in d["signatures"]],
            correlation_space=d["correlation_space"],
            confidence=d["confidence"],
            source_games=d["source_games"],
            raw_metrics=d["raw_metrics"],
        )


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
