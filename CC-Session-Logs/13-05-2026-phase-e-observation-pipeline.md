# Session Log: 13-05-2026 — Phase E: Compositional Verdict Rendering

## Quick Reference (for AI scanning)
**Confidence keywords:** observation pipeline, observe_death_cluster, observe_inefficient_combat, compositional verdict, first-match-wins replaced, secondary observations, Observation dataclass, _build_fractal_statement removed
**Projects:** FaceCheck
**Outcome:** Completed Phase E. Replaced the if/elif cascade in `_build_fractal_statement()` with a compositional Observation pipeline. Each verdict branch is now an independent producer that returns an Observation or None. All producers run, top observations compose the verdict.

---

## Decisions Made

### Observation pipeline replaces if/elif cascade
**Decision:** Each branch of the old `_build_fractal_statement()` elif chain is now an `observe_*` method that returns an `Observation` object or `None`. All 7 producers run independently. Observations are sorted by score, and the top one becomes the verdict statement. Secondary observations render as bullet points.

**Why:** The old cascade was first-match-wins. A game with both a death cluster AND inefficient combat only got the death cluster statement. With the pipeline, all patterns are detected and the richest ones surface to the user.

**Result:** Games with multiple patterns now show "Also detected: inefficient combat (high), counter-pick position (medium)" below the primary verdict statement.

### Observation dataclass design
**Decision:** `Observation(obs_type, label, statement, score, data, priority)`. Score (0.0-1.0) determines ordering. Priority ("critical", "high", "medium", "low") is for display.

**Scoring philosophy:** Structural patterns (death_cluster: 0.9, death_chain: 0.85) score highest because they describe causal mechanisms. Distribution-band observations (efficient_combat: 0.7, inefficient_combat: 0.75) score lower because they describe statistical positions, not causation. Baseline observations (win_baseline: 0.4, loss_baseline: 0.4) are the lowest-priority fallbacks.

### Secondary observation rendering
**Decision:** "Also detected:" bullet points showing up to 3 secondary observations with their priority level.

**Why:** Shows the user that multiple patterns were detected without overwhelming the primary verdict. The primary statement still anchors the narrative.

### Death cluster/chain observation producer
**Decision:** `observe_death_cluster` handles both death_cluster and death_chain when both are present (higher-priority sub-case). `observe_death_chain` only fires when there's a chain but no cluster (to avoid duplication).

**Why:** When a game has both a cluster and a chain, the cluster producer emits the combined statement "Death chain: N deaths in M minutes with accelerating frequency." This is richer than either alone. The standalone chain producer only fires for chains without clusters.

---

## Files Modified

- **facecheck_synthesis.py** — Added `Observation` dataclass. Added 7 `observe_*` methods to `SynthesisLayer`. Added `OBSERVATION_PRODUCERS` class variable and `collect_observations()` pipeline method. Added `observations` field to `Verdict` dataclass. Updated `analyze_single_game()` to use `collect_observations()` instead of `_build_fractal_statement()`. Deleted `_build_fractal_statement()` (113 lines removed, replaced by 7 producers + pipeline).
- **facecheck_display.py** — Added `Observation` import. Added secondary observations rendering in `print_synthesis_block()`.
- **CLAUDE.md** — Added Observation to module structure, marked Phase E done, added observation pipeline to key design decisions.

---

## Verification

- `py_compile` on facecheck_synthesis.py and facecheck_display.py — all pass
- `python facecheck_game.py last` — verdict shows primary observation + "Also detected:" secondary observations
- `python facecheck_game.py worst` — aggregate patterns still work
- `python facecheck_game.py best` — aggregate patterns still work
- Confirmed: a game with both death cluster AND inefficient combat now shows BOTH patterns instead of only the death cluster

---

## Key Learnings

### The pipeline is additive, not exclusive
The key insight: the old elif cascade was exclusive (first match wins). The new pipeline is additive (all matches fire). This means a game can now show "death cluster + inefficient combat + counter-pick position" instead of just "death cluster." The verdict is richer and more honest.

### Observation producers need deduplication awareness
`observe_death_cluster` and `observe_death_chain` both check for death-related structural patterns. Without coordination, both would fire for the same game and produce redundant statements. Solution: `observe_death_cluster` handles the combined case (chain + cluster), and `observe_death_chain` skips when a cluster exists. This deduplication pattern should be applied to future producers that may overlap.

### Score-based composition is simpler than priority ordering
The old cascade used a fixed priority order hardcoded in the elif structure. The new system uses a floating-point score that naturally sorts observations. Adding a new producer is as simple as defining a method and adding it to OBSERVATION_PRODUCERS — no need to figure out where it fits in an elif chain.

---

**END OF SESSION LOG