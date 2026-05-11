"""
Similarity Engine — FaceCheck Engine Architecture

Domain: behavioral fingerprinting and game similarity.
Assigns each game a behavioral fingerprint vector (5 dimensions).
Provides nearest-neighbor search: given a game, find the K most similar games.
Provides matched comparison: given a signal, find similar games with/without it.

The fingerprint is a 5-D vector in [0, 1]^5 per game.
All dimensions use percentile-rank normalization against Kuda's own distribution —
so a 0.9 means "top 10% of your games" regardless of raw scale.

Session 1: Fingerprint extraction + nearest neighbor search
Session 2: Clustering + cluster-level outcome analysis
Session 3: Matched comparison for counterfactual reasoning
"""

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# ────────────────────────────────────────────────────────────────
# Fingerprint Dataclasses
# ────────────────────────────────────────────────────────────────

@dataclass
class GameFingerprint:
    """5-D behavioral fingerprint of a single game."""
    match_id: str
    champion: str
    win: bool
    duration_min: float

    # The 5 dimensions — all normalized [0, 1]
    aggression: float      # fight intensity
    efficiency: float      # resource acquisition
    objective_race: float  # map pressure / objective push
    collapse: float        # snowball potential
    vision: float           # map control

    # Raw components (for debugging / display)
    raw_kills_pm: float
    raw_assists_pm: float
    raw_damage_pm: float
    raw_cs_pm: float
    raw_cs_10: float
    raw_turret_kills: int
    raw_lks: int
    raw_gold_lead_15: int
    raw_vision_pm: float
    raw_wards_placed: float


@dataclass
class SimilarityResult:
    """A similar game with distance metric and outcome."""
    match_id: str
    champion: str
    win: bool
    distance: float         # euclidean distance in fingerprint space
    fingerprint: GameFingerprint


# ────────────────────────────────────────────────────────────────
# Percentile Rank Helper
# ────────────────────────────────────────────────────────────────

def _percentile_rank(value: float, distribution: List[float]) -> float:
    """Convert a raw value to a percentile rank in [0, 1]."""
    if not distribution:
        return 0.5
    count_below = sum(1 for v in distribution if v < value)
    count_equal = sum(1 for v in distribution if v == value)
    return (count_below + 0.5 * count_equal) / len(distribution)


# ────────────────────────────────────────────────────────────────
# Main Engine
# ────────────────────────────────────────────────────────────────

