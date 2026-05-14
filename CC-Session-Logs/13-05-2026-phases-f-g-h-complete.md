# Session Log: 13-05-2026 — Phases F, G, H Complete

## Quick Reference (for AI scanning)
**Confidence keywords:** observation mining, mine_observations, compare_players, print_compare, print_scout, fetch_player_games, resolve_riot_id, synthesize_games_with_engines, distribution deltas, observation deltas, per-player caching, scout mode, compare mode
**Projects:** FaceCheck
**Outcome:** Completed Phases F, G, and H. Observation mining replaces mechanism grouping in worst/best/pool. Scout mode analyzes any player through the synthesis pipeline. Compare mode shows delta verdicts between two players.

---

## Phase F: Aggregate Synthesis — Observation Mining

### Decisions Made

**Observation mining replaces mechanism grouping**
- `worst_patterns()` and `best_patterns()` now group by `obs_type` instead of `v.mechanism` (opaque cluster strings)
- `mine_observations(pairs, result_filter)` groups observations across verdicts, filters baselines (score < 0.5), returns sorted pattern dicts
- Display shows human-readable labels: "Death Cluster: 28 losses (30.8%)" instead of "Cluster Loss Mechanism: 30.8% of losses"

**Pool observation enrichment**
- `print_pool()` now runs synthesis when `player_id` is available and shows per-champion observation patterns
- For champs below 50% WR: shows dominant loss observation ("Viego: loss pattern: counter-pick position (13/39 losses)")
- For champs at 50%+ WR: shows dominant win observation ("Mordekaiser: win pattern: champion repetition (17/18 wins)")

**Baseline filtering in mine_observations**
- Observations with score < 0.5 are filtered out of aggregate mining — these are fallback observations ("Viego loss", "Warwick win") that fire on every game and aren't actionable patterns

### Files Modified
- **facecheck_aggregate.py** — Added `mine_observations()`, `worst_patterns()` now returns `observation_patterns` instead of `mechanisms`, `best_patterns()` same, `print_worst()` and `print_best()` render observation patterns, `print_pool()` shows champion observations, `print_pool()` now accepts `player_id` parameter
- **facecheck_game.py** — `print_pool` call updated to pass `player_id`

---

## Phase G: Scout Mode — Arbitrary Player Analysis

### Decisions Made

**Scout uses the full synthesis pipeline**
- `face scout Name#Tag [count]` fetches any player's ranked games WITH timeline data (not the lightweight approach the old scout used)
- Games are built via `build_match_record()` — same rich records as self-analysis
- Full 7-engine pipeline runs on scouted player's games
- Per-player caching: scout games in `scout_cache/{safe_id}_cache.json`, engine outputs per-player via `_cache_path(player_id)`, player models per-player via `_player_model_path(player_id)`

**No pro data infrastructure built preemptively**
- Scout handles any Riot ID, including pro players — `face scout Faker#KR1` just works
- Pro baselines, tournament data, pro shortcuts are Phase H+ concerns that need actual data
- G3 discipline: don't build untested code paths for data that doesn't exist

### Files Modified
- **facecheck_data.py** — Added `resolve_riot_id(riot_id)` and `fetch_player_games(riot_id, count=20)` with per-player caching
- **facecheck_player_model.py** — Added `_player_model_path(player_id)` for per-player model files; `get_or_create_player_model()` uses it
- **facecheck_special.py** — Added `print_scout()` with champion pool, observation patterns, worst/best builds, bottom line, recent games table
- **facecheck_game.py** — Added `scout` mode to dispatcher, usage string updated

---

## Phase H: Personal vs Player Comparison — Delta Verdicts

### Decisions Made

**Compare against any player, not just "pro"**
- `face compare Name#Tag [count]` runs both players through synthesis and shows deltas
- Works today with any scouted player — no pro data needed
- Extends naturally to pro baselines when data arrives — same `compare_players()` function, different reference data source

**Observation deltas: rate comparison**
- For each obs_type, compares the percentage of games where it fires between both players
- Sorted by absolute delta (biggest differences first)
- Shows: "Death cluster: You 30% vs Them 12% (+18pp)"

**Distribution deltas: median comparison**
- Compares engine distribution medians for deaths_per_game, damage_per_min, kill_participation, total_heal, damage_mitigated, cc_time, wards_killed
- Shows: "DPM: You 480 vs Them 720 (+50%)"

**synthesize_games_with_engines() returns both pairs and engines**
- `compare_players()` needs engine outputs for distribution comparison
- Added `synthesize_games_with_engines()` that returns `(pairs, engines)` tuple
- `synthesize_games()` still works as before (returns pairs only)

### Files Modified
- **facecheck_aggregate.py** — Added `_compute_observation_deltas()`, `_compute_distribution_deltas()`, `compare_players()`, `synthesize_games_with_engines()`
- **facecheck_special.py** — Added `print_compare()` with pattern deltas, distribution deltas, bottom line
- **facecheck_game.py** — Added `compare` mode to dispatcher, usage string updated

---

## Verification
- `py_compile` on all modified files after each step — all pass
- `python facecheck_game.py worst` — observation patterns render correctly, items/champions still work
- `python facecheck_game.py best` — same
- `python facecheck_game.py pool` — champion observations render after stats table
- `python facecheck_game.py scout` (no args) — usage message works
- `python facecheck_game.py compare` (no args) — usage message works
- `python facecheck_game.py` — usage string includes scout and compare

---

## Key Learnings

### Observation mining is additive, not exclusive
Same insight as Phase E's pipeline: the old mechanism grouping was exclusive (one mechanism per game). The new observation mining is additive — all observations are collected, grouped by type, and counted. A game with both death cluster AND inefficient combat now contributes to both pattern counts.

### Baseline observations must be filtered in aggregate
Individual game verdicts include baseline observations (score 0.4, "Viego loss") as fallbacks so every game has at least one observation. But in aggregate, these baseline observations dominate the counts (95%+ of games) and aren't actionable. Filtering by score >= 0.5 removes them from pattern mining.

### Per-player caching avoids collisions
Self-analysis uses `facecheck_cache.json` and `facecheck_brain.json`. Scout uses `scout_cache/{safe_id}_cache.json` and `scout_cache/{safe_id}_brain.json`. Engine cache already supported per-player paths via `_cache_path(player_id)`. No data collision between self and scout analysis.

### Compare works with any two players, not just self vs pro
The key architectural insight: `compare_players()` takes two sets of `(pairs, engines)` and computes deltas. The reference player can be anyone — a friend, a rival, a pro. When pro baseline data arrives, the same function compares against aggregated pro distributions with zero refactoring.

---

**END OF SESSION LOG**