# FaceCheck

A personal League of Legends diagnostic system. Analyzes match history to surface causal relationships between early-game decisions and outcomes.

## Architecture

### Engine Pipeline
All 7 domain-pure extraction engines accept `(games, player_id)` as explicit parameters. The old `cache_path`-only signature still works as a backward-compatible fallback via `run_engine_from_cache()` in `facecheck_engine_base.py`.

**Engine call interface contract:**
- `run_death_engine(games=None, player_id=None, cache_path=None)` — if `games` and `player_id` provided, runs directly; otherwise loads from `cache_path`
- Same pattern for all 7: economy, combat, durability, vision, objective, draft
- `run_similarity_engine(games=None, cache_path=None)` — similar but no `player_id` (SimilarityEngine doesn't need it)
- `run_engine_from_cache(engine_class, cache_path, games, player_id)` — shared convenience wrapper in base

### Module Structure (current)
- `facecheck_game.py` — CLI entry point and mode dispatch only
- `facecheck_display.py` — Core display functions (fmt_num, fmt_k, print_full_game, print_compact_game, print_synthesis_block, print_team_breakdown, ROLE_LABELS, enemy_role_label)
- `facecheck_aggregate.py` — synthesize_games, synthesize_games_with_engines, mine_observations, compare_players, worst_patterns, best_patterns, print_worst, print_best, print_pool (synthesis-native aggregate analysis + display, observation mining, player comparison)
- `facecheck_special.py` — Specialized modes (run_select, print_matchups, print_guide, print_bans, print_heatmap, print_pathing, print_scout, print_compare)
- `facecheck_engine_base.py` — Distribution, EngineNode, EngineSignature, EngineOutput (with to_dict/from_dict), run_engine_from_cache
- `facecheck_engine_*.py` — 7 domain-pure extraction engines
- `facecheck_engine_cache.py` — Engine output caching (save/load MultiEngineOutput JSON, keyed on player_id + games hash, 24h auto-invalidation)
- `facecheck_synthesis.py` — SynthesisLayer, Verdict, MultiEngineOutput (with to_dict/from_dict), Evidence, Lesson, Observation
- `facecheck_similarity.py` — SimilarityEngine, GameFingerprint, ClusterResult, PatternResult
- `facecheck_player_model.py` — PlayerModel, PlayerBaseline, PatternMemory (per-player caching via _player_model_path)
- `facecheck_data.py` — Riot API, cache management, match record building, get_ranked_games, fetch_player_games (scout), resolve_riot_id

### Verdict System
- Synthesis is the ONLY path for `face lastgame`, `face game N`, `face worst`, `face best`
- `print_worst` and `print_best` use synthesize_games + mine_observations + worst_patterns/best_patterns via facecheck_aggregate.py
- `print_pool` uses _winrate + per-champion observation enrichment when synthesis is available
- Legacy `diagnose_game()` and `generate_verdict()` are dead code — defined but never called
- `face lastgame` fallback shows raw stats (KDA, CS, gold, damage) — no templates, no legacy diagnosis
- `facecheck_game.py` no longer imports from facecheck_analysis.py (deleted)
- Dead modules removed: facecheck_analysis.py, facecheck_diagnosis.py, facecheck_recent.py, facecheck_scout.py
- Scout mode (`face scout Name#Tag`) uses the full synthesis pipeline on any player's games — same engines, observations, verdicts as self-analysis
- Scout games cached per-player in scout_cache/{safe_id}_cache.json — no collision with self-analysis cache
- PlayerModel per-player via _player_model_path() — scout players get their own brain file

### Key Design Decisions
- Personal baselines (P10/P25/P75/P90) — not generic thresholds
- Distribution-based assessment in synthesis — "top_25" not hardcoded numbers
- Matched comparison for counterfactual reasoning — not simple correlation
- Superadditivity detection — only 2/31 signal pairs compound harm
- Centroid delta for mechanism naming — not hardcoded thresholds
- Observation pipeline — each verdict branch is an independent producer that returns Observation or None; all producers run, top observations compose the verdict statement
- Observation mining — aggregate functions mine observations across verdicts (group by obs_type, filter baselines); replaces opaque mechanism grouping with structured, labeled patterns
- Scout mode — arbitrary player analysis via same synthesis pipeline; per-player caching for engine outputs, player models, and game data
- Compare mode — delta comparison between two players' patterns and distributions; observation rate deltas and distribution median deltas

### Refactoring Plan (8 phases)
- **Phase A** (DONE): Engine call interface refactored
- **Phase B** (DONE): Engine output caching
- **Phase C** (DONE): Kill legacy for aggregates
- **Phase D** (DONE): Split facecheck_game.py into modules
- **Phase E** (DONE): Compositional verdict rendering
- **Phase F** (DONE): Aggregate synthesis for worst/best/pool
- **Phase G** (DONE): Scout mode — arbitrary player analysis via synthesis pipeline
- **Phase H** (DONE): Personal vs player comparison — delta verdicts

### Discipline
- G1: py_compile after every edit
- G2: Manual compression after every session
- G3: Never build anything crappy
- G4: Always ask "can this be better?"