class SimilarityEngine:
    """
    Builds behavioral fingerprints for all games and enables
    nearest-neighbor queries and matched comparisons.
    """

    def __init__(self):
        self.player_id: str = ""
        self.games: List[Dict] = []
        self.fingerprints: List[GameFingerprint] = []
        self._distributions: Dict[str, List[float]] = {}

    def analyze(self, games: List[Dict]) -> "SimilarityOutput":
        """
        Build fingerprints for all games. Call once per session.
        """
        self.games = games
        self.player_id = games[0].get("puuid", "") if games else ""
        self.fingerprints = []
        self._distributions = {}

        # Pre-compute distributions for normalization
        self._compute_distributions(games)

        # Build fingerprints
        for game in games:
            fp = self._extract_fingerprint(game)
            self.fingerprints.append(fp)

        return SimilarityOutput(
            player_id=self.player_id,
            timestamp=datetime.now(),
            total_games=len(games),
            fingerprints=self.fingerprints,
            distributions=self._distributions,
            confidence=self._compute_confidence(games)
        )

    def _compute_distributions(self, games: List[Dict]):
        """Pre-compute all distributions for normalization."""
        raw_data = {
            "kills_pm": [],
            "assists_pm": [],
            "damage_pm": [],
            "cs_pm": [],
            "cs_10": [],
            "turret_kills": [],
            "lks": [],
            "gold_lead_15": [],
            "vision_pm": [],
            "wards_placed": [],
        }

        for g in games:
            dur = max(g.get("duration_min", 1), 1)
            kills = g.get("kills", 0) or 0
            assists = g.get("assists", 0) or 0
            damage = g.get("damage", 0) or 0

            raw_data["kills_pm"].append(kills / dur)
            raw_data["assists_pm"].append(assists / dur)
            raw_data["damage_pm"].append(damage / dur)
            raw_data["cs_pm"].append(g.get("cs_per_min", 0) or 0)
            raw_data["cs_10"].append(g.get("cs_10", 0) or 0)
            raw_data["turret_kills"].append(g.get("turret_kills", 0) or 0)
            raw_data["lks"].append(g.get("largest_killing_spree", 0) or 0)
            raw_data["gold_lead_15"].append(g.get("gold_lead_15", 0) or 0)
            raw_data["vision_pm"].append(g.get("vision_per_min", 0) or 0)
            raw_data["wards_placed"].append(g.get("wards_placed", 0) or 0)

        self._distributions = raw_data

    def _extract_fingerprint(self, game: Dict) -> GameFingerprint:
        """Build a 5-D fingerprint for one game."""
        dur = max(game.get("duration_min", 1), 1)

        # Raw components
        kills_pm = (game.get("kills", 0) or 0) / dur
        assists_pm = (game.get("assists", 0) or 0) / dur
        damage_pm = (game.get("damage", 0) or 0) / dur
        cs_pm = game.get("cs_per_min", 0) or 0
        cs_10 = game.get("cs_10", 0) or 0
        turret_kills = game.get("turret_kills", 0) or 0
        lks = game.get("largest_killing_spree", 0) or 0
        gold_lead_15 = game.get("gold_lead_15", 0) or 0
        vision_pm = game.get("vision_per_min", 0) or 0
        wards_placed = game.get("wards_placed", 0) or 0

        # Dimension 1: Aggression — fight intensity
        agg_k = _percentile_rank(kills_pm, self._distributions["kills_pm"])
        agg_a = _percentile_rank(assists_pm, self._distributions["assists_pm"])
        agg_d = _percentile_rank(damage_pm, self._distributions["damage_pm"])
        aggression = (agg_k * 0.4 + agg_a * 0.3 + agg_d * 0.3)

        # Dimension 2: Efficiency — farming and resource management
        eff_cs = _percentile_rank(cs_pm, self._distributions["cs_pm"])
        eff_cs10 = _percentile_rank(cs_10, self._distributions["cs_10"])
        efficiency = (eff_cs * 0.6 + eff_cs10 * 0.4)

        # Dimension 3: Objective Race — push vs farm
        # High turret_kills = high objective focus
        # High cs_pm might mean you're farming instead of pressuring
        # We want to reward turret_kills and slightly penalize camping
        obj_tk = _percentile_rank(turret_kills, self._distributions["turret_kills"])
        obj_cs = _percentile_rank(cs_pm, self._distributions["cs_pm"])
        objective_race = (obj_tk * 0.7 + (1 - obj_cs) * 0.3)  # inverse on cs to catch camping

        # Dimension 4: Collapse — snowball or get snowballed
        collapse_lks = _percentile_rank(lks, self._distributions["lks"])
        collapse_gl = _percentile_rank(gold_lead_15, self._distributions["gold_lead_15"])
        collapse = (collapse_lks * 0.5 + collapse_gl * 0.5)

        # Dimension 5: Vision — map control and information
        vis_vpm = _percentile_rank(vision_pm, self._distributions["vision_pm"])
        vis_wp = _percentile_rank(wards_placed, self._distributions["wards_placed"])
        vision = (vis_vpm * 0.6 + vis_wp * 0.4)

        return GameFingerprint(
            match_id=game.get("match_id", ""),
            champion=game.get("champion", ""),
            win=game.get("win", False),
            duration_min=dur,
            aggression=round(aggression, 4),
            efficiency=round(efficiency, 4),
            objective_race=round(objective_race, 4),
            collapse=round(collapse, 4),
            vision=round(vision, 4),
            raw_kills_pm=round(kills_pm, 3),
            raw_assists_pm=round(assists_pm, 3),
            raw_damage_pm=round(damage_pm, 1),
            raw_cs_pm=round(cs_pm, 2),
            raw_cs_10=round(cs_10, 1),
            raw_turret_kills=turret_kills,
            raw_lks=lks,
            raw_gold_lead_15=gold_lead_15,
            raw_vision_pm=round(vision_pm, 3),
            raw_wards_placed=wards_placed,
        )

    def nearest_neighbors(self, match_id: str, k: int = 5) -> List[SimilarityResult]:
        """
        Find the K games most similar to the given game,
        by euclidean distance in fingerprint space.
        """
        target_idx = None
        for i, g in enumerate(self.games):
            if g.get("match_id") == match_id:
                target_idx = i
                break

        if target_idx is None:
            return []

        target_fp = self.fingerprints[target_idx]
        target_game = self.games[target_idx]

        distances = []
        for i, fp in enumerate(self.fingerprints):
            if i == target_idx:
                continue
            dist = self._fingerprint_distance(target_fp, fp)
            game = self.games[i]
            distances.append(SimilarityResult(
                match_id=fp.match_id,
                champion=fp.champion,
                win=fp.win,
                distance=round(dist, 4),
                fingerprint=fp
            ))

        distances.sort(key=lambda x: x.distance)
        return distances[:k]

    def _fingerprint_distance(self, a: GameFingerprint, b: GameFingerprint) -> float:
        """Euclidean distance in 5-D fingerprint space."""
        return math.sqrt(
            (a.aggression - b.aggression) ** 2 +
            (a.efficiency - b.efficiency) ** 2 +
            (a.objective_race - b.objective_race) ** 2 +
            (a.collapse - b.collapse) ** 2 +
            (a.vision - b.vision) ** 2
        )

    def matched_comparison(
        self,
        signal_fn,  # callable(game) -> bool
        k: int = 30,
        min_games: int = 5
    ) -> Optional["MatchedComparisonResult"]:
        """
        For a given signal (pass a lambda), find games WITH and WITHOUT the signal,
        then find the K most similar matches for each group.
        Returns win rate delta with statistical confidence.

        Usage:
            result = engine.matched_comparison(
                signal_fn=lambda g: g.get('deaths', 0) >= 8,
                k=30
            )
        """
        games_with = []
        games_without = []

        for i, game in enumerate(self.games):
            if signal_fn(game):
                games_with.append(i)
            else:
                games_without.append(i)

        if len(games_with) < min_games:
            return None

        if len(games_without) < min_games:
            return None

        def _build_match_set(target_idx: int, pool: List[int], k: int) -> List[int]:
            """Find K most similar games from pool to target."""
            target_fp = self.fingerprints[target_idx]
            scored = []
            for idx in pool:
                if idx == target_idx:
                    continue
                dist = self._fingerprint_distance(target_fp, self.fingerprints[idx])
                scored.append((dist, idx))
            scored.sort(key=lambda x: x[0])
            return [idx for _, idx in scored[:k]]

        # Build matched sets for the signal-present games
        matched_with = set()
        for idx in games_with:
            match_set = _build_match_set(idx, games_without, k)
            matched_with.update(match_set)

        # Build matched sets for signal-absent games (to get baseline)
        matched_without = set()
        sample_without = games_without[:min(len(games_without), len(games_with) * 2)]
        for idx in sample_without:
            match_set = _build_match_set(idx, games_with, k)
            matched_without.update(match_set)

        # Compute win rates
        wins_with = sum(1 for i in games_with if self.games[i].get("win", False))
        wr_with = wins_with / len(games_with)

        wins_matched_with = sum(1 for i in matched_with if self.games[i].get("win", False))
        wr_matched = wins_matched_with / len(matched_with) if matched_with else 0.5

        wins_without = sum(1 for i in games_without if self.games[i].get("win", False))
        wr_without = wins_without / len(games_without)

        delta = wr_with - wr_matched  # signal's impact controlling for fingerprint

        return MatchedComparisonResult(
            signal_games=len(games_with),
            no_signal_games=len(games_without),
            matched_games=len(matched_with),
            win_rate_with_signal=round(wr_with, 3),
            win_rate_matched_comparison=round(wr_matched, 3),
            win_rate_without_signal=round(wr_without, 3),
            delta=round(delta, 3),
            confidence=self._compute_comparison_confidence(
                len(games_with), len(matched_with), delta
            )
        )

    def _compute_comparison_confidence(
        self,
        n_signal: int,
        n_matched: int,
        delta: float
    ) -> float:
        """
        Compute confidence for a matched comparison result.
        Higher confidence when: large N, matched set is large, delta is large.
        """
        n_factor = min(n_signal / 30, 1.0) * 0.4
        matched_factor = min(n_matched / 60, 1.0) * 0.3
        delta_factor = min(abs(delta) / 0.20, 1.0) * 0.3
        return round(n_factor + matched_factor + delta_factor, 3)

    def cluster(self, min_k: int = 3, max_k: int = 12) -> "ClusteringOutput":
        """
        Cluster all games by fingerprint similarity using K-Means.
        Automatically selects the best K using silhouette score.
        Labels each cluster by its dominant behavioral characteristic.
        Pure Python implementation — no sklearn needed.
        """
        if not self.fingerprints:
            raise ValueError("Must call analyze() before cluster()")

        player_id = self.player_id
        n_games = len(self.fingerprints)

        # Build feature vectors
        features = []
        for fp in self.fingerprints:
            features.append([
                fp.aggression,
                fp.efficiency,
                fp.objective_race,
                fp.collapse,
                fp.vision
            ])

        # Find best K using silhouette score
        best_score = -1
        best_k = min_k
        scores_by_k = {}

        for k in range(min_k, min(max_k + 1, n_games)):
            labels = self._kmeans_predict(features, k, n_iter=30)
            if len(set(labels)) < 2:
                scores_by_k[k] = 0.0
                continue
            score = self._silhouette_score(features, labels)
            scores_by_k[k] = score
            if score > best_score:
                best_score = score
                best_k = k

        # Final clustering with best K
        final_labels = self._kmeans_predict(features, best_k, n_iter=50)

        # Build cluster results
        cluster_map: Dict[int, List[int]] = {}
        for i, label in enumerate(final_labels):
            if label not in cluster_map:
                cluster_map[label] = []
            cluster_map[label].append(i)

        clusters = []
        for cid in sorted(cluster_map.keys()):
            indices = cluster_map[cid]
            fps = [self.fingerprints[i] for i in indices]

            wins = sum(1 for i in indices if self.fingerprints[i].win)
            losses = len(indices) - wins
            wr = wins / len(indices) if indices else 0.0

            # Dominant champion
            champ_counts: Dict[str, int] = {}
            for fp in fps:
                champ_counts[fp.champion] = champ_counts.get(fp.champion, 0) + 1
            dom_champ = max(champ_counts, key=champ_counts.get) if champ_counts else "Unknown"
            dom_pct = champ_counts[dom_champ] / len(fps) if fps else 0

            # Mean fingerprint (centroid)
            mean_agg = statistics.mean(f.aggression for f in fps) if fps else 0.5
            mean_eff = statistics.mean(f.efficiency for f in fps) if fps else 0.5
            mean_obj = statistics.mean(f.objective_race for f in fps) if fps else 0.5
            mean_col = statistics.mean(f.collapse for f in fps) if fps else 0.5
            mean_vis = statistics.mean(f.vision for f in fps) if fps else 0.5

            mean_fp = GameFingerprint(
                match_id="centroid",
                champion=dom_champ,
                win=wr > 0.5,
                duration_min=statistics.mean(f.duration_min for f in fps) if fps else 0,
                aggression=round(mean_agg, 4),
                efficiency=round(mean_eff, 4),
                objective_race=round(mean_obj, 4),
                collapse=round(mean_col, 4),
                vision=round(mean_vis, 4),
                raw_kills_pm=0, raw_assists_pm=0, raw_damage_pm=0,
                raw_cs_pm=0, raw_cs_10=0, raw_turret_kills=0,
                raw_lks=0, raw_gold_lead_15=0, raw_vision_pm=0, raw_wards_placed=0
            )

            label = self._label_cluster(mean_fp, wr)

            clusters.append(ClusterResult(
                cluster_id=cid,
                games=fps,
                win_rate=round(wr, 3),
                total_games=len(indices),
                wins=wins,
                losses=losses,
                dominant_champion=dom_champ,
                dominant_champion_pct=round(dom_pct, 3),
                mean_fingerprint=mean_fp,
                behavioral_label=label
            ))

        # Sort clusters by win rate descending
        clusters.sort(key=lambda c: c.win_rate, reverse=True)
        for i, c in enumerate(clusters):
            c.cluster_id = i

        return ClusteringOutput(
            player_id=player_id,
            timestamp=datetime.now(),
            total_games=n_games,
            clusters=clusters,
            k_best=best_k,
            silhouette_score=round(best_score, 4),
            fingerprints=self.fingerprints
        )

    def _kmeans_predict(self, vectors: List[List[float]], k: int, n_iter: int) -> List[int]:
        """Pure-python K-Means clustering. Returns cluster labels."""
        if k >= len(vectors):
            return [0] * len(vectors)

        # Initialize centroids randomly from data points
        centroids = [list(vectors[i]) for i in random.sample(range(len(vectors)), k)]

        for _ in range(n_iter):
            # Assign each vector to nearest centroid
            labels = []
            for v in vectors:
                dists = [self._euclidean(v, c) for c in centroids]
                labels.append(dists.index(min(dists)))

            # Recompute centroids
            new_centroids = []
            for cluster_id in range(k):
                members = [vectors[i] for i in range(len(vectors)) if labels[i] == cluster_id]
                if members:
                    new_centroids.append([
                        statistics.mean(m[d] for m in members)
                        for d in range(len(vectors[0]))
                    ])
                else:
                    # Empty cluster — re-init with random point
                    new_centroids.append(list(random.choice(vectors)))
            centroids = new_centroids

        return labels

    def _euclidean(self, a: List[float], b: List[float]) -> float:
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(len(a))))

    def _silhouette_score(self, vectors: List[List[float]], labels: List[int]) -> float:
        """
        Compute average silhouette score for clustering.
        silhouette(i) = (b(i) - a(i)) / max(a(i), b(i))
        where a(i) = avg intra-cluster distance, b(i) = nearest other cluster distance
        """
        n = len(vectors)
        if n < 2:
            return 0.0

        unique_labels = set(labels)
        if len(unique_labels) < 2:
            return 0.0

        # Precompute distances
        dists = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                d = self._euclidean(vectors[i], vectors[j])
                dists[i][j] = d
                dists[j][i] = d

        total = 0.0
        for i in range(n):
            label_i = labels[i]

            # a(i): avg distance to others in same cluster
            same_cluster = [j for j in range(n) if j != i and labels[j] == label_i]
            if same_cluster:
                a_i = statistics.mean(dists[i][j] for j in same_cluster)
            else:
                a_i = 0.0

            # b(i): min avg distance to each other cluster
            b_i = float('inf')
            for lab in unique_labels:
                if lab == label_i:
                    continue
                other_cluster = [j for j in range(n) if labels[j] == lab]
                if other_cluster:
                    avg_d = statistics.mean(dists[i][j] for j in other_cluster)
                    if avg_d < b_i:
                        b_i = avg_d

            if b_i == float('inf'):
                b_i = 0.0

            if max(a_i, b_i) > 0:
                total += (b_i - a_i) / max(a_i, b_i)

        return total / n

    def _label_cluster(self, centroid: "GameFingerprint", win_rate: float) -> str:
        """
        Generate a human-readable behavioral label for a cluster
        based on its centroid fingerprint and win rate.
        """
        parts = []

        # Aggression label
        if centroid.aggression >= 0.65:
            parts.append("High Aggression")
        elif centroid.aggression <= 0.35:
            parts.append("Low Aggression")
        else:
            parts.append("Moderate Aggression")

        # Efficiency label
        if centroid.efficiency >= 0.65:
            parts.append("High Efficiency")
        elif centroid.efficiency <= 0.35:
            parts.append("Low Efficiency")
        else:
            parts.append("Balanced Economy")

        # Objective race
        if centroid.objective_race >= 0.60:
            parts.append("Pusher")
        elif centroid.objective_race <= 0.35:
            parts.append("Farmer")
        else:
            parts.append("Mixed Pressure")

        # Collapse
        if centroid.collapse >= 0.60:
            parts.append("Snowball")
        elif centroid.collapse <= 0.35:
            parts.append("Scaling")
        else:
            parts.append("Stable")

        # Vision
        if centroid.vision >= 0.60:
            parts.append("Vision Heavy")
        elif centroid.vision <= 0.35:
            parts.append("Vision Light")
        else:
            parts.append("Normal Vision")

        base = " / ".join(parts)

        if win_rate >= 0.60:
            return f"{base} — WINNING TYPE"
        elif win_rate <= 0.35:
            return f"{base} — LOSING TYPE"
        else:
            return f"{base} — NEUTRAL TYPE"

    def _compute_confidence(self, games: List[Dict]) -> float:
        if not games:
            return 0.0
        return min(len(games) / 50, 0.95)


