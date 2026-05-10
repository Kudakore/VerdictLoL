import json
import sys
import os
import random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# TEMPLATE POOLS
# Multiple ways to express the same finding.
# pick_template() selects one based on a seed derived from the data
# so the same game always gets the same template, but different games vary.
# ─────────────────────────────────────────────

def pick(templates, seed_val, extra=""):
    """
    Deterministically pick a template based on a seed value.
    extra: additional string mixed into seed to ensure different findings
    with the same numeric value don't always pick the same template.
    """
    idx = abs(hash(str(round(seed_val, 3)) + str(extra))) % len(templates)
    return templates[idx]

def magnitude_tier(value, thresholds):
    """
    Returns 'low', 'mid', or 'high' based on where value falls in thresholds.
    thresholds: (low_max, high_min) — below low_max = low, above high_min = high
    """
    low_max, high_min = thresholds
    if abs(value) <= low_max:
        return "low"
    elif abs(value) >= high_min:
        return "high"
    return "mid"

def pick_magnitude(templates_by_tier, seed_val, value, thresholds):
    """
    Pick from magnitude-appropriate templates.
    templates_by_tier: dict with keys "low", "mid", "high" each containing a list.
    Falls back to "mid" if tier not found.
    """
    tier = magnitude_tier(value, thresholds)
    pool = templates_by_tier.get(tier, templates_by_tier.get("mid", []))
    if not pool:
        pool = templates_by_tier.get("high", templates_by_tier.get("low", ["."]))
    idx = abs(hash(str(round(seed_val, 2)))) % len(pool)
    return pool[idx]

def ctx(fired_types, *check_types):
    """Return True if any of check_types are in fired_types."""
    return any(t in fired_types for t in check_types)

# ─────────────────────────────────────────────
# SECTION HEADERS
# ─────────────────────────────────────────────

CATEGORY_HEADERS = {
    "Build":               "BUILD PATTERNS",
    "Performance":         "PERFORMANCE GAPS",
    "Early Game":          "EARLY GAME",
    "Early Game Tempo":    "EARLY GAME TEMPO",
    "Champion":            "CHAMPION SELECTION",
    "Enemy Matchup":       "ENEMY MATCHUP",
    "Pattern":             "GAME PATTERNS",
    "Causal Chain":        "CAUSAL CHAINS",
    "Matchup Intelligence":"MATCHUP INTELLIGENCE",
    "Trend":               "PERFORMANCE TREND",
    "Queue Split":         "QUEUE SPLIT",
    "Map Side":            "MAP SIDE",
    "Vision-Objectives":   "VISION & OBJECTIVES",
    "Game Fingerprint":    "GAME FINGERPRINT",
}

SEVERITY_ORDER = {
    "CRITICAL": 0,
    "CLEAR":    1,
    "NOTABLE":  2,
    "WEAK":     3,
}

# ─────────────────────────────────────────────
# FINDING FORMATTERS
# ─────────────────────────────────────────────

