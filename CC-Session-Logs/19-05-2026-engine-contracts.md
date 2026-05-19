# Session Log: 19-05-2026 — Engine Contract Clarification

## Quick Reference (for AI scanning)
**Confidence keywords:** engine contracts, synthesis decomposition prerequisite, distribution keys, signature types, profile features, _get_profile_features, objective engine unused, draft engine no distributions, untyped dict access
**Projects:** Verdict
**Outcome:** Engine contracts documented in docs/engine-contracts.md. Key finding: synthesis consumes only 11/40+ distribution keys and 10/30+ signature types. Objective engine distributions never read by synthesis.

---

## What Was Done

### Producer Calibration (completed this session)
- Split `observe_counter_pick` into `observe_countered` (relation=="counter", score 0.55) and `observe_blind_pick` (relation=="blind", score 0.45)
- Fixed bug: counter-pick statement used `game.champion` instead of enemy champion name
- Removed `win_baseline`/`loss_baseline` fallback observations (fired on nearly every game at score 0.4)
- Added 4 new observation producers: `observe_economy_pattern`, `observe_vision_control`, `observe_objective_control`, `observe_kill_participation`
- Added severity scaling to `observe_death_cluster` (0.7 + severity bonus) and `observe_death_chain` (0.7 + severity bonus)
- Removed `blue_side`/`red_side` signals from `verdict_win_impact.py` (fired on 100% of games)
- Updated action maps in `verdict_service.py` and `verdict_special.py`
- Total: 12 observation producers (up from 7)

### Engine Contract Clarification
- Cataloged all 7 engines' complete output contracts
- Mapped every synthesis access point to specific engine outputs
- Documented in `docs/engine-contracts.md`

### Key Findings from Contract Analysis

**Only 11 of 40+ distribution keys are consumed by synthesis:**
- Death: `deaths_per_game` (7 access points)
- Economy: `cs_at_10` (3), `cs_at_15` (1)
- Combat: `damage_per_min` (6), `total_damage` (2), `kill_participation` (3)
- Durability: `total_heal` (3), `damage_mitigated` (3), `cc_time` (3)
- Vision: `vision_score` (1), `wards_killed` (3)
- Objective: 0 (synthesis reads from `game.my_team` directly)
- Draft: 0 (no distributions)

**Only 10 of 30+ signature types are consumed by synthesis:**
- `death_cluster`, `death_chain`, `death_phase_concentration`, `combat_profile`, `durability_profile`, `vision_profile`, `champion_repetition`, `counter_pick_relation`, `pick_position`, `side_assignment`

**20+ signature types produced but never consumed:**
- Including: `survival_profile`, `cs_checkpoint_sequence`, `gold_checkpoint`, `multi_kill_event`, `killing_spree_event`, `bounty_acquired`, `spell_cast_profile`, `enemy_vision_contrast`, all objective signatures, `role_assignment`, `draft_sequence`

**Three access patterns in synthesis:**
1. Distribution band assessment: `engines.X.distributions.get("key")` → `_assess_against_distribution()` → band string
2. Profile feature extraction: `_get_profile_features(signatures, "type")` → untyped dict (FRAGILE — main friction point for decomposition)
3. Direct game field access: `game.cs_10`, `game.my_team.dragon_kills`, etc.

### Implications for Synthesis Decomposition
- `_get_profile_features()` returns an untyped dict — this is the main thing to formalize
- Objective engine's distributions could be removed from synthesis consumption or consumed properly
- Many engine signatures are produced but never used — could be trimmed or could be consumed by new features
- Each output channel (observations, evidence, lessons, summary, explanation, divergence) has documented dependencies on specific engine outputs

## Architecture Priority Status
1. ✅ Game dataclass — DONE
2. ✅ Producer calibration — DONE
3. ✅ Engine contract clarification — DONE
4. 🔲 Synthesis decomposition — next (3-5 days, breaks analyze_single_game into composable producers)
5. 🔲 Config to .env — needed before FastAPI
6. 🔲 Test suite — insurance for future changes

## Stopping Points for Synthesis Decomposition
- After formalizing `_get_profile_features` return types (typed dataclass per profile)
- After extracting each output channel (observations, evidence, lessons, summary, explanation, divergence) into its own method/class
- After each channel has documented input dependencies per the contract doc
- The contract doc at `docs/engine-contracts.md` is the reference for all input dependencies

## Files Modified This Session
- `verdict_synthesis.py` — Counter-pick split, baselines removed, 4 new producers, severity scaling, OBSERVATION_PRODUCERS list
- `verdict_win_impact.py` — Side signals removed
- `verdict_service.py` — Action map updated with new obs_type keys
- `verdict_special.py` — Action map updated with new obs_type keys
- `CLAUDE.md` — Producer calibration and engine contracts marked as DONE
- `docs/engine-contracts.md` — NEW: complete contract documentation

**END OF SESSION LOG**