@dataclass
class MatchedComparisonResult:
    """Result of a matched comparison query."""
    signal_games: int
    no_signal_games: int
    matched_games: int
    win_rate_with_signal: float
    win_rate_matched_comparison: float
    win_rate_without_signal: float
    delta: float
    confidence: float


@dataclass
class SimilarityOutput:
    """Full output of the Similarity Engine."""
    player_id: str
    timestamp: datetime
    total_games: int
    fingerprints: List[GameFingerprint]
    distributions: Dict[str, List[float]]
    confidence: float


@dataclass
class ClusterResult:
    """Result of clustering all games by fingerprint similarity."""
    cluster_id: int
    games: List["GameFingerprint"]
    win_rate: float
    total_games: int
    wins: int
    losses: int
    dominant_champion: str
    dominant_champion_pct: float
    mean_fingerprint: "GameFingerprint"
    behavioral_label: str


@dataclass
class ClusteringOutput:
    """Full output of cluster analysis."""
    player_id: str
    timestamp: datetime
    total_games: int
    clusters: List[ClusterResult]
    k_best: int
    silhouette_score: float
    fingerprints: List[GameFingerprint]


# ────────────────────────────────────────────────────────────────
# Convenience runner
# ────────────────────────────────────────────────────────────────

def run_similarity_engine(
    cache_path: str = r"C:\Facecheck\facecheck_cache.json"
) -> Optional[SimilarityOutput]:
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    games = cache.get("games", [])
    if not games:
        return None

    engine = SimilarityEngine()
    return engine.analyze(games)


