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
- `verdict_game.py` — CLI entry point and mode dispatch only
- `verdict_display.py` — Core display functions (fmt_num, fmt_k, print_full_game, print_compact_game, print_synthesis_block, print_team_breakdown, ROLE_LABELS, enemy_role_label)
- `verdict_aggregate.py` — synthesize_games, synthesize_games_with_engines, mine_observations, compare_players, worst_patterns, best_patterns, print_worst, print_best, print_pool (synthesis-native aggregate analysis + display, observation mining, player comparison)
- `verdict_special.py` — Specialized modes (run_select, print_matchups, print_guide, print_bans, print_heatmap, print_pathing, print_scout, print_compare, print_recent, print_enemy)
- `verdict_engine_base.py` — Distribution, EngineNode, EngineSignature, EngineOutput (with to_dict/from_dict), run_engine_from_cache
- `verdict_engine_*.py` — 7 domain-pure extraction engines
- `verdict_engine_cache.py` — Engine output caching (save/load MultiEngineOutput JSON, keyed on player_id + games hash, 24h auto-invalidation)
- `verdict_synthesis.py` — SynthesisLayer, Verdict, MultiEngineOutput (with to_dict/from_dict), Evidence, Lesson, Observation
- `verdict_similarity.py` — SimilarityEngine, GameFingerprint, ClusterResult, PatternResult
- `verdict_player_model.py` — PlayerModel, PlayerBaseline, PatternMemory (per-player caching via _player_model_path)
- `verdict_config.py` — Config auto-setup (creates config.py from template if missing, validates placeholders)
- `verdict_data.py` — Riot API, cache management, match record building, get_ranked_games, fetch_player_games (scout), resolve_riot_id, get_current_game (Spectator v5), resolve_puuid_to_riot_id
- `verdict_item.py` — Item and component lookup (standalone, not in synthesis pipeline)
- `league_stats.py` — Match history stats, builds analysis (standalone)
- `league_build.py` — Item and champion stat lookup (standalone)
- `league_players.py` — Player/enemy analysis from games (standalone)
- `league_scout.py` — Basic player scout (standalone, superseded by verdict scout)
- `league_vault.py` — Champion data vault builder from Data Dragon

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

### Verdict System
- Synthesis is the ONLY path for `verdict lastgame`, `verdict game N`, `verdict worst`, `verdict best`
- `print_worst` and `print_best` use synthesize_games + mine_observations + worst_patterns/best_patterns via verdict_aggregate.py
- `print_pool` uses _winrate + per-champion observation enrichment when synthesis is available
- `print_recent` is pure match history — no synthesis, no engines, just cache data
- Legacy `diagnose_game()` and `generate_verdict()` are dead code — defined but never called
- `verdict lastgame` fallback shows raw stats (KDA, CS, gold, damage) — no templates, no legacy diagnosis
- `verdict_game.py` no longer imports from verdict_analysis.py (deleted)
- Dead modules removed: verdict_analysis.py, verdict_diagnosis.py, verdict_recent.py, verdict_scout.py
- Scout mode (`verdict scout Name#Tag`) uses the full synthesis pipeline on any player's games — same engines, observations, verdicts as self-analysis
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
- Recent mode — pure match history with queue filtering, streaks, champion breakdown; no synthesis for speed
- Enemy mode — live enemy scout via Spectator v5 API; auto-detects same-position enemy, shows role versatility, loss observations, and stat comparison; auto-waits for game if not detected

### Refactoring Plan (8 phases — ALL COMPLETE)
- **Phase A** (DONE): Engine call interface refactored
- **Phase B** (DONE): Engine output caching
- **Phase C** (DONE): Kill legacy for aggregates
- **Phase D** (DONE): Split verdict_game.py into modules
- **Phase E** (DONE): Compositional verdict rendering
- **Phase F** (DONE): Aggregate synthesis for worst/best/pool
- **Phase G** (DONE): Scout mode — arbitrary player analysis via synthesis pipeline
- **Phase H** (DONE): Personal vs player comparison — delta verdicts

### Discipline
- G1: py_compile after every edit
- G2: Manual compression after every session
- G3: Never build anything crappy
- G4: Always ask "can this be better?"

### Known Issues
- config.py is gitignored (contains API key) — auto-created from config_template.py on first run via verdict_config.py
- Counter-pick observation fires at 97.8% of losses — likely too broad, needs producer tuning
- `verdict enemy` not tested in a live game — Spectator API behavior during champ select is untested