# Engine Contracts — Verdict Architecture Reference

## Purpose
Defines what each engine provides and what synthesis consumes. This is the prerequisite for synthesis decomposition (priority #4).

## Engine Output Structure (verdict_engine_base.py)
All engines return `EngineOutput` with:
- `engine_name: str`
- `distributions: Dict[str, Distribution]` — personal baseline distributions
- `signatures: List[EngineSignature]` — per-game structural patterns
- `nodes: List[EngineNode]` — temporal event data
- `correlation_space: Dict[str, List[float]]` — per-game metric vectors
- `confidence: float`
- `source_games: List[str]`
- `raw_metrics: Dict`

## Distribution Keys

### Death Engine
| Key | Source | Consumed By |
|---|---|---|
| `deaths_per_game` | `g.deaths` | synthesis (7 access points: observations, evidence, lessons, summary, explanation, divergence) |
| `death_timing` | `g.death_minutes` (flattened) | NOT consumed by synthesis |
| `early_deaths` | `g.early_deaths` | NOT consumed by synthesis |
| `longest_living` | `g.longest_living` | NOT consumed by synthesis |
| `time_spent_dead` | `g.time_spent_dead` | NOT produced by engine |

### Economy Engine
| Key | Source | Consumed By |
|---|---|---|
| `cs_at_10` | `g.cs_10` | synthesis (3: observe_economy_pattern, explanation) |
| `cs_at_15` | `g.cs_15` | synthesis (1: observe_economy_pattern) |
| `cs_per_min` | `g.cs_per_min` | NOT consumed by synthesis |
| `gold_lead_15` | `g.gold_lead_15` | NOT consumed by synthesis (read directly from game) |
| `gold_15` | `g.gold_15` | NOT consumed by synthesis |
| `gold_per_min` | `g.gold_per_min` | NOT consumed by synthesis |
| `first_clear_timing` | `jungle_pathing.first_clear_min` | NOT consumed by synthesis |

### Combat Engine
| Key | Source | Consumed By |
|---|---|---|
| `damage_per_min` | `g.damage_per_min` | synthesis (6: observations, evidence, lessons, summary, explanation, divergence) |
| `total_damage` | `g.damage` | synthesis (2: observations, lessons) |
| `kill_participation` | `g.kp_pct` | synthesis (3: observe_kill_participation, evidence, explanation) |
| `damage_per_gold` | `g.damage / g.gold` | NOT consumed by synthesis |
| `damage_per_death` | `g.damage / g.deaths` | NOT consumed by synthesis |
| `killing_spree` | `g.largest_killing_spree` | NOT consumed by synthesis |
| `multi_kills` | sum of multi-kill stats | NOT consumed by synthesis |

### Durability Engine
| Key | Source | Consumed By |
|---|---|---|
| `total_heal` | `g.total_heal` | synthesis (3: lessons, summary, divergence) |
| `damage_mitigated` | `g.damage_mitigated` | synthesis (3: lessons, summary, divergence) |
| `cc_time` | `g.cc_time` | synthesis (3: lessons, summary, divergence) |
| `heals_on_teammates` | `g.heals_on_teammates` | NOT consumed by synthesis |
| `damage_shielded` | `g.damage_shielded` | NOT consumed by synthesis |
| `damage_taken` | `g.total_damage_taken` | NOT consumed by synthesis |
| `physical_damage_taken` | `g.physical_damage_taken` | NOT consumed by synthesis |
| `magic_damage_taken` | `g.magic_damage_taken` | NOT consumed by synthesis |

### Vision Engine
| Key | Source | Consumed By |
|---|---|---|
| `vision_score` | `g.vision` | synthesis (1: observe_vision_control) |
| `wards_killed` | `g.wards_killed` | synthesis (3: observe_vision_control, lessons, summary) |
| `vision_per_min` | `g.vision_per_min` | NOT consumed by synthesis |
| `wards_placed` | `g.wards_placed` | NOT consumed by synthesis |
| `control_wards` | `g.control_wards` | NOT consumed by synthesis |

### Objective Engine
| Key | Source | Consumed By |
|---|---|---|
| All 11 keys | team/enemy objectives | NOT consumed by synthesis (objective_control reads from game directly) |

### Draft Engine
| Key | Source | Consumed By |
|---|---|---|
| `pick_order` | `g.pick_order` | NOT consumed by synthesis (draft has no distributions) |

## Signature Types

### Consumed by Synthesis (10 types)
| Type | Source Engine | Features Used |
|---|---|---|
| `death_cluster` | death | `cluster_size`, `gap_minutes` |
| `death_chain` | death | `chain_length`, `initial_gap`, `final_gap` |
| `death_phase_concentration` | death | `concentrated_phase`, `phase_death_count` |
| `combat_profile` | combat | `deaths`, `damage`, `dpm`, `kp_pct`, `kills`, `assists` |
| `durability_profile` | durability | `total_heal`, `damage_mitigated`, `cc_time`, `damage_shielded` |
| `vision_profile` | vision | `vision_score`, `vision_per_min`, `wards_killed`, `wards_placed`, `control_wards` |
| `champion_repetition` | draft | `champion`, `games_on_champ`, `champ_wr` |
| `counter_pick_relation` | draft | `relation`, `my_pick_order`, `enemy_pick_order` |
| `pick_position` | draft | `pick_order`, `position_label` |
| `side_assignment` | draft | `side` |

### Produced but NOT Consumed by Synthesis (20 types)
| Type | Source Engine | Why Unused |
|---|---|---|
| `survival_profile` | death | Features read from game, not from signature |
| `cs_checkpoint_sequence` | economy | CS values read from game, not from signature |
| `cs_partial_data` | economy | No consumer |
| `gold_checkpoint` | economy | Gold values read from game, not from signature |
| `first_clear_timing` | economy | No consumer (jungle-specific) |
| `item_purchase_sequence` | economy | No consumer |
| `multi_kill_event` | combat | No consumer |
| `killing_spree_event` | combat | No consumer |
| `bounty_acquired` | combat | No consumer |
| `spell_cast_profile` | combat | No consumer |
| `damage_taken_breakdown` | durability | No consumer |
| `enemy_vision_contrast` | vision | No consumer |
| `personal_objective_profile` | objective | No consumer |
| `team_objective_profile` | objective | No consumer |
| `enemy_objective_profile` | objective | No consumer |
| `objective_contrast` | objective | No consumer |
| `objective_steal_event` | objective | No consumer |
| `first_objective_sequence` | objective | No consumer |
| `inhibitor_presence` | objective | No consumer |
| `role_assignment` | draft | No consumer |
| `draft_sequence` | draft | No consumer |

## Access Patterns in Synthesis

### Pattern 1: Distribution Band Assessment (most common)
```python
dist = engines.combat.distributions.get("damage_per_min")
band = self._assess_against_distribution(value, dist)
# Returns: "bottom_10", "bottom_25", "middle", "top_25", "top_10", "unknown"
```
Used in: observations, evidence, lessons, summary, explanation, divergence

### Pattern 2: Profile Feature Extraction
```python
combat = self._get_profile_features(signatures, "combat_profile")
deaths = combat.get("deaths", game.deaths)
```
Fragile: untyped dict access with string keys and fallback to game fields

### Pattern 3: Direct Game Field Access
```python
game.my_team.dragon_kills
game.cs_10
game.gold_lead_15
```
Used in: observe_objective_control, observe_economy_pattern, _build_summary_multi, _identify_divergences_multi

### Pattern 4: Signature Type Filtering
```python
death_clusters = self._get_signatures_by_type(signatures, "death_cluster")
```
Returns list of EngineSignature objects matching a type

## Contract Summary for Synthesis Decomposition

For each output channel in the Verdict, the required engine data is:

**Observations** (12 producers):
- Need: combat distributions (deaths_per_game, damage_per_min, total_damage, kill_participation), economy distributions (cs_at_10, cs_at_15), vision distributions (vision_score, wards_killed), death signatures, draft signatures
- Also need: game fields directly (my_team, duration_min, cs_10, cs_15, gold_lead_15, kp_pct, turret_kills)

**Evidence** (_build_evidence_multi):
- Need: all profile signatures (combat, durability, vision), death signatures, draft signatures
- Need: combat distributions (damage_per_min, kill_participation), death distributions (deaths_per_game)

**Lessons** (_derive_lessons_multi):
- Need: death signatures, draft signatures, champion_repetition
- Need: combat distributions (damage_per_min, total_damage), death distributions (deaths_per_game), durability distributions (total_heal, damage_mitigated, cc_time), vision distributions (wards_killed)
- Need: game fields (cs_10, cs_15, gold_lead_15, champion, overall WR from similarity_output)

**Summary** (_build_summary_multi):
- Need: all profile signatures, death signatures, draft signatures
- Need: combat distributions (damage_per_min), death distributions (deaths_per_game), durability distributions (total_heal, damage_mitigated, cc_time), vision distributions (wards_killed), economy distributions (cs_at_10)
- Need: game fields (cs_10, cs_15, gold_lead_15, duration_min)

**Explanation** (_build_explanation_multi):
- Need: matched patterns from player model
- Need: combat distributions (damage_per_min, kill_participation), death distributions (deaths_per_game), economy distributions (cs_at_10)
- Need: profile signatures (combat, durability, vision)

**Divergences** (_identify_divergences_multi):
- Need: combat distributions (damage_per_min), death distributions (deaths_per_game), durability distributions (total_heal, damage_mitigated, cc_time)
- Need: game fields (early_deaths, turret_kills)

## Typed Profile Contracts (Decomposition)

Synthesis now uses typed dataclasses instead of untyped dicts for profile feature extraction:

### CombatProfile (from combat_profile signature + Game fallbacks)
| Field | Signature Key | Game Fallback |
|---|---|---|
| deaths | "deaths" | game.deaths |
| damage | "damage" | game.damage |
| dpm | "dpm" | game.damage_per_min |
| kp_pct | "kp_pct" | game.kp_pct |
| kills | "kills" | game.kills |
| assists | "assists" | game.assists |

### DurabilityProfile (from durability_profile signature + Game fallbacks)
| Field | Signature Key | Game Fallback |
|---|---|---|
| total_heal | "total_heal" | game.total_heal |
| damage_mitigated | "damage_mitigated" | game.damage_mitigated |
| cc_time | "cc_time" | game.cc_time |
| damage_shielded | "damage_shielded" | game.damage_shielded |

### VisionProfile (from vision_profile signature + Game fallbacks)
| Field | Signature Key | Game Fallback |
|---|---|---|
| vision_score | "vision_score" | game.vision |
| vision_per_min | "vision_per_min" | game.vision_per_min |
| wards_killed | "wards_killed" | game.wards_killed |
| wards_placed | "wards_placed" | game.wards_placed |
| control_wards | "control_wards" | game.control_wards |

### SummarySection
| Field | Description |
|---|---|
| domain | "death", "combat", "economy", "durability", "vision", "draft" |
| statement | Sentence fragment for this domain |
| data | Dict with supporting metrics for UI rendering |

### Summary
| Field | Description |
|---|---|
| sections | List[SummarySection] |
| to_text() | Backward-compatible: joins section statements with spaces |

### Divergence
| Field | Description |
|---|---|
| divergence_type | "win_high_deaths", "loss_low_impact", "cs_recovery", "high_dpm_loss", "survival_no_convert", etc. |
| statement | Human-readable sentence |
| data | Dict with supporting metrics |
| win | Whether this divergence is from a win |

### Removed
- `Verdict.explanation` — was dead data, never rendered by any consumer
- `_build_explanation_multi()` — 66 lines of dead code removed