# ────────────────────────────────────────────────────────────────
# CLI test
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Load cache
    try:
        with open(r"C:\Facecheck\facecheck_cache.json", 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No data available.")
        exit()

    games = cache.get("games", [])
    if not games:
        print("No games in cache.")
        exit()

    # Run fingerprint analysis
    engine = SimilarityEngine()
    output = engine.analyze(games)

    print(f"Similarity Engine — {output.total_games} games fingerprinted")
    print()

    print("Fingerprint distributions (percentile rank ranges):")
    print(f"  aggression:      {min(f.aggression for f in output.fingerprints):.2f} – {max(f.aggression for f in output.fingerprints):.2f}")
    print(f"  efficiency:      {min(f.efficiency for f in output.fingerprints):.2f} – {max(f.efficiency for f in output.fingerprints):.2f}")
    print(f"  objective_race: {min(f.objective_race for f in output.fingerprints):.2f} – {max(f.objective_race for f in output.fingerprints):.2f}")
    print(f"  collapse:        {min(f.collapse for f in output.fingerprints):.2f} – {max(f.collapse for f in output.fingerprints):.2f}")
    print(f"  vision:          {min(f.vision for f in output.fingerprints):.2f} – {max(f.vision for f in output.fingerprints):.2f}")
    print()

    # Run clustering
    print("Running cluster analysis...")
    clustering = engine.cluster(min_k=3, max_k=12)
    if not clustering:
        print("Clustering failed.")
        exit()

    print(f"Best K={clustering.k_best} (silhouette={clustering.silhouette_score:.3f})")
    print()
    print(f"{'='*60}")
    for c in clustering.clusters:
        print(f"Cluster {c.cluster_id}: {c.behavioral_label}")
        print(f"  {c.total_games} games | WR: {c.win_rate:.1%} | {c.wins}W/{c.losses}L")
        print(f"  Dominant: {c.dominant_champion} ({c.dominant_champion_pct:.0%})")
        fp = c.mean_fingerprint
        print(f"  Centroid: agg={fp.aggression:.2f} eff={fp.efficiency:.2f} "
              f"obj={fp.objective_race:.2f} col={fp.collapse:.2f} vis={fp.vision:.2f}")
        print()