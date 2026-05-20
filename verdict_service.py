"""
Verdict Analysis Service — Single pipeline entry point.

Runs the synthesis pipeline once, caches all intermediate results,
and provides analysis methods that reuse the cached data.
"""

from collections import defaultdict
from verdict_aggregate import (
    synthesize_games, synthesize_games_with_engines,
    mine_observations, worst_patterns, best_patterns,
    _winrate, _split_by_result, _analyze_basic_worst, _analyze_basic_best,
)
from verdict_engine_cache import load_engine_outputs, save_engine_outputs
from verdict_engine_death import run_death_engine
from verdict_engine_economy import run_economy_engine
from verdict_engine_combat import run_combat_engine
from verdict_engine_durability import run_durability_engine
from verdict_engine_vision import run_vision_engine
from verdict_engine_objective import run_objective_engine
from verdict_engine_draft import run_draft_engine
from verdict_synthesis import SynthesisLayer, MultiEngineOutput
from verdict_similarity import SimilarityEngine
from verdict_player_model import get_or_create_player_model
from verdict_game_model import Game


class AnalysisService:
    """Single pipeline entry point. Runs engines once, caches results."""

    def __init__(self, player_id: str, games: list):
        self.player_id = player_id
        self.games = games
        self._engines = None           # MultiEngineOutput
        self._player_model = None      # PlayerModel
        self._similarity_output = None  # SimilarityEngine result
        self._cluster_membership = {}  # {match_id: cluster_id}
        self._pairs = None             # List[(game, Verdict)]
        self._synthesis = None         # SynthesisLayer
        self._pipeline_ready = False

    @property
    def pipeline_ready(self):
        """Whether the analysis pipeline has been initialized."""
        return self._pipeline_ready

    @property
    def pairs(self):
        """Cached (game, verdict) pairs. Runs pipeline if needed."""
        self._ensure_pipeline()
        return self._pairs

    @property
    def engines(self):
        """Cached MultiEngineOutput. Runs pipeline if needed."""
        self._ensure_pipeline()
        return self._engines

    def _ensure_pipeline(self):
        """Run the full synthesis pipeline if not already done. Caches all results."""
        if self._pipeline_ready:
            return

        if len(self.games) < 3:
            self._pairs = []
            self._engines = None
            self._pipeline_ready = True
            return

        # 1. Load or compute engine outputs
        engines = load_engine_outputs(self.player_id, self.games)
        if engines is None:
            engines = MultiEngineOutput(
                death=run_death_engine(games=self.games, player_id=self.player_id),
                economy=run_economy_engine(games=self.games, player_id=self.player_id),
                combat=run_combat_engine(games=self.games, player_id=self.player_id),
                durability=run_durability_engine(games=self.games, player_id=self.player_id),
                vision=run_vision_engine(games=self.games, player_id=self.player_id),
                objective=run_objective_engine(games=self.games, player_id=self.player_id),
                draft=run_draft_engine(games=self.games, player_id=self.player_id),
            )
            save_engine_outputs(self.player_id, self.games, engines)
        self._engines = engines

        # 2. Build player model + similarity (only if engines produced data)
        if engines.death:
            self._player_model = get_or_create_player_model(self.player_id, self.games)

            self._similarity_output = None
            self._cluster_membership = {}
            try:
                sim_engine = SimilarityEngine()
                sim_result = sim_engine.analyze(self.games)
                if sim_result and sim_result.fingerprints:
                    self._similarity_output = sim_result
                    cluster_result = sim_engine.cluster()
                    if cluster_result and cluster_result.clusters:
                        for cluster in cluster_result.clusters:
                            for fp in cluster.games:
                                self._cluster_membership[fp.match_id] = cluster.cluster_id
                    try:
                        sim_engine.discover_patterns()
                    except Exception:
                        pass
            except Exception:
                pass

            # 3. Create synthesis layer and produce verdicts
            self._synthesis = SynthesisLayer(
                self._player_model,
                similarity_output=self._similarity_output,
                cluster_membership=self._cluster_membership,
            )
            self._pairs = []
            for game in self.games:
                verdict = self._synthesis.analyze_single_game(game, self._engines)
                if verdict:
                    self._pairs.append((game, verdict))
        else:
            self._pairs = []

        self._pipeline_ready = True

    # ── Pipeline-dependent analysis methods ──────────────────────────

    def analyze_worst(self, champion=None):
        """Worst patterns. Returns same dict structure as aggregate.analyze_worst."""
        self._ensure_pipeline()
        wins, losses = _split_by_result(self.games)
        wr = _winrate(self.games) or 0

        header = {
            "label": f"VERDICT WORST — {champion}" if champion else "VERDICT WORST",
            "total_games": len(self.games),
            "wins": len(wins),
            "losses": len(losses),
            "wr": wr,
        }

        if self._pairs:
            data = worst_patterns(self._pairs)
            if champion:
                filtered_pairs = [(g, v) for g, v in self._pairs if g.champion == champion]
                if filtered_pairs:
                    data = worst_patterns(filtered_pairs)
        else:
            data = _analyze_basic_worst(self.games, champion, wins, losses, wr)

        return {"header": header, **data}

    def analyze_best(self, champion=None):
        """Best patterns. Returns same dict structure as aggregate.analyze_best."""
        self._ensure_pipeline()
        wins, losses = _split_by_result(self.games)
        wr = _winrate(self.games) or 0

        header = {
            "label": f"VERDICT BEST — {champion}" if champion else "VERDICT BEST",
            "total_games": len(self.games),
            "wins": len(wins),
            "losses": len(losses),
            "wr": wr,
        }

        if self._pairs:
            data = best_patterns(self._pairs)
            if champion:
                filtered_pairs = [(g, v) for g, v in self._pairs if g.champion == champion]
                if filtered_pairs:
                    data = best_patterns(filtered_pairs)
        else:
            data = _analyze_basic_best(self.games, champion, wins, losses, wr)

        return {"header": header, **data}

    def analyze_pool(self, min_games=3):
        """Champion pool health. Uses cached pairs for enrichment. Same dict structure as aggregate.analyze_pool."""
        self._ensure_pipeline()

        champ_games = defaultdict(list)
        for g in self.games:
            champ_games[g.champion].append(g)

        rows = []
        for champ, cg in champ_games.items():
            if len(cg) < min_games:
                continue
            wr = _winrate(cg)
            if wr is None:
                continue
            recent = cg[:5]
            recent_wr = _winrate(recent)
            if recent_wr is None or len(recent) < 3:
                trend = "→"
            elif recent_wr >= wr + 10:
                trend = "↑"
            elif recent_wr <= wr - 10:
                trend = "↓"
            else:
                trend = "→"

            if len(cg) < 3:
                verdict = "UNSTABLE"
            elif wr >= 58 and trend != "↓":
                verdict = "PLAY"
            elif wr >= 58 and trend == "↓":
                verdict = "PLAY (DECLINING)"
            elif wr >= 50 and len(cg) >= 10:
                verdict = "SOLID"
            elif wr >= 50 and len(cg) < 10:
                verdict = "PLAY (LOW SAMPLE)"
            elif wr < 50 and trend == "↑" and len(cg) >= 10:
                verdict = "CONDITIONAL"
            elif wr < 50 and trend == "↑" and len(cg) < 10:
                verdict = "UNSTABLE"
            elif wr < 45:
                verdict = "AVOID"
            else:
                verdict = "INCONSISTENT"

            rows.append({
                "champion": champ, "games": len(cg), "wr": wr,
                "trend": trend, "verdict": verdict,
            })

        rows.sort(key=lambda x: x["wr"], reverse=True)

        wins_total = sum(1 for g in self.games if g.win)
        header = {
            "total_games": len(self.games),
            "wins": wins_total,
            "losses": len(self.games) - wins_total,
            "wr": round(wins_total / len(self.games) * 100, 1) if self.games else 0,
            "min_games": min_games,
        }

        # Per-champion observation enrichment using cached pairs
        champion_patterns = []
        if self._pairs:
            champ_verdicts = defaultdict(list)
            for g, v in self._pairs:
                champ_verdicts[g.champion].append((g, v))

            for row in rows:
                champ = row["champion"]
                if champ not in champ_verdicts or len(champ_verdicts[champ]) < 3:
                    continue
                cv = champ_verdicts[champ]
                losses = [(g, v) for g, v in cv if not g.win]
                wins_list = [(g, v) for g, v in cv if g.win]

                if row["wr"] < 50 and losses:
                    obs_counts = defaultdict(int)
                    for _, v in losses:
                        if v.observations:
                            obs_counts[v.observations[0].label] += 1
                    if obs_counts:
                        top_obs = max(obs_counts.items(), key=lambda x: x[1])
                        champion_patterns.append({
                            "champion": champ,
                            "type": "loss",
                            "pattern": top_obs[0],
                            "count": top_obs[1],
                            "total": len(losses),
                        })
                elif row["wr"] >= 50 and wins_list:
                    obs_counts = defaultdict(int)
                    for _, v in wins_list:
                        if v.observations:
                            obs_counts[v.observations[0].label] += 1
                    if obs_counts:
                        top_obs = max(obs_counts.items(), key=lambda x: x[1])
                        champion_patterns.append({
                            "champion": champ,
                            "type": "win",
                            "pattern": top_obs[0],
                            "count": top_obs[1],
                            "total": len(wins_list),
                        })

        play_these = [r for r in rows if r["verdict"] == "PLAY"]
        conditional_these = [r for r in rows if r["verdict"] == "CONDITIONAL"]
        avoid_these = [r for r in rows if r["verdict"] == "AVOID"]

        return {
            "header": header,
            "rows": rows,
            "champion_patterns": champion_patterns,
            "play_pick": play_these[0] if play_these else None,
            "conditional_pick": conditional_these[0] if conditional_these else None,
            "avoid_pick": avoid_these[-1] if avoid_these else None,
        }

    def analyze_scout(self, riot_id):
        """Scout analysis. Returns same dict structure as special.analyze_scout."""
        self._ensure_pipeline()
        wins, losses = _split_by_result(self.games)
        wr = _winrate(self.games) or 0

        header = {
            "riot_id": riot_id,
            "total_games": len(self.games), "wins": len(wins), "losses": len(losses), "wr": wr,
        }

        # Champion pool
        champ_games = defaultdict(list)
        for g in self.games:
            champ_games[g.champion].append(g)
        champ_rows = []
        for champ, cg in champ_games.items():
            cwr = _winrate(cg)
            if cwr is not None:
                champ_rows.append({"champion": champ, "games": len(cg), "wr": cwr})
        champ_rows.sort(key=lambda x: (-x["games"], -x["wr"]))

        # Synthesis-powered analysis (use cached pairs)
        loss_patterns = []
        win_patterns = []
        worst_items = []
        best_items = []
        bottom_line = None
        has_synthesis = False

        if self._pairs:
            has_synthesis = True
            loss_patterns = mine_observations(self._pairs, result_filter="loss")
            win_patterns = mine_observations(self._pairs, result_filter="win")
            worst_data = worst_patterns(self._pairs)
            best_data = best_patterns(self._pairs)
            worst_items = worst_data["items"][:3]
            best_items = best_data["items"][:3]
            bottom_line = worst_data.get("bottom_line")

        # Recent games
        recent = []
        for i, g in enumerate(self.games[:10], 1):
            recent.append({
                "num": i, "champion": g.champion,
                "result": "WIN" if g.win else "LOSS",
                "kda": f"{g.kills}/{g.deaths}/{g.assists}",
                "cs_per_min": g.cs_per_min,
                "dpm": g.damage_per_min,
            })

        return {
            "header": header, "champion_pool": champ_rows[:8],
            "has_synthesis": has_synthesis,
            "loss_patterns": loss_patterns[:4], "win_patterns": win_patterns[:4],
            "worst_items": worst_items, "best_items": best_items,
            "bottom_line": bottom_line,
            "recent_games": recent,
        }

    def analyze_game(self, game, game_number=None, historical_games=None, cache=None):
        """Single-game verdict. Returns same dict structure as render_game."""
        from verdict_display import render_game
        # Delegate to render_game, passing the service for cached pipeline
        return render_game(game, game_number=game_number,
                          historical_games=historical_games or self.games,
                          player_id=self.player_id, cache=cache,
                          service=self)

    # ── Two-player analysis methods ──────────────────────────────────

    def analyze_enemy(self, riot_id, champion=None, role=None, my_games=None, my_player_id=None):
        """Enemy scout. Uses cached pipeline for enemy analysis.
        Optionally creates a second service for my_games comparison."""
        self._ensure_pipeline()

        if not self.games or len(self.games) < 3:
            return {"has_data": False, "riot_id": riot_id}

        total = len(self.games)
        wins = sum(1 for g in self.games if g.win)
        wr = _winrate(self.games)

        # Role versatility
        role_counts = defaultdict(lambda: {"w": 0, "l": 0})
        for g in self.games:
            r = g.role
            if g.win:
                role_counts[r]["w"] += 1
            else:
                role_counts[r]["l"] += 1

        roles_sorted = sorted(role_counts.items(), key=lambda x: x[1]["w"] + x[1]["l"], reverse=True)
        primary_role, primary_stats = roles_sorted[0]
        primary_total = primary_stats["w"] + primary_stats["l"]

        if primary_total / total >= 0.7:
            role_line = f"{primary_role} main ({primary_total}/{total} games)"
        else:
            role_parts = [f"{r} {s['w']}/{s['w']+s['l']}" for r, s in roles_sorted[:3]]
            role_line = ", ".join(role_parts)

        best_role = max(roles_sorted, key=lambda x: x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1))
        best_total = best_role[1]["w"] + best_role[1]["l"]
        best_wr = best_role[1]["w"] / best_total * 100 if best_total else 0

        role_wr_line = ""
        if best_role[0] != primary_role or best_total != primary_total:
            role_wr_line = f" | Best: {best_role[0]} {best_wr:.0f}% WR"
        elif len(roles_sorted) > 1:
            role_wr_line = f" | Overall: {wr}% WR"

        # Synthesis — use cached pairs
        weaknesses = []
        bottom_line = None
        if self._pairs:
            loss_pairs = [(g, v) for g, v in self._pairs if not g.win]
            loss_obs = mine_observations(loss_pairs, result_filter="loss") if loss_pairs else []
            for obs in loss_obs[:3]:
                weaknesses.append({
                    "label": obs.get("label", obs.get("obs_type", "?")).title(),
                    "pct": obs.get("pct", 0),
                    "count": obs.get("count", 0),
                    "total_losses": len(loss_pairs),
                    "statement": obs.get("statement", ""),
                })
            if loss_obs:
                top = loss_obs[0]
                obs_type = top.get("obs_type", "")
                label = top.get("label", obs_type).title()
                pct = top.get("pct", 0)
                action_map = {
                    "death_cluster": f"Punish early deaths — {pct:.0f}% of their losses cluster.",
                    "early_deaths": f"Invade early — {pct:.0f}% of losses have pre-15min deaths.",
                    "inefficient_combat": f"They deal low damage per death — force fights, they lose trades.",
                    "poor_farming": f"Out-farm them — they fall behind in gold by {pct:.0f}% of losses.",
                    "countered": f"They were counter-picked and lost — draft advantage matters.",
                    "blind_pick": f"They drafted blind and lost — early pick disadvantage.",
                    "cs_deficit_early": f"They fall behind in CS early — pressure their lane.",
                    "gold_deficit": f"They fall behind in gold by 15 — snowball your lead.",
                    "vision_deficit": f"They ward sparingly — gank freely, they lack vision control.",
                    "low_vision": f"They ward sparingly — gank freely, they lack vision control.",
                    "no_dragon": f"They neglect objectives — take dragons/herald early.",
                    "no_turret_pressure": f"They don't push towers — pressure their lanes.",
                    "low_kp": f"They avoid fights — force skirmishes, they don't show up.",
                }
                advice = action_map.get(obs_type, f"Exploit their {label.lower()} pattern ({pct:.0f}% of losses).")
                bottom_line = {"weakness": label, "pct": pct, "advice": advice}

        # Stats comparison
        my_edge = None
        if my_games and len(my_games) >= 5:
            my_deaths = sum(g.deaths for g in my_games) / len(my_games)
            their_deaths = sum(g.deaths for g in self.games) / len(self.games)
            my_cs = sum(g.cs_per_min for g in my_games) / len(my_games)
            their_cs = sum(g.cs_per_min for g in self.games) / len(self.games)
            my_dpm = sum(g.damage_per_min for g in my_games) / len(my_games)
            their_dpm = sum(g.damage_per_min for g in self.games) / len(self.games)
            my_edge = {
                "deaths": {"me": my_deaths, "them": their_deaths},
                "cs_per_min": {"me": my_cs, "them": their_cs},
                "dpm": {"me": my_dpm, "them": their_dpm},
            }

        return {
            "has_data": True,
            "header": {
                "riot_id": riot_id, "champion": champion, "role": role,
                "total": total, "wins": wins, "wr": wr,
                "role_line": role_line, "role_wr_line": role_wr_line,
            },
            "weaknesses": weaknesses,
            "my_edge": my_edge,
            "bottom_line": bottom_line,
        }

    @staticmethod
    def analyze_compare(my_service, ref_service, my_id, ref_id):
        """Compare two players. Both services must have _ensure_pipeline() called."""
        from verdict_aggregate import compare_players
        my_service._ensure_pipeline()
        ref_service._ensure_pipeline()

        if not my_service._pairs or not ref_service._pairs:
            return {"observation_deltas": [], "distribution_deltas": [],
                    "bottom_line": "Not enough data for comparison."}

        return compare_players(
            my_service._pairs, ref_service._pairs,
            my_service._engines, ref_service._engines,
            my_service.games, ref_service.games,
        )

    # ── Non-pipeline analysis methods (delegate to standalone) ───────

    def analyze_matchups(self, champion=None):
        """Matchup breakdown. Delegates to special.analyze_matchups."""
        from verdict_special import analyze_matchups
        return analyze_matchups(self.games, champion)

    def analyze_bans(self):
        """Ban recommendations. Delegates to special.analyze_bans."""
        from verdict_special import analyze_bans
        return analyze_bans(self.games)

    def analyze_heatmap(self):
        """Death heatmap. Delegates to special.analyze_heatmap."""
        from verdict_special import analyze_heatmap
        return analyze_heatmap(self.games)

    def analyze_pathing(self):
        """Jungle pathing. Delegates to special.analyze_pathing."""
        from verdict_special import analyze_pathing
        return analyze_pathing(self.games)

    def analyze_recent(self, queue_filter=None, count=20, cache=None):
        """Match history. Delegates to special.analyze_recent."""
        from verdict_special import analyze_recent
        return analyze_recent(self.games, queue_filter=queue_filter, count=count, cache=cache)

    def analyze_win_impact(self):
        """Win impact analysis — how much each problem signal hurts or helps win rate.
        Runs WinImpactEngine on cached games. Returns WinImpactOutput."""
        from verdict_win_impact import WinImpactEngine
        engine = WinImpactEngine(self.player_id)
        return engine.analyze(self.games)