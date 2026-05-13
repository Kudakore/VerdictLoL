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
- `facecheck_game.py` — CLI entry point, diagnostics, display functions (to be split in Phase D)
- `facecheck_engine_base.py` — Distribution, EngineNode, EngineSignature, EngineOutput (with to_dict/from_dict), run_engine_from_cache
- `facecheck_engine_*.py` — 7 domain-pure extraction engines
- `facecheck_engine_cache.py` — Engine output caching (save/load MultiEngineOutput JSON, keyed on player_id + games hash, 24h auto-invalidation)
- `facecheck_synthesis.py` — SynthesisLayer, Verdict, MultiEngineOutput (with to_dict/from_dict), Evidence, Lesson
- `facecheck_similarity.py` — SimilarityEngine, GameFingerprint, ClusterResult, PatternResult
- `facecheck_aggregate.py` — synthesize_games, worst_patterns, best_patterns (synthesis-native aggregate analysis)
- `facecheck_player_model.py` — PlayerModel, PlayerBaseline, PatternMemory
- `facecheck_data.py` — Riot API, cache management, match record building
- `facecheck_analysis.py` — Legacy analysis system (dead code — no active callers)

### Verdict System
- Synthesis is the ONLY path for `face lastgame`, `face game N`, `face worst`, `face best`
- `print_worst` and `print_best` use synthesize_games + worst_patterns/best_patterns via facecheck_aggregate.py
- `print_pool` uses _winrate from facecheck_aggregate.py (pure stats, no legacy)
- Legacy `diagnose_game()` and `generate_verdict()` are dead code — defined but never called
- `face lastgame` fallback shows raw stats (KDA, CS, gold, damage) — no templates, no legacy diagnosis
- `facecheck_game.py` no longer imports from facecheck_analysis.py

### Key Design Decisions
- Personal baselines (P10/P25/P75/P90) — not generic thresholds
- Distribution-based assessment in synthesis — "top_25" not hardcoded numbers
- Matched comparison for counterfactual reasoning — not simple correlation
- Superadditivity detection — only 2/31 signal pairs compound harm
- Centroid delta for mechanism naming — not hardcoded thresholds

### Refactoring Plan (8 phases)
- **Phase A** (DONE): Engine call interface refactored
- **Phase B** (DONE): Engine output caching
- **Phase C** (DONE): Kill legacy for aggregates
- **Phase D**: Split facecheck_game.py into modules
- **Phase E**: Compositional verdict rendering
- **Phase F**: Aggregate synthesis for worst/best/pool
- **Phase G**: Pro data adapter
- **Phase H**: Personal vs pro comparison

### Discipline
- G1: py_compile after every edit
- G2: Manual compression after every session
- G3: Never build anything crappy
- G4: Always ask "can this be better?"