def format_finding(finding):
    ftype  = finding["type"]
    data   = finding["data"]
    voice  = finding["voice"]
    label  = finding["confidence_label"]
    validated = finding.get("validated")

    caution = " [Pattern weakens on trimmed dataset — interpret with caution]" if validated is False else ""

    lines = []

    # ── BUILD ─────────────────────────────────────────────────────────────────

    if ftype == "first_item_underperform":
        item  = data["item"]
        games = data["games"]
        wins  = data["wins"]
        losses = data["losses"]
        wr    = data["winrate"]
        comp  = data.get("comparison", "")

        if voice == "high":
            lines.append(f"  [{label}] First Item: {item}")
            lines.append(f"  {games} games. {wins}W {losses}L. {wr}% winrate.")
            if comp:
                lines.append(f"  {comp}")
            conclusion = pick([
                f"  You are {losses - wins} losses deeper than wins when you start {item}. That is not variance.",
                f"  {wr}% on {games} games starting {item}. The pattern is established.",
                f"  Starting {item} is costing you games. {games} games of evidence.",
            ], wr)
            lines.append(conclusion + caution)

        elif voice == "medium":
            lines.append(f"  [{label}] First Item: {item}")
            lines.append(f"  {games} games, {wr}% winrate.")
            if comp:
                lines.append(f"  {comp}")
            lines.append(f"  Below 50% and trending negative. Worth adjusting.{caution}")

        elif voice == "low":
            lines.append(f"  [{label}] First Item: {item} — {wr}% across {games} games. Early signal.{caution}")

    elif ftype == "build_divergence":
        wi   = data["win_item"]
        wc   = data["win_count"]
        wwr  = data.get("win_item_wr")
        li   = data["loss_item"]
        lc   = data["loss_count"]
        lwr  = data.get("loss_item_wr")

        if voice == "high":
            lines.append(f"  [{label}] Build Path Divergence")
            lines.append(f"  Wins:   {wi} ({wc}x{f', {wwr}% WR' if wwr else ''})")
            lines.append(f"  Losses: {li} ({lc}x{f', {lwr}% WR' if lwr else ''})")
            conclusion = pick([
                f"  Your winning games and losing games start with different items. That is not coincidence.",
                f"  The build path splits your results. {wi} is your winning identity. {li} is not.",
                f"  Two different first items, two different outcomes. The data picks {wi}.",
            ], wc)
            lines.append(conclusion + caution)

        elif voice in ("medium", "low"):
            lines.append(f"  [{label}] Build Path Divergence")
            lines.append(f"  Wins start with {wi} ({wc}x) | Losses start with {li} ({lc}x){caution}")

    # ── PERFORMANCE ───────────────────────────────────────────────────────────

    elif ftype.startswith("delta_"):
        metric    = data["metric"]
        win_avg   = data["win_avg"]
        loss_avg  = data["loss_avg"]
        delta     = data["delta"]
        direction = data["direction"]
        ws        = data["win_sample"]
        ls        = data["loss_sample"]
        better    = "higher" if direction == "higher" else "lower"

        if voice == "high":
            lines.append(f"  [{label}] {metric}")
            lines.append(f"  Wins:   {win_avg}  ({ws} games)")
            lines.append(f"  Losses: {loss_avg}  ({ls} games)")
            lines.append(f"  Gap: {delta}")

            fired = finding.get("_fired_types", set())

            if metric == "Deaths before 15min":
                conclusion = pick_magnitude({
                    "low": [
                        f"  Slightly more early deaths in losses. The early game is leaning against you.",
                        f"  A small but consistent early death gap. It compounds over time.",
                    ],
                    "mid": [
                        f"  {delta} more deaths before 15min in losses. The early game is where these are decided.",
                        f"  Early deaths set the deficit. By the time mid-game arrives the snowball is already rolling.",
                        f"  The pre-15min death gap is real. You are getting caught early and it is costing you the game.",
                    ],
                    "high": [
                        f"  {delta} early deaths more in losses. That is a collapse, not a gap. The game is over before it starts.",
                        f"  You are dying significantly more before 15 minutes in losses. This is the primary loss signal.",
                        f"  The early death count in losses is alarming. The enemy jungler is setting the tempo from the opening clear.",
                    ],
                }, delta, delta, (0.4, 1.0))

            elif metric in ("CS", "CS/min"):
                if ctx(fired, "delta_early_deaths", "causal_invaded_snowball"):
                    conclusion = pick([
                        f"  The CS gap is downstream of the early deaths — the invasion costs you farm and the deficit holds.",
                        f"  You fall behind in the jungle invasion and never recover the CS. These two problems are one.",
                        f"  Early deaths and CS deficit travel together in your losses. Fix the early game and the farm follows.",
                    ], delta)
                else:
                    conclusion = pick_magnitude({
                        "low": [
                            f"  Small CS gap but consistent. Farm efficiency matters across a full game.",
                            f"  Slightly lower farm in losses. A {delta} gap per game compounds into item timing differences.",
                        ],
                        "mid": [
                            f"  {delta} {metric} separating wins from losses. Farm is the foundation of everything else.",
                            f"  The CS gap is real and consistent. Lower farm means slower items, less agency, less presence.",
                            f"  Your CS drops in every loss. That is not variance — it is the deficit compounding.",
                        ],
                        "high": [
                            f"  {delta} {metric} gap is severe. You are being completely out-farmed in losing games.",
                            f"  This farm deficit is the story of your losses. At this gap you are fighting with half an item behind.",
                            f"  Out-farmed by {delta} CS/min in every loss. The resource war is being lost before teamfights matter.",
                        ],
                    }, delta, delta, (0.5, 1.2))

            elif metric == "Vision/min":
                conclusion = pick_magnitude({
                    "low": [
                        f"  Slightly lower vision in losses. The map information gap is subtle but present.",
                        f"  A small vision deficit in losses. Wards are being skipped more when games go wrong.",
                    ],
                    "mid": [
                        f"  Less vision in losses means fewer informed decisions and more guesses that cost you.",
                        f"  Vision score tracks map control. In losses, the map belonged to them.",
                        f"  You see less of the map when you lose. Every uninformed objective attempt is a risk.",
                    ],
                    "high": [
                        f"  The vision gap in losses is significant. You are playing the mid and late game blind.",
                        f"  {delta} vision/min gap. In losses you essentially stopped warding — the map became their territory.",
                        f"  This is not a minor vision gap. It is the difference between knowing where the enemy is and guessing.",
                    ],
                }, delta, delta, (0.2, 0.5))

            elif metric == "Damage/min":
                if ctx(fired, "cs_differential", "damage_differential"):
                    conclusion = pick([
                        f"  Lower damage per minute and lower damage vs the enemy jungler. You are losing the combat presence battle on both axes.",
                        f"  The damage deficit shows up in your personal stats and in the head-to-head. You are less threatening in losses.",
                        f"  Damage down, jungle matchup down. In losses you are not a threat — you are a target.",
                    ], delta)
                else:
                    conclusion = pick_magnitude({
                        "low": [
                            f"  Slightly lower damage output in losses. Less presence in fights.",
                            f"  Small damage gap. You are a bit less active in combat when you lose.",
                        ],
                        "mid": [
                            f"  Lower damage output in losses means less threat on the map — objectives, skirmishes, teamfights.",
                            f"  The damage gap reflects how much you were in the game. In losses, not enough.",
                            f"  Your damage drops in losses. Less fighting presence translates directly into less map impact.",
                        ],
                        "high": [
                            f"  {delta} damage/min gap. In losses you are barely a factor in combat.",
                            f"  The damage difference is not a gap — it is an absence. You are not in the fights in losing games.",
                            f"  This damage deficit means the enemy team is not scared of you. No threat, no respect, no space.",
                        ],
                    }, delta, delta, (100, 400))

            elif metric == "Gold Lead at 15min":
                if ctx(fired, "causal_invaded_snowball", "delta_early_deaths"):
                    conclusion = pick([
                        f"  The gold deficit at 15 is the result of early deaths — the invasion set the economic hole.",
                        f"  Early deaths translated directly into gold deficit. One problem expressed as two numbers.",
                        f"  You die early, lose farm, lose gold. By 15 minutes the game is structurally decided.",
                    ], delta)
                else:
                    conclusion = pick_magnitude({
                        "low": [
                            f"  Small gold deficit at 15 but consistent. Item timing differences start here.",
                            f"  A {delta} gold gap at 15 is minor but it compounds into the mid-game.",
                        ],
                        "mid": [
                            f"  Early gold deficit against the enemy jungler is a consistent loss condition.",
                            f"  The resource gap at 15 is established before mid-game starts. You enter teamfights behind.",
                            f"  {delta} gold behind at 15min. That is a component item. The economy war is being lost early.",
                        ],
                        "high": [
                            f"  {delta} gold deficit at 15min is severe. That is a completed item worth of disadvantage entering mid-game.",
                            f"  You are being economically destroyed in the early game. The gold gap at 15 in losses is not recoverable.",
                            f"  This gold deficit at 15 is the single clearest predictor of your losses. The early economy decides everything.",
                        ],
                    }, delta, delta, (300, 700))

            elif metric in ("Kill Participation", "Death Share", "Damage Share"):
                win_pct  = round(win_avg * 100, 1)
                loss_pct = round(loss_avg * 100, 1)
                gap_pct  = round(delta * 100, 1)
                lines[-2] = f"  Wins:   {win_pct}%  ({ws} games)"
                lines[-1] = f"  Losses: {loss_pct}%  ({ls} games)"
                lines.append(f"  Gap: {gap_pct}%")
                if metric == "Kill Participation":
                    conclusion = f"  You contribute to kills more in wins. Lower KP in losses means you are not converting farm into fight presence."
                elif metric == "Death Share":
                    conclusion = f"  Your share of team deaths is higher in losses. You are taking more of the damage when your team is already losing fights."
                else:
                    conclusion = f"  Your damage share of team total is higher in wins. In losses you are being neutralized."
                conclusion = conclusion

            else:
                conclusion = pick_magnitude({
                    "low": [
                        f"  Small {metric} gap but it is consistent across the sample.",
                        f"  {metric} is slightly {better} in wins. Not dominant but real.",
                    ],
                    "mid": [
                        f"  {metric} is consistently {better} in every win. A reliable separator.",
                        f"  The {metric} gap holds across the full sample. Not noise.",
                        f"  {metric} tracks with your results.",
                    ],
                    "high": [
                        f"  The {metric} gap is one of the clearest splits in your data.",
                        f"  {metric} difference this large is decisive. It is a primary win condition.",
                        f"  {delta} {metric} gap. This is not a marginal edge — it is the game.",
                    ],
                }, delta, delta, (0.3, 1.0))

            lines.append(conclusion + caution)

        elif voice == "medium":
            if metric in ("Kill Participation", "Death Share", "Damage Share"):
                win_pct  = round(win_avg * 100, 1)
                loss_pct = round(loss_avg * 100, 1)
                gap_pct  = round(delta * 100, 1)
                lines.append(f"  [{label}] {metric}")
                lines.append(f"  Wins: {win_pct}% | Losses: {loss_pct}% | Gap: {gap_pct}%{caution}")
            else:
                lines.append(f"  [{label}] {metric}")
                lines.append(f"  Wins: {win_avg} | Losses: {loss_avg} | Gap: {delta}")
                # Build a short contextual note based on metric
                if metric in ("CS", "CS/min"):
                    note = f"  Consistently {better} in wins — the farm gap compounds into item timing and map pressure."
                elif metric == "Deaths before 15min":
                    note = f"  Consistently {better} in wins — early deaths set the economic and tempo deficit before mid-game starts."
                elif metric == "Vision/min":
                    note = f"  Consistently {better} in wins — more vision means better decisions on objectives and rotations."
                elif metric == "Damage/min":
                    note = f"  Consistently {better} in wins — more damage output means more threat on the map in fights and skirmishes."
                elif metric == "Gold/min":
                    note = f"  Consistently {better} in wins — gold pace determines item timing, and item timing determines fight windows."
                elif metric == "Gold Lead at 15min":
                    note = f"  Consistently {better} in wins — early gold advantage translates directly into item spikes before the enemy."
                else:
                    note = f"  Consistently {better} in wins. Meaningful gap."
                lines.append(note + caution)

        elif voice == "low":
            if metric in ("Kill Participation", "Death Share", "Damage Share"):
                win_pct  = round(win_avg * 100, 1)
                loss_pct = round(loss_avg * 100, 1)
                lines.append(f"  [{label}] {metric} — Wins: {win_pct}% | Losses: {loss_pct}%{caution}")
            else:
                lines.append(f"  [{label}] {metric} — Wins: {win_avg} | Losses: {loss_avg}")
                lines.append(f"  Small but consistent.{caution}")

    # ── EARLY GAME ────────────────────────────────────────────────────────────

    elif ftype == "short_loss_pattern":
        short  = data["short_losses"]
        total  = data["total_losses"]
        pct    = data["pct"]
        avg_cs = data.get("avg_cs_15")
        avg_d  = data.get("avg_early_deaths")

        if voice == "high":
            lines.append(f"  [{label}] Early Surrender Pattern")
            lines.append(f"  {short} of {total} losses ({pct}%) ended before 22 minutes.")
            if avg_cs:
                lines.append(f"  Average CS at 15min in these games: {avg_cs}")
            if avg_d is not None:
                lines.append(f"  Average early deaths: {avg_d}")
            conclusion = pick([
                f"  Nearly half your losses are decided in the first 20 minutes. These are not close games.",
                f"  {pct}% of losses are stomps, not competitive games. The early game is where they are lost.",
                f"  The game ends before it starts in {short} of your losses. Early collapse is the primary loss condition.",
            ], pct)
            lines.append(conclusion + caution)

        elif voice in ("medium", "low"):
            lines.append(f"  [{label}] Early Surrender Pattern — {short}/{total} losses ({pct}%) before 22 min.{caution}")

    elif ftype == "cs15_gap":
        win_avg  = data["win_avg"]
        loss_avg = data["loss_avg"]
        delta    = data["delta"]
        gold_val = round(delta * 20)

        if voice == "high":
            lines.append(f"  [{label}] CS at 15min Gap")
            lines.append(f"  Wins:   {win_avg} CS")
            lines.append(f"  Losses: {loss_avg} CS")
            conclusion = pick([
                f"  {delta} CS behind your winning pace at 15 minutes. That is ~{gold_val} gold in missed income before mid-game.",
                f"  The farm deficit at 15 minutes is established before teamfights matter. You are already behind.",
                f"  {delta} CS gap at 15min. Item spikes happen sooner for whoever farms better — and it is not you in these games.",
            ], delta)
            lines.append(conclusion + caution)

        elif voice in ("medium", "low"):
            lines.append(f"  [{label}] CS at 15min — Wins: {win_avg} | Losses: {loss_avg} | Gap: {delta}{caution}")

    # ── CHAMPION ──────────────────────────────────────────────────────────────

    elif ftype == "champion_winrate_gap":
        worst   = data["worst_champ"]
        worst_wr = data["worst_wr"]
        worst_n = data["worst_games"]
        best    = data["best_champ"]
        best_wr = data["best_wr"]
        best_n  = data["best_games"]
        gap     = round(best_wr - worst_wr, 1)

        if voice == "high":
            lines.append(f"  [{label}] Champion Performance Gap")
            lines.append(f"  {best}: {best_wr}% across {best_n} games")
            lines.append(f"  {worst}: {worst_wr}% across {worst_n} games")
            conclusion = pick([
                f"  {gap}% gap. The data has a preference. It is {best}.",
                f"  {worst} is underperforming at {worst_wr}% over {worst_n} games. That sample is significant.",
                f"  Your results split clearly by champion. {best} is working. {worst} is not.",
            ], gap)
            lines.append(conclusion + caution)

        elif voice == "medium":
            lines.append(f"  [{label}] {best} ({best_wr}% WR, {best_n}g) vs {worst} ({worst_wr}% WR, {worst_n}g) — {gap}% gap.{caution}")

        elif voice == "low":
            lines.append(f"  [{label}] {best} ({best_wr}% WR, {best_n}g) vs {worst} ({worst_wr}% WR, {worst_n}g)")
            lines.append(f"  Small sample — {worst_n + best_n} games total. Pattern may not hold.{caution}")

    # ── ENEMY MATCHUP ─────────────────────────────────────────────────────────

    elif ftype == "cs_differential":
        win_d   = data["win_avg_diff"]
        loss_d  = data["loss_avg_diff"]
        swing   = data.get("total_swing", round(abs(win_d) + abs(loss_d)))
        role_label = data.get("role_label", "Enemy Counterpart")

        if voice == "high":
            lines.append(f"  [{label}] CS Differential vs {role_label}")
            lines.append(f"  Wins:   {'+' if win_d >= 0 else ''}{round(win_d)} CS vs enemy")
            lines.append(f"  Losses: {'+' if loss_d >= 0 else ''}{round(loss_d)} CS vs enemy")
            conclusion = pick_magnitude({
                "low": [
                    f"  Small but consistent CS edge in wins. You are farming slightly cleaner against the {role_label.lower()}.",
                    f"  The CS differential is modest but it shows up every time. Marginal farm edges compound.",
                ],
                "mid": [
                    f"  {swing} CS swing. The farm battle with the {role_label.lower()} determines the outcome.",
                    f"  When you lose the CS race against the {role_label.lower()}, you lose the game.",
                    f"  CS differential vs {role_label.lower()} is the clearest split in your data. {round(win_d):+} in wins, {round(loss_d):+} in losses.",
                    f"  The farm 1v1 is the game. You win it when you win.",
                    f"  {round(win_d):+} in wins, {round(loss_d):+} in losses. That gap does not close itself.",
                    f"  Consistent CS advantage in wins, consistent deficit in losses. The farm battle is being won and lost.",
                ],
                "high": [
                    f"  {swing} CS swing. That is not a race — it is a rout. The {role_label.lower()} is lapping you in losses.",
                    f"  This CS gap is severe. You are being dominated in the farm battle in every loss.",
                    f"  {round(win_d):+} in wins, {round(loss_d):+} in losses. The farm differential alone could predict your results.",
                ],
            }, swing, swing, (30, 70))
            lines.append(conclusion + caution)

        elif voice == "medium":
            lines.append(f"  [{label}] CS vs Enemy — Wins: {round(win_d):+} | Losses: {round(loss_d):+}")
            lines.append(f"  The farm gap with the enemy is a consistent predictor of your result.{caution}")
        elif voice == "low":
            lines.append(f"  [{label}] CS vs Enemy — Wins: {round(win_d):+} | Losses: {round(loss_d):+}{caution}")

    elif ftype == "damage_differential":
        win_d   = data["win_avg_diff"]
        loss_d  = data["loss_avg_diff"]
        swing   = data.get("total_swing", round(abs(win_d) + abs(loss_d)))

        role_label = data.get("role_label", "Enemy Counterpart")

        if voice == "high":
            lines.append(f"  [{label}] Damage Differential vs {role_label}")
            lines.append(f"  Wins:   {'+' if win_d >= 0 else ''}{round(win_d)} damage vs enemy")
            lines.append(f"  Losses: {'+' if loss_d >= 0 else ''}{round(loss_d)} damage vs enemy")
            conclusion = pick_magnitude({
                "low": [
                    f"  Slight damage edge in wins. You are a marginally bigger threat when you win.",
                    f"  Small but consistent damage differential. Combat presence is slightly higher in wins.",
                ],
                "mid": [
                    f"  {swing} damage swing. In losses the {role_label.lower()} is the bigger combat threat.",
                    f"  When you lose, the {role_label.lower()} controls skirmishes. That pressure translates to map control.",
                    f"  Damage differential reflects who owns the 1v1 fight window. In losses, it is not you.",
                    f"  You deal more damage when you win. In losses you are not a threat — you are a target.",
                    f"  {round(win_d):+} in wins, {round(loss_d):+} in losses. The combat gap is real and consistent.",
                ],
                "high": [
                    f"  {swing} damage swing is decisive. In losses the {role_label.lower()} is not just ahead — they are a different tier of threat.",
                    f"  This damage gap means the {role_label.lower()} is winning every fight they take against you in losing games.",
                    f"  At {swing} damage swing, the {role_label.lower()} has free reign. They fight, they win, they snowball.",
                ],
            }, swing, swing, (2000, 6000))
            lines.append(conclusion + caution)

        elif voice == "medium":
            lines.append(f"  [{label}] Damage vs Enemy — Wins: {round(win_d):+} | Losses: {round(loss_d):+}")
            lines.append(f"  You are less threatening in combat during losses.{caution}")
        elif voice == "low":
            lines.append(f"  [{label}] Damage vs Enemy — Wins: {round(win_d):+} | Losses: {round(loss_d):+}{caution}")

    elif ftype == "kills_differential":
        win_d   = data["win_avg_diff"]
        loss_d  = data["loss_avg_diff"]
        swing   = data.get("total_swing", round(abs(win_d) + abs(loss_d), 1))
        role_label = data.get("role_label", "Enemy Counterpart")

        if voice == "high":
            lines.append(f"  [{label}] Kill Differential vs {role_label}")
            lines.append(f"  Wins:   {'+' if win_d >= 0 else ''}{round(win_d, 1)} kills vs {role_label.lower()}")
            lines.append(f"  Losses: {'+' if loss_d >= 0 else ''}{round(loss_d, 1)} kills vs {role_label.lower()}")
            conclusion = pick([
                f"  {swing} kill swing. The individual duels with the {role_label.lower()} go your way when you win — and against you when you lose.",
                f"  Kill differential tracks who is winning the 1v1 matchup. In losses, the {role_label.lower()} is ahead in every metric that matters.",
                f"  You are trading kills differently depending on the result. In wins you come out ahead. In losses you do not.",
            ], swing)
            lines.append(conclusion + caution)

        elif voice in ("medium", "low"):
            lines.append(f"  [{label}] Kills vs Enemy — Wins: {round(win_d, 1):+} | Losses: {round(loss_d, 1):+}{caution}")

    # ── PATTERNS ──────────────────────────────────────────────────────────────

    elif ftype == "pattern_invaded_early":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_ed  = data.get("avg_early_deaths")
        avg_cs  = data.get("avg_cs_15")
        avg_dur = data.get("avg_duration")

        lines.append(f"  [{label}] Early Invasion Pattern")
        lines.append(f"  {count} of {total} losses ({pct}%) share this signature:")
        if avg_ed:
            lines.append(f"    — {avg_ed} deaths before 15 minutes on average")
        if avg_cs:
            lines.append(f"    — {avg_cs} CS at 15 minutes on average")
        if avg_dur:
            lines.append(f"    — Games ended at {avg_dur} minutes on average")
        conclusion = pick([
            f"  You are getting invaded early, falling behind in farm, and not recovering. The pattern is consistent enough to be a pathing or ward problem, not variance.",
            f"  Early deaths and low CS at 15 in short games. This is an invasion pattern — you are being caught in your jungle and never rebuilding the deficit.",
            f"  The early game is being taken from you in these losses. Better ward coverage on your second buff and jungle entrances would reduce this pattern.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "pattern_won_jungle_lost_game":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_d   = data.get("avg_deaths")
        avg_cd  = data.get("avg_cs_diff")

        lines.append(f"  [{label}] Won Jungle, Lost Game")
        lines.append(f"  {count} of {total} losses ({pct}%) — you farmed even or ahead, but still lost.")
        if avg_d:
            lines.append(f"  Average deaths in these games: {avg_d}")
        if avg_cd is not None:
            lines.append(f"  Average CS differential vs enemy jungler: {round(avg_cd):+}")
        conclusion = pick([
            f"  The matchup was not the problem in these games. The deaths tell the story — overcommitting in fights when already in a winning position.",
            f"  You build a farm lead and then give it back through deaths. The farm is there. The decision-making in fights is where these are lost.",
            f"  Winning the farm battle but losing the game points to mid-late game decision-making. Too aggressive when you should be patient.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "pattern_pure_stomp":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_dur = data.get("avg_duration")

        lines.append(f"  [{label}] Pure Stomp Pattern")
        lines.append(f"  {count} of {total} losses ({pct}%) — all metrics negative, short games.")
        if avg_dur:
            lines.append(f"  Average duration: {avg_dur} minutes.")
        conclusion = pick([
            f"  These are not close games. The enemy jungler is ahead in CS, damage, and kills simultaneously. These losses are about the matchup — either champion, pathing, or both.",
            f"  When all three metrics go negative in a short game, you are being outclassed in the jungle matchup itself. Not teamfight, not vision — the 1v1 jungle dynamic.",
            f"  {pct}% of your losses are complete jungle stomps. These are not recoverable with better teamfighting — the problem is in the jungle from the opening clear.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "pattern_scaled_misplayed":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_kp  = data.get("avg_kp")
        avg_d   = data.get("avg_deaths")

        lines.append(f"  [{label}] Scaled But Misplayed")
        lines.append(f"  {count} of {total} losses ({pct}%) — good farm and kill participation, but too many deaths in long games.")
        if avg_kp:
            lines.append(f"  Average kills + assists: {avg_kp}")
        if avg_d:
            lines.append(f"  Average deaths: {avg_d}")
        conclusion = pick([
            f"  You are in these games — farming, getting picks — but dying too many times to convert the lead. The resource is there. The execution at the point of conversion is not.",
            f"  High participation, high deaths, long losses. You are fighting too much when ahead instead of forcing objectives. The lead bleeds out through unnecessary deaths.",
            f"  These games are being given away. You have enough farm and presence to win them — the deaths are the difference between winning and losing the game you are already ahead in.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "pattern_vision_deficit":
        win_avg  = data["win_avg"]
        loss_avg = data["loss_avg"]
        delta    = data["delta"]

        lines.append(f"  [{label}] Vision Deficit in Losses")
        lines.append(f"  Wins:   {win_avg} vision/min")
        lines.append(f"  Losses: {loss_avg} vision/min")
        conclusion = pick([
            f"  {delta} vision/min lower in losses. Less information means worse decisions on objective timers, invades, and rotations.",
            f"  Vision score drops in losses. This is not about raw warding — it is about how much of the map you control. In losses, you control less.",
            f"  The vision gap between your wins and losses is consistent. Better ward placement in losing games changes the information landscape.",
        ], delta)
        lines.append(conclusion + caution)

    elif ftype == "pattern_dragon_control":
        games   = data["games"]
        win_pct = data["win_dragon_pct"]
        loss_pct = data["loss_dragon_pct"]

        lines.append(f"  [{label}] Dragon Control Correlation")
        lines.append(f"  In {win_pct}% of wins, your team controlled more dragons.")
        lines.append(f"  In {loss_pct}% of losses, the enemy team controlled more dragons.")
        conclusion = pick([
            f"  Dragon control tracks with winning positions in your data. Build this as a pathing habit — not ahead of fixing early economy and deaths.",
            f"  The dragon correlation in your data is strong enough to be meaningful. Your team wins when it controls early drakes.",
            f"  Objective control and game results are aligned in your data. Dragon priority translates directly into winning.",
        ], win_pct)
        lines.append(conclusion + caution)


    # ── CAUSAL CHAINS ─────────────────────────────────────────────

    elif ftype == "causal_invaded_snowball":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_ed  = data.get("avg_early_deaths")
        avg_cs  = data.get("avg_cs_15")
        avg_gold = data.get("avg_gold_lead_15")

        lines.append(f"  [{label}] Invasion → Farm Loss → Gold Deficit → Loss")
        lines.append(f"  {count} of {total} losses ({pct}%) follow this exact sequence:")
        if avg_ed: lines.append(f"    1. {avg_ed} early deaths on average")
        if avg_cs: lines.append(f"    2. {avg_cs} CS at 15 minutes — farm never recovered")
        if avg_gold: lines.append(f"    3. {round(avg_gold)} gold deficit at 15 minutes")
        lines.append(f"    4. Game lost")
        conclusion = pick([
            f"  This is not three separate problems. It is one — the early jungle is being taken from you and the deficit compounds.",
            f"  Early invasion sets off a chain reaction. Every stat that follows is a consequence, not an independent failure.",
            f"  The root cause is jungle access in the first 8 minutes. Fix that and the CS, gold, and result follow.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "causal_ahead_threw":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_gold = data.get("avg_gold_lead_15")
        avg_deaths = data.get("avg_deaths")
        avg_dur = data.get("avg_duration")
        death_related = data.get("death_related", 0)
        obj_related = data.get("objective_related", 0)

        lines.append(f"  [{label}] Won the Early Game, Lost the Game")
        lines.append(f"  {count} of {total} losses ({pct}%) — ahead at 15 minutes, still lost.")
        if avg_gold: lines.append(f"  Average gold lead at 15: +{round(avg_gold)}")
        if avg_deaths: lines.append(f"  Average deaths: {avg_deaths}")
        if avg_dur: lines.append(f"  Average game length: {round(avg_dur)} minutes")
        if death_related >= count * 0.5:
            lines.append(f"  Primary cause: deaths. Lead built, lead bled out through fighting.")
        elif obj_related >= count * 0.5:
            lines.append(f"  Primary cause: objectives. Enemy took drakes while you held the gold lead.")
        conclusion = pick([
            f"  You are earning leads and not converting them. The early game is not the problem. What happens after the lead is.",
            f"  A gold lead at 15 should close a game, not start a new fight. The advantage is being spent on combat instead of objectives.",
            f"  These are the most frustrating losses — you did the hard part and gave it back. Converting a lead is its own skill.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "causal_no_vision_objectives":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_drakes = data.get("avg_enemy_drakes")

        lines.append(f"  [{label}] No Vision → Conceded Objectives")
        lines.append(f"  {count} of {total} losses ({pct}%): 0 control wards, enemy secured dragons freely.")
        if avg_drakes: lines.append(f"  Enemy averaged {avg_drakes} dragons in these games.")
        conclusion = pick([
            f"  No control wards means no information on dragon, baron, or river. The enemy team just walked up and took them.",
            f"  Control wards are not optional in ranked. Every drake taken without vision was contestable.",
            f"  The objective chain starts with a single ward. 0 control wards in a 30-minute game costs you every time.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "causal_team_feed_unwinnable":
        count   = data["count"]
        total   = data["total_losses"]
        pct     = data["pct"]
        avg_team_deaths = data.get("avg_team_deaths")
        avg_my_cs = data.get("avg_my_cs")

        lines.append(f"  [{label}] Team Feeding → Unwinnable")
        lines.append(f"  {count} of {total} losses ({pct}%) — your CS was fine, your team was not.")
        if avg_team_deaths: lines.append(f"  Average team deaths: {avg_team_deaths}")
        if avg_my_cs: lines.append(f"  Your average CS in these games: {avg_my_cs}")
        conclusion = pick([
            f"  These losses are not about your performance. Your farm was fine. Your team collapsed.",
            f"  When your team dies this many times, the map becomes unplayable regardless of individual performance.",
            f"  Not every loss is recoverable from your position. Recognize these games early and manage tilt.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "causal_comeback_wins":
        count   = data["count"]
        total_wins = data["total_wins"]
        pct     = data["pct"]
        avg_deficit = data.get("avg_gold_deficit_15")

        lines.append(f"  [+] Comeback Wins")
        lines.append(f"  {count} of {total_wins} wins ({pct}%) — behind at 15, won anyway.")
        if avg_deficit: lines.append(f"  Average gold deficit at 15 in these games: {round(avg_deficit)}")
        conclusion = pick([
            f"  You know how to come back. Being behind at 15 is not a death sentence for you.",
            f"  Late-game resilience is a real skill and your data confirms you have it.",
            f"  {pct}% of your wins started from behind. That is a mental edge worth keeping.",
        ], pct)
        lines.append(conclusion + caution)

    elif ftype == "causal_cs_recovery":
        lines.append(f"  [{label}] CS Recovery Determines Outcome")
        lines.append(f"  Games where you started behind in CS at 10 ({data['behind_games']} total):")
        lines.append(f"  Recovered by 15 ({data['recovered_games']} games):     {data['recovered_wr']}% WR")
        lines.append(f"  Did not recover ({data['nrecovered_games']} games): {data['nrecovered_wr']}% WR")
        lines.append(f"  Gap: {data['gap']}%")
        lines.append(f"  When you fall behind early on CS, recovering in the next 5 minutes mostly saves the game. Not recovering mostly ends it.{caution}")

    # ── MATCHUP INTELLIGENCE ──────────────────────────────────────

    elif ftype == "matchup_bad":
        matchups = data["matchups"]
        lines.append(f"  [{label}] Losing Matchups")
        for m in matchups:
            cs_note = f"  (avg {round(m['avg_cs_diff']):+} CS)" if m.get('avg_cs_diff') is not None else ""
            lines.append(f"  {m['champion']}: {m['winrate']}% WR across {m['games']} games{cs_note}")
        worst = matchups[0]["champion"] if matchups else "this champion"
        conclusion = pick([
            f"  These are not random losses — they are matchup losses. Adjust your approach or respect the counter.",
            f"  Your data shows specific champions that beat you consistently. That is actionable for champion select.",
            f"  When you see {worst} on the enemy team, you need a different approach — or a different pick.",
        ], len(matchups))
        lines.append(conclusion + caution)

    elif ftype == "matchup_good":
        matchups = data["matchups"]
        lines.append(f"  [+] Winning Matchups")
        for m in matchups:
            cs_note = f"  (avg {round(m['avg_cs_diff']):+} CS)" if m.get('avg_cs_diff') is not None else ""
            lines.append(f"  {m['champion']}: {m['winrate']}% WR across {m['games']} games{cs_note}")
        lines.append(f"  These are favorable matchups based on your personal data. Seek them out.{caution}")

    # ── TIME TREND ────────────────────────────────────────────────

    elif ftype == "trend_declining":
        recent_wr = data["recent_wr"]
        hist_wr   = data["historical_wr"]
        diff      = data["diff"]
        streak    = data.get("max_loss_streak", 0)

        lines.append(f"  [{label}] Performance Declining")
        lines.append(f"  Last 10 games: {recent_wr}% WR  |  Baseline: {hist_wr}% WR  |  Drop: {abs(diff)}%")
        if streak >= 3: lines.append(f"  Loss streak: {streak} consecutive games")
        conclusion = pick([
            f"  Something changed recently. Either the meta shifted, you are tilting, or a habit crept in.",
            f"  A {abs(diff)}% winrate drop over 10 games is significant. Take a break or change your approach.",
            f"  Recent performance is below your baseline. Worth paying attention to before it extends further.",
        ], abs(diff))
        lines.append(conclusion + caution)

    elif ftype == "trend_improving":
        recent_wr = data["recent_wr"]
        hist_wr   = data["historical_wr"]
        diff      = data["diff"]

        lines.append(f"  [+] Performance Improving")
        lines.append(f"  Last 10 games: {recent_wr}% WR vs {hist_wr}% baseline. +{diff}%.")
        conclusion = pick([
            f"  You are playing better than your average right now. Whatever changed, keep doing it.",
            f"  Recent games are outperforming your baseline. This is momentum — sustain it.",
            f"  +{diff}% over your baseline in 10 games. Something is clicking. Do not overthink it.",
        ], diff)
        lines.append(conclusion + caution)

    elif ftype == "trend_loss_streak":
        streak    = data["streak"]
        recent_wr = data["recent_wr"]

        lines.append(f"  [{label}] {streak}-Game Loss Streak")
        lines.append(f"  {streak} consecutive losses. Recent WR: {recent_wr}%.")
        conclusion = pick([
            f"  Loss streaks compound mentally. Consider a break before the streak gets longer.",
            f"  {streak} in a row is when tilt becomes a factor independent of skill.",
            f"  Stop the streak before it extends. One break, one reset, come back fresh.",
        ], streak)
        lines.append(conclusion + caution)

    elif ftype == "streak_active":
        current_len  = data["current_len"]
        current_type = data["current_type"]
        longest_win  = data.get("longest_win", 0)
        longest_loss = data.get("longest_loss", 0)

        if current_type == "loss":
            lines.append(f"  [{label}] {current_len}-Game Loss Streak")
            lines.append(f"  {current_len} consecutive losses currently active.")
            lines.append(f"  Longest win streak: {longest_win}  |  Longest loss streak: {longest_loss}")
            conclusion = pick([
                f"  Stop the streak before it extends. A single session break resets the spiral.",
                f"  {current_len} in a row. Tilt is now a real factor. Step away before the next game.",
                f"  Loss streaks compound mentally. One break is worth more than one more game right now.",
            ], current_len)
            lines.append(conclusion + caution)
        else:
            lines.append(f"  [+] {current_len}-Game Win Streak")
            lines.append(f"  {current_len} consecutive wins. You are in form.")
            lines.append(f"  Longest win streak: {longest_win}  |  Longest loss streak: {longest_loss}")
            conclusion = pick([
                f"  Whatever you are doing right now, keep doing it. This is your peak form.",
                f"  {current_len} wins in a row. Momentum is real — sustain it.",
                f"  You are on a run. Play your best champions and do not overthink it.",
            ], current_len)
            lines.append(conclusion + caution)

    # ── VISION-OBJECTIVES ─────────────────────────────────────────

    elif ftype == "vision_dragon_correlation":
        wg   = data["warded_games"]
        ug   = data["unwarded_games"]
        wdp  = data["warded_dragon_pct"]
        udp  = data["unwarded_dragon_pct"]
        diff = data["dragon_diff"]
        wwr  = data.get("warded_wr")
        uwr  = data.get("unwarded_wr")

        lines.append(f"  [{label}] Control Wards → Dragon Control")
        lines.append(f"  With 2+ control wards ({wg} games):  dragon control {wdp}%{f'  |  {wwr}% WR' if wwr else ''}")
        lines.append(f"  With 0 control wards  ({ug} games):  dragon control {udp}%{f'  |  {uwr}% WR' if uwr else ''}")
        lines.append(f"  Dragon control gap: {diff}%")
        conclusion = pick([
            f"  Your control ward placement directly predicts whether your team gets dragon. One ward changes what you can contest.",
            f"  {diff}% more dragon control when you ward. That translates into drake stacks, soul, and wins.",
            f"  The data draws a straight line from your ward to your team's objective control. Two wards per game is the minimum.",
        ], diff)
        lines.append(conclusion + caution)

    # ── GAME FINGERPRINT ──────────────────────────────────────────

    elif ftype == "fingerprint_cluster":
        gc         = data["games"]
        wins_c     = data["wins"]
        losses_c   = data["losses"]
        wr         = data["winrate"]
        conditions = data.get("conditions", [])

        lines.append(f"  [{label}] Game Pattern Cluster  —  {wins_c}W {losses_c}L ({wr}% WR across {gc} games)")
        lines.append(f"  When all of these are true:")
        for c in conditions:
            lines.append(f"    — {c}")
        if wr <= 30:
            conclusion = pick([
                f"  This specific combination is reliably losing for you. When these conditions align, the game goes one direction.",
                f"  The data has identified a losing fingerprint. In this exact situation, play differently or avoid it.",
                f"  {losses_c} losses out of {gc} games with these exact conditions. This is not variance.",
            ], wr)
        else:
            conclusion = pick([
                f"  This combination reliably produces wins. Recreate these conditions intentionally.",
                f"  Your winning fingerprint is identified. When these align, you perform.",
                f"  {wins_c} wins out of {gc} games with these conditions. This is your formula.",
            ], wr)
        lines.append(conclusion + caution)

    # ── EARLY GAME TEMPO ──────────────────────────────────────────

    elif ftype == "tempo_score":
        strong_n  = data["strong_games"]
        strong_wr = data["strong_wr"]
        weak_n    = data["weak_games"]
        weak_wr   = data["weak_wr"]
        mid_n     = data.get("mid_games", 0)
        mid_wr    = data.get("mid_wr")
        spread    = data["spread"]
        threw     = data.get("threw_from_strong", 0)
        won_weak  = data.get("won_from_weak", 0)

        lines.append(f"  [{label}] Early Game Tempo Score")
        lines.append(f"  Strong early games ({strong_n}):  {strong_wr}% WR")
        if mid_n and mid_wr:
            lines.append(f"  Average early games ({mid_n}): {mid_wr}% WR")
        lines.append(f"  Weak early games ({weak_n}):    {weak_wr}% WR")
        lines.append(f"  Spread: {spread}%")
        if threw >= 3:
            lines.append(f"  Note: {threw} strong early games still lost — leads are being thrown.")
        if won_weak >= 3:
            lines.append(f"  Note: {won_weak} weak early games still won — comeback ability is real.")
        conclusion = pick_magnitude({
            "low": [
                f"  Your early game performance moderately predicts results. Strong early helps but is not definitive.",
                f"  The early game matters in your data but the {spread}% spread suggests other factors decide games too.",
            ],
            "mid": [
                f"  The early game tempo score reliably predicts your results. Strong early games win. Weak ones lose.",
                f"  {spread}% winrate spread between strong and weak early games. The first 15 minutes are the game.",
                f"  Your early game performance and your result are strongly linked. Protect the early tempo.",
            ],
            "high": [
                f"  {spread}% spread. Your early game tempo essentially determines the outcome. The most predictive single number in your data.",
                f"  When your early game is strong you win. When it is weak you lose. At {spread}% this is near-deterministic.",
                f"  The early game tempo score is the clearest predictor of your results. Everything else is downstream.",
            ],
        }, spread, spread, (20, 40))
        lines.append(conclusion + caution)

    elif ftype == "queue_split":
        data_ = data
        better = data_["better"]
        solo_n = data_["solo_games"]
        flex_n = data_["flex_games"]
        gap = data_["gap"]

        lines.append(f"  [{label}] Queue Performance Gap")
        lines.append(f"  Solo/Duo ({solo_n} games): {data_['solo_wr']}% WR")
        lines.append(f"  Flex     ({flex_n} games): {data_['flex_wr']}% WR")
        lines.append(f"  Gap: {gap}%")

        if better == "Solo/Duo":
            lines.append(f"  You perform significantly better in Solo/Duo. When you want to climb, queue Solo.")
        else:
            lines.append(f"  Your Flex winrate is stronger. Your coordinated play outperforms your solo carry.")
        lines.append(f"  These are different games. Analyzing them together dilutes both signals.{caution}")

    elif ftype == "rift_herald_correlation":
        lines.append(f"  [{label}] Rift Herald Correlation")
        lines.append(f"  Games where your team took Rift Herald ({data['took_games']}): {data['took_wr']}% WR")
        lines.append(f"  Games where your team skipped it       ({data['skipped_games']}): {data['skipped_wr']}% WR")
        lines.append(f"  Gap: {data['gap']}%")
        if data["gap"] > 0:
            lines.append(f"  Rift Herald correlates with wins when you are ahead or stable. Use it as a conversion tool — not as a replacement for winning the early CS and gold race.{caution}")
        else:
            lines.append(f"  Taking Rift Herald is not producing wins. It may be costing time that could be spent elsewhere.{caution}")

    elif ftype == "map_side":
        d = data
        lines.append(f"  [{label}] Map Side Winrate Gap")
        lines.append(f"  Blue side ({d['blue_games']} games): {d['blue_wr']}% WR")
        lines.append(f"  Red side  ({d['red_games']} games): {d['red_wr']}% WR")
        lines.append(f"  Gap: {d['gap']}%")
        if d["better"] == "blue":
            lines.append(f"  You win significantly more on blue side. Prioritize blue-side picks and draft comfort.{caution}")
        else:
            lines.append(f"  You win significantly more on red side. Your counter-pick advantage may be contributing.{caution}")

    return lines

# ─────────────────────────────────────────────
# MAIN OUTPUT
# ─────────────────────────────────────────────

def _summary_insight(finding):
    """Convert a finding into a plain-language priority action."""
    ftype = finding["type"]
    data  = finding.get("data", {})

    if ftype == "cs_differential":
        win_d  = round(data.get("win_avg_diff", 0))
        loss_d = round(data.get("loss_avg_diff", 0))
        return f"Win the CS race — you average {loss_d} CS vs your counterpart in losses vs {win_d:+} in wins. The farm battle decides the game."
    elif ftype == "damage_differential":
        loss_d = round(data.get("loss_avg_diff", 0))
        role_label = data.get("role_label", "enemy counterpart")
        return f"Trade better and deal more damage — you're down {abs(loss_d):,} damage vs enemy in losses. The {role_label.lower()} is the bigger threat in fights."
    elif ftype == "kills_differential":
        loss_d = round(data.get("loss_avg_diff", 0), 1)
        role_label = data.get("role_label", "enemy jungler")
        if abs(loss_d) < 0.5:
            return None  # Not meaningful enough to surface
        return f"Stop farming while they're taking kills — {role_label.lower()} averages {abs(loss_d)} more kills than you in losses. Skirmish when ahead, not just at camp timers."
    elif ftype == "delta_gold_lead_15":
        gap = data.get("delta", 0)
        return f"Win the early economy — {round(gap)} gold gap at 15min separates wins from losses. That is a component item. Early pathing matters."
    elif ftype == "first_item_underperform":
        item = data.get("item", "that item")
        wr   = data.get("winrate", 0)
        return f"Stop starting {item} — {wr}% winrate. Change the first item."
    elif ftype == "pattern_invaded_early":
        pct = data.get("pct", 0)
        return f"Get invaded less — {pct}% of losses start with early deaths and low CS. Ward second buff entrance before your first clear."
    elif ftype == "causal_ahead_threw":
        pct = data.get("pct", 0)
        return f"Convert your leads — you throw {pct}% of games where you were ahead at 15. Take objectives, not fights."
    elif ftype == "fingerprint_cluster":
        wr = data.get("winrate", 0)
        return f"Avoid your losing fingerprint — {wr}% WR when your game matches this exact pattern. Change something upstream."
    elif ftype == "matchup_bad":
        matchups = data.get("matchups", [])
        worst = matchups[0]["champion"] if matchups else "certain matchups"
        return f"Study your losing matchups — {worst} in particular. You have a consistent losing record that is not variance."
    elif ftype == "causal_invaded_snowball":
        pct = data.get("pct", 0)
        return f"Protect your early jungle — {pct}% of losses follow the invasion chain. One ward before your second buff changes the result."
    elif ftype == "short_loss_pattern":
        pct = data.get("pct", 0)
        return f"Survive early — {pct}% of losses end before 22 minutes. These are not close games. The issue is in the first 15 minutes."
    elif ftype == "trend_loss_streak":
        streak = data.get("streak", 0)
        return f"Take a break — {streak}-game loss streak. Reset before continuing."
    elif ftype == "causal_team_feed_unwinnable":
        pct = data.get("pct", 0)
        return f"Recognize unwinnable games early — {pct}% of losses your farm was fine but your team collapsed. Stop forcing carries and cut tilt losses short."
    elif ftype == "causal_no_vision_objectives":
        pct = data.get("pct", 0)
        return f"Place control wards — {pct}% of losses had 0 wards and enemy freely stacked drakes. One ward changes what you can contest."
    elif ftype == "causal_comeback_wins":
        pct = data.get("pct", 0)
        return f"Your comeback ability is real — {pct}% of wins came from behind at 15. Don't surrender the mental when you're down early."
    elif ftype == "causal_cs_recovery":
        rec_wr  = data.get("recovered_wr", 0)
        nrec_wr = data.get("nrecovered_wr", 0)
        return f"Recover CS after falling behind — when you close the farm gap by 15min you win {rec_wr}% vs {nrec_wr}% when you don't. Farm through pressure."
    elif ftype == "matchup_good":
        matchups = data.get("matchups", [])
        if matchups:
            top = matchups[0]
            return f"Seek out {top['champion']} — you have a winning record against them. Queue into these matchups when you can."
        return None
    elif ftype == "causal_ahead_threw":
        pct = data.get("pct", 0)
        return f"Convert leads into objectives not fights — you throw {pct}% of games where you were ahead at 15. Take towers and drakes."
    elif ftype == "tempo_score":
        spread = data.get("spread", 0)
        return f"Your early game determines everything — {spread}% WR spread between strong and weak starts. Protect the first 15 minutes."
    elif ftype == "vision_dragon_correlation":
        diff = data.get("dragon_diff", 0)
        return f"Ward for dragon — {diff}% more dragon control when you place control wards. Direct line from your ward to your team's objectives."
    elif ftype == "trend_declining":
        diff = abs(data.get("diff", 0))
        return f"Take a break — performance dropped {diff}% over your last 10 games. Reset before the decline extends."
    elif ftype == "trend_loss_streak":
        streak = data.get("streak", 0)
        return f"Stop the streak — {streak} consecutive losses. One session break is worth more than one more game right now."
    elif ftype == "matchup_bad":
        matchups = data.get("matchups", [])
        worst = matchups[0]["champion"] if matchups else "certain matchups"
        return f"Study your losing matchups — {worst} specifically. Adjust your approach or consider a counter pick."
    else:
        return finding.get("title", ftype)

def print_diagnosis(games, findings, champion_filter=None):
    wins   = [g for g in games if g["win"]]
    losses = [g for g in games if not g["win"]]
    wr     = round(len(wins) / len(games) * 100, 1) if games else 0

    header = "FaceCheck Diagnosis"
    if champion_filter:
        header += f" — {champion_filter}"

    print(f"\n  {'='*60}")
    print(f"  {header}")
    print(f"  {'='*60}")
    print(f"  Games analyzed: {len(games)}  |  {len(wins)}W {len(losses)}L  |  {wr}% WR")
    solo_games = [g for g in games if g.get("queue_id") == 420]
    flex_games  = [g for g in games if g.get("queue_id") == 440]
    if solo_games and flex_games:
        solo_wr = round(sum(1 for g in solo_games if g["win"]) / len(solo_games) * 100, 1)
        flex_wr = round(sum(1 for g in flex_games if g["win"]) / len(flex_games) * 100, 1)
        print(f"  Solo/Duo: {len(solo_games)}g {solo_wr}%  |  Flex: {len(flex_games)}g {flex_wr}%")
    print(f"  {'='*60}\n")

    if not findings:
        if len(games) < 15:
            print("  Not enough games to detect patterns reliably.")
            print(f"  {len(games)} games analyzed — patterns emerge around 20+.")
            print("  Run: face fetch 50")
        else:
            print("  No significant patterns detected.")
            print("  Your performance is consistent across wins and losses.")
            print("  Play more ranked games and re-run to see if patterns develop.")
        return

    # ── DECISION BRIEF ─────────────────────────────────────────
    primary   = [f for f in findings
                 if f.get("control_level") == "direct"
                 and f.get("confidence_label") in ("CRITICAL", "CLEAR")
                 and f.get("action_type") not in ("context",)]
    secondary = [f for f in findings
                 if f.get("control_level") in ("direct", "indirect")
                 and f not in primary
                 and f.get("confidence_label") in ("CRITICAL", "CLEAR", "NOTABLE")]
    context   = [f for f in findings
                 if f.get("control_level") == "none"
                 or f.get("action_type") == "context"]

    primary.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    primary = primary[:3]
    secondary.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    secondary = secondary[:4]

    if primary or secondary or context:
        print(f"  ── DECISION BRIEF {'─'*44}")
        print()
        if primary:
            print(f"  PRIMARY — Fix these first:")
            for f in primary:
                atype = f.get("action_type", "").upper().replace("_", " ")
                insight = _summary_insight(f)
                if insight:
                    print(f"  !! [{atype}] {insight}")
            print()
        if secondary:
            print(f"  SECONDARY — Contributing factors:")
            for f in secondary:
                atype = f.get("action_type", "").upper().replace("_", " ")
                insight = _summary_insight(f)
                if insight:
                    print(f"   → [{atype}] {insight}")
            print()
        if context:
            ctx_insights = [_summary_insight(f) for f in context]
            ctx_insights = [c for c in ctx_insights if c]
            if ctx_insights:
                print(f"  CONTEXT — Do not overweight:")
                for ci in ctx_insights[:3]:
                    print(f"   ~ {ci}")
            print()
        print(f"  {'─'*60}")
        print()

    by_category = {}
    for f in findings:
        cat = f["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(f)

    # Patterns first, then metrics
    category_order = ["Causal Chain", "Pattern", "Trend", "Queue Split", "Map Side", "Build", "Early Game", "Early Game Tempo", "Performance", "Champion", "Enemy Matchup", "Matchup Intelligence", "Vision-Objectives", "Game Fingerprint"]

    # Pre-compute all fired types for cross-context language
    all_fired_types = {f["type"] for f in findings}
    for f in findings:
        f["_fired_types"] = all_fired_types

    for category in category_order:
        if category not in by_category:
            continue
        cat_findings = by_category[category]
        cat_findings.sort(key=lambda x: SEVERITY_ORDER.get(x["confidence_label"], 99))

        print(f"  ── {CATEGORY_HEADERS.get(category, category)} {'─'*40}")
        print()

        for finding in cat_findings:
            lines = format_finding(finding)
            if lines:
                for line in lines:
                    print(line)
                print()

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from facecheck_data import load_cache, CACHE_PATH
    from facecheck_analysis import run_analysis

    cache = load_cache()
    games = cache.get("games", [])

    if not games:
        print("No cached games found. Run: facecheck-fetch")
        sys.exit(1)

    champion_filter = None
    count_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        if arg.isdigit():
            count_filter = int(arg)
        else:
            champion_filter = arg

    # Filter to ranked only, then champion, then count
    ranked = [g for g in games if g.get("queue_id") in (420, 440)]
    if champion_filter:
        ranked = [g for g in ranked if g["champion"].lower() == champion_filter.lower()]
    if count_filter:
        ranked = ranked[:count_filter]

    findings = run_analysis(ranked)
    print_diagnosis(ranked, findings, champion_filter=champion_filter)
