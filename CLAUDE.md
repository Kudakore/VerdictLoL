# Verdict

A personal League of Legends diagnostic system. Analyzes match history to surface causal relationships between early-game decisions and outcomes.

## Architecture

### Engine Pipeline
All 7 domain-pure extraction engines accept `(games, player_id)` as explicit parameters. The old `cache_path`-only signature still works as a backward-compatible fallback via `run_engine_from_cache()` in `verdict_engine_base.py`.

**Engine call interface contract:**
- `run_death_engine(games=None, player_id=None, cache_path=None)` — if `games` and `player_id` provided, runs directly; otherwise loads from `cache_path`
- Same pattern for all 7: economy, combat, durability, vision, objective, draft
- `run_similarity_engine(games=None, cache_path=None)` — similar but no `player_id` (SimilarityEngine doesn't need it)
- `run_engine_from_cache(engine_class, cache_path, games, player_id)` — shared convenience wrapper in base

### Module Structure (current)
- `verdict_game_model.py` — Game dataclass and nested models (Game, EnemyPlayer, PlayerStats, TeamObjectives, JunglePathing) with from_dict/to_dict for JSON cache round-tripping
- `verdict_game.py` — CLI entry point and mode dispatch only
- `verdict_service.py` — AnalysisService class (single pipeline entry point, caches engines/pairs/similarity)
- `verdict_display.py` — Core display functions (fmt_num, fmt_k, render_game + print_full_game, render_compact_game + print_compact_game, render_verdict + print_synthesis_block, render_team_breakdown + print_team_breakdown, ROLE_LABELS, enemy_role_label)
- `verdict_aggregate.py` — synthesize_games, synthesize_games_with_engines, mine_observations, compare_players, worst_patterns, best_patterns, analyze_worst + print_worst, analyze_best + print_best, analyze_pool + print_pool (synthesis-native aggregate analysis + display, observation mining, player comparison)
- `verdict_special.py` — Specialized modes with data/display split (analyze_matchups + print_matchups, analyze_guide + print_guide, analyze_bans + print_bans, analyze_heatmap + print_heatmap, analyze_pathing + print_pathing, analyze_scout + print_scout, analyze_compare + print_compare, analyze_recent + print_recent, analyze_enemy + print_enemy, get_select_games + get_select_page + run_select)
- `verdict_champ_intel.py` — Champion intelligence (render_matchup_context + print_matchup_context, analyze_counter_command + print_counter_command, analyze_intel_profile + print_intel_profile)
- `verdict_engine_base.py` — Distribution, EngineNode, EngineSignature, EngineOutput (with to_dict/from_dict), run_engine_from_cache
- `verdict_engine_*.py` — 7 domain-pure extraction engines
- `verdict_engine_cache.py` — Engine output caching (save/load MultiEngineOutput JSON, keyed on player_id + games hash, 24h auto-invalidation)
- `verdict_synthesis.py` — SynthesisLayer, Verdict, MultiEngineOutput (with to_dict/from_dict), Evidence, Lesson, Observation
- `verdict_similarity.py` — SimilarityEngine, GameFingerprint, ClusterResult, PatternResult
- `verdict_player_model.py` — PlayerModel, PlayerBaseline, PatternMemory (per-player caching via _player_model_path)
- `verdict_win_impact.py` — WinImpactEngine, WinImpactSignature, CompensatingFactor (batch statistical impact analysis across games. Wired into AnalysisService via `analyze_win_impact()` and CLI via `verdict impact`)
- `verdict_config.py` — Config auto-setup (creates config.py from template if missing, validates placeholders)
- `verdict_paths.py` — Centralized path configuration (DATA_DIR env var, all paths derived from it)
- `verdict_data.py` — Riot API, cache management, match record building, get_ranked_games, fetch_player_games (scout), resolve_riot_id, get_current_game (Spectator v5), resolve_puuid_to_riot_id
- `verdict_item.py` — Item and component lookup, champion build analysis (analyze_champ_builds + print_champ_builds)
- `verdict_champ_intel.py` — Champion intelligence (matchup context, counter recommendations, intel profiles)
- `league_vault.py` — Champion data vault builder from Data Dragon

### AnalysisService (verdict_service.py)
Single pipeline entry point. Runs the synthesis pipeline once per player, caches all intermediate results (engines, player_model, similarity_output, cluster_membership, pairs, synthesis). Analysis methods reuse cached data:
- **Pipeline-dependent** (call `_ensure_pipeline()` first): `analyze_worst`, `analyze_best`, `analyze_pool`, `analyze_scout`, `analyze_enemy`, `analyze_game`
- **Non-pipeline** (work from raw games): `analyze_matchups`, `analyze_bans`, `analyze_heatmap`, `analyze_pathing`, `analyze_recent`, `analyze_win_impact`
- **Two-player** (needs two service instances): `analyze_compare`
- `render_game` accepts optional `service` parameter to use cached pipeline data instead of re-running

### Command Reference (current)
All commands available via `verdict`, `v`, or `face` (legacy alias):
- `verdict fetch [N] [--force]` — Fetch and cache ranked games from Riot API
- `verdict clean` — Remove duplicate games from cache
- `verdict update` — Sync LeagueVault to latest patch
- `verdict recent [solo|flex] [N]` — Pure match history table (no synthesis)
- `verdict lastgame` — Deep dive on most recent game (synthesis)
- `verdict game N` — Deep dive on specific game (synthesis)
- `verdict games [N]` — Last N games with compact synthesis
- `verdict select [champ]` — Browse games, pick one for deep dive
- `verdict worst [champ]` — What is costing you games (observation mining)
- `verdict best [champ]` — What is working (observation mining)
- `verdict pool [N]` — Champion pool health report
- `verdict matchups [champ]` — Matchup breakdown
- `verdict bans` — Counter pool tracker
- `verdict heatmap` — Time-of-game death analysis
- `verdict pathing` — Jungle camp efficiency
- `verdict scout Name#Tag [N]` — Analyze any player via synthesis
- `verdict compare Name#Tag [N]` — Delta comparison vs another player
- `verdict counter [champ]` — How to beat a champion
- `verdict intel [champ]` — Full champion intel profile
- `verdict enemy` — Live enemy scout via Spectator API (auto-waits for game)
- `verdict guide` — Playing guide
- `verdict item [name]` — Item stats and build path
- `verdict components [name]` — Full component tree
- `verdict champ [name]` — Champion base stats
- `verdict builds [champ]` — Item winrate analysis
- `verdict impact` — Win impact analysis (which patterns hurt/help win rate most)

### Verdict System
- Synthesis is the ONLY path for `verdict lastgame`, `verdict game N`, `verdict worst`, `verdict best`
- `render_game` delegates to `synthesize_games_with_engines` for pipeline — no inline pipeline duplication
- `analyze_worst` and `analyze_best` return structured dicts; `print_worst`/`print_best` are thin wrappers
- `analyze_pool` uses _winrate + per-champion observation enrichment when synthesis is available
- `analyze_recent` is pure match history — no synthesis, no engines, just cache data
- Every `print_` function has an `analyze_*`/`render_*` data twin that returns structured dicts (data/display split complete)
- `AnalysisService` provides cached pipeline access for all analysis modes (Phase 3)

### Key Design Decisions
- **Game dataclass** — all game data uses typed `Game` objects (not dicts). Fields like `game.champion`, `game.kp_pct`, `game.my_team.dragon_kills` give IDE autocompletion and prevent silent bugs from typos. `from_dict`/`to_dict` handle JSON cache round-tripping. `kp_pct` is computed from `(kills + assists) / team_kills`.
- Personal baselines (P10/P25/P75/P90) — not generic thresholds
- Distribution-based assessment in synthesis — "top_25" not hardcoded numbers
- Matched comparison for counterfactual reasoning — not simple correlation
- Superadditivity detection — only 2/31 signal pairs compound harm
- Centroid delta for mechanism naming — not hardcoded thresholds
- Observation pipeline — 12 independent producers return Observation or None; severity-scaled scores (0.45–0.95); counter_pick split into observe_countered/observe_blind_pick; baselines removed; new producers for economy, vision, objectives, kill participation; win_impact side signals removed
- Observation mining — aggregate functions mine observations across verdicts (group by obs_type, filter baselines); replaces opaque mechanism grouping with structured, labeled patterns
- AnalysisService — single pipeline entry point; runs engines once per player, caches all intermediate results; analysis methods reuse cached data instead of re-running pipeline
- Data/display split — every `print_` function has an `analyze_*`/`render_*` twin that returns structured dicts; print versions are thin wrappers
- Scout mode — arbitrary player analysis via same synthesis pipeline; per-player caching for engine outputs, player models, and game data
- Compare mode — delta comparison between two players' patterns and distributions; observation rate deltas and distribution median deltas
- Enemy mode — live enemy scout via Spectator v5 API; auto-detects same-position enemy, shows role versatility, loss observations, and stat comparison

### Refactoring Plan (complete through Phase 3 + Game dataclass)
- **Phase 0** (DONE): Rename facecheck_* → verdict_*
- **Phase 1** (DONE): Path configuration (verdict_paths.py, DATA_DIR env var)
- **Phase 2** (DONE): Data/display split (19 analyze_/render_ + print_ pairs)
- **Phase 3** (DONE): AnalysisService (verdict_service.py, render_game pipeline deduplication)
- **Game dataclass** (DONE): Typed Game/EnemyPlayer/PlayerStats/TeamObjectives/JunglePathing dataclasses replace untyped dicts. Fixes 8 bugs where wrong field names silently returned 0.
- **Producer calibration** (DONE): Counter-pick split into countered/blind_pick (was 97.8% fire rate). Baseline fallbacks removed. 4 new producers: economy, vision, objectives, kill participation. Severity scaling on death cluster/chain. Side signals removed from win_impact.
- **Engine contracts** (DONE): Documented in docs/engine-contracts.md. 11/40+ distribution keys consumed, 10/30+ signature types consumed, objective engine unused by synthesis, draft has no distributions.
- **Synthesis decomposition** (DONE): Verdict output channels now use structured dataclasses. CombatProfile/DurabilityProfile/VisionProfile replace untyped dicts from `_get_profile_features()`. Summary returns `Summary` with `List[SummarySection]` (domain, statement, data) instead of joined string. Divergences return `List[Divergence]` (divergence_type, statement, data, win) instead of `List[str]`. Dead `_build_explanation_multi()` removed. `Verdict.explanation` field removed.
- **Phase 4** (PLANNED): FastAPI Server
- **Phase 5** (PLANNED): Tauri Shell
- **Phase 6** (PLANNED): Frontend Views

### Deleted Modules
- `facecheck_analysis.py`, `facecheck_diagnosis.py`, `facecheck_recent.py`, `facecheck_scout.py` — dead code removed in Phase C
- `league_scout.py` — fully superseded by `verdict_data.fetch_player_games`
- `league_stats.py` — champion build analysis extracted to `verdict_item.analyze_champ_builds`; rest superseded by `verdict_data`
- `league_players.py` — enemy analysis recomposable from `verdict_data` functions
- `league_build.py` — fully superseded by `verdict_item.py` and `verdict_champ_intel.py`
- `facecheck_win_impact.py` — renamed to `verdict_win_impact.py`, now wired into AnalysisService and CLI

### Discipline
- G1: py_compile after every edit
- G2: Manual compression after every session
- G3: Never build anything crappy
- G4: Always ask "can this be better?"

### Known Issues
- config.py is gitignored (contains API key) — auto-created from config_template.py on first run via verdict_config.py
- Counter-pick observation fires at 97.8% of losses — likely too broad, needs producer tuning (next: producer calibration)
- `verdict enemy` not tested in a live game — Spectator API behavior during champ select is untested
- `verdict enemy` not tested in a live game — Spectator API behavior during champ select is untested