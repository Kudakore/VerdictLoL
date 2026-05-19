# Session Log: 19-05-2026 — Synthesis Decomposition

## Quick Reference (for AI scanning)
**Confidence keywords:** synthesis decomposition, CombatProfile, DurabilityProfile, VisionProfile, SummarySection, Summary, Divergence, typed profiles, _get_profile_features removed, explanation removed, Verdict.explanation removed, structured output channels
**Projects:** Verdict
**Outcome:** Synthesis decomposition complete. Verdict output channels now use structured dataclasses. Summary returns Summary with List[SummarySection] instead of joined string. Divergences return List[Divergence] instead of List[str]. Dead _build_explanation_multi() removed. Verdict.explanation field removed. CombatProfile/DurabilityProfile/VisionProfile typed dataclasses replace untyped dicts.

---

## What Was Done

### Typed Profile Dataclasses
- Added `CombatProfile` (deaths, damage, dpm, kp_pct, kills, assists) with `from_signatures()` class method and game-field fallbacks
- Added `DurabilityProfile` (total_heal, damage_mitigated, cc_time, damage_shielded) with `from_signatures()` class method
- Added `VisionProfile` (vision_score, vision_per_min, wards_killed, wards_placed, control_wards) with `from_signatures()` class method
- Added `_extract_features()` module-level helper to replace `_get_profile_features()` internally
- All 12 observation producers now accept `combat_profile`, `durability_profile`, `vision_profile` keyword arguments (backward compatible)
- All channel methods (`_build_evidence_multi`, `_derive_lessons_multi`, `_build_summary_multi`, `_identify_divergences_multi`) accept typed profiles as parameters
- `analyze_single_game()` builds profiles once and passes them to all channel methods

### Structured Output Types
- Added `SummarySection` (domain, statement, data) — one domain's contribution to the verdict summary
- Added `Summary` (sections: List[SummarySection]) with `to_text()` for backward-compatible string rendering
- Added `Divergence` (divergence_type, statement, data, win) — structured divergence replacing string
- `_build_summary_multi()` now returns `Summary` instead of `str`; each `parts.append(...)` converted to `sections.append(SummarySection(...))`
- `_identify_divergences_multi()` now returns `List[Divergence]` instead of `List[str]`; each string converted to Divergence with type, data dict, and win flag

### Dead Code Removal
- Removed `_build_explanation_multi()` method entirely (66 lines) — never rendered by any consumer
- Removed `Verdict.explanation` field from the Verdict dataclass
- Removed the `explanation=` argument from the Verdict constructor in `analyze_single_game()`

### Display Updates
- `render_verdict()` in verdict_display.py now provides: `summary` (text via to_text()), `summary_sections` (structured), `divergences` (strings), `divergence_details` (structured)
- `print_synthesis_block()` uses `hasattr()` guards for backward compatibility with both old and new types

### Documentation
- Updated `docs/engine-contracts.md` with typed profile contracts section
- Updated `CLAUDE.md` refactoring plan

## Files Modified
- `verdict_synthesis.py` — Added CombatProfile, DurabilityProfile, VisionProfile, SummarySection, Summary, Divergence, _extract_features. Removed _build_explanation_multi and Verdict.explanation. Converted _build_summary_multi to return Summary. Converted _identify_divergences_multi to return List[Divergence]. Wired typed profiles through all channel methods and observation producers.
- `verdict_display.py` — Updated render_verdict and print_synthesis_block for new Summary/Divergence types
- `docs/engine-contracts.md` — Added typed profile contracts section
- `CLAUDE.md` — Updated refactoring plan with synthesis decomposition DONE

## Architecture Priority Status
1. ✅ Game dataclass — DONE
2. ✅ Producer calibration — DONE
3. ✅ Engine contract clarification — DONE
4. ✅ Synthesis decomposition — DONE
5. 🔲 Config to .env — needed before FastAPI
6. 🔲 Test suite — insurance for future changes

**END OF SESSION LOG**