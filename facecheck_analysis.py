from collections import defaultdict, Counter
import statistics

# ─────────────────────────────────────────────
# CONFIDENCE SYSTEM
# ─────────────────────────────────────────────

def confidence_score(sample_size, effect_size, consistency=1.0):
    if sample_size < 3:
        return 0.0
    sample_weight = min(1.0, (sample_size - 2) / 8)
    effect_weight = min(1.0, effect_size)
    score = sample_weight * 0.4 + effect_weight * 0.4 + consistency * 0.2
    return round(score, 2)

def confidence_label(score):
    if score >= 0.85:
        return "CRITICAL"
    elif score >= 0.65:
        return "CLEAR"
    elif score >= 0.45:
        return "NOTABLE"
    else:
        return "WEAK"

def confidence_voice(score):
    if score >= 0.85: return "high"
    elif score >= 0.65: return "medium"
    elif score >= 0.45: return "low"
    else: return None

# ─────────────────────────────────────────────
# DATASET HELPERS
# ─────────────────────────────────────────────

def split_by_result(games):
    return [g for g in games if g["win"]], [g for g in games if not g["win"]]

def robust_avg(values):
    values = [v for v in values if v is not None]
    if not values: return None
    if len(values) < 3:
        return round(statistics.median(values), 2)
    if len(values) < 15:
        # Smooth blend: median for small samples, trending toward mean
        median = statistics.median(values)
        mean = statistics.mean(values)
        weight = (len(values) - 3) / 12  # 0 at n=3, 1.0 at n=15
        blended = median * (1 - weight) + mean * weight
        return round(blended, 2)
    return round(statistics.mean(values), 2)

def winrate(games):
    if not games: return None
    return round(sum(1 for g in games if g["win"]) / len(games) * 100, 1)

def delta_pct(win_val, loss_val):
    if win_val is None or loss_val is None: return 0
    if win_val == loss_val: return 0
    max_val = max(abs(win_val), abs(loss_val))
    if max_val == 0: return 0
    return abs(win_val - loss_val) / max_val

def derive_primary_role(games):
    """Returns the most common role in the game set, or 'JUNGLE' as fallback."""
    from collections import Counter
    roles = [g.get("role", "") for g in games if g.get("role")]
    if not roles:
        return "JUNGLE"
    most_common = Counter(roles).most_common(1)[0][0]
    return most_common

ROLE_DISPLAY = {
    "JUNGLE":  "Enemy Jungler",
    "TOP":     "Enemy Top Laner",
    "MIDDLE":  "Enemy Mid Laner",
    "BOTTOM":  "Enemy ADC",
    "UTILITY": "Enemy Support",
}

# ─────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────

def deduplicate_findings(findings):
    fired_types = {f["type"] for f in findings}
    # Build confidence map — only suppress if the suppressor is at least as confident
    conf_map = {f["type"]: f["confidence"] for f in findings}
    suppressed = set()

    # Only suppress cs_final if cs_per_min is CLEAR or above
    if "delta_cs_per_min" in fired_types:
        if conf_map.get("delta_cs_per_min", 0) >= 0.65:
            suppressed.add("delta_cs_final")

    # Only suppress deaths if early_deaths is CRITICAL
    if "delta_early_deaths" in fired_types:
        if conf_map.get("delta_early_deaths", 0) >= 0.85:
            suppressed.add("delta_deaths")

    # Causal chains suppress their component metrics only if chain is CLEAR or above
    pattern_types = {f["type"] for f in findings if f.get("category") == "Pattern"}
    causal_types  = {f["type"] for f in findings if f.get("category") == "Causal Chain"}

    if "causal_invaded_snowball" in causal_types and conf_map.get("causal_invaded_snowball", 0) >= 0.65:
        suppressed.add("delta_early_deaths")
        suppressed.add("cs15_gap")
    elif "pattern_invaded_early" in pattern_types and conf_map.get("pattern_invaded_early", 0) >= 0.85:
        suppressed.add("delta_early_deaths")
        suppressed.add("cs15_gap")

    if "causal_ahead_threw" in causal_types and conf_map.get("causal_ahead_threw", 0) >= 0.65:
        suppressed.add("delta_deaths")

    if "pattern_won_jungle_lost_game" in pattern_types and conf_map.get("pattern_won_jungle_lost_game", 0) >= 0.85:
        suppressed.add("delta_deaths")

    return [f for f in findings if f["type"] not in suppressed]

# ─────────────────────────────────────────────
# MODULE 1: BUILD ANALYSIS
# ─────────────────────────────────────────────

def analyze_builds(games):
    findings = []
    if len(games) < 5: return findings

    wins, losses = split_by_result(games)

    first_item_games = defaultdict(list)
    for g in games:
        if g.get("first_item"):
            first_item_games[g["first_item"]].append(g)

    item_wr_map = {
        item: winrate(ig)
        for item, ig in first_item_games.items()
        if len(ig) >= 3
    }
    best_item = max(item_wr_map.items(), key=lambda x: x[1] if x[1] else 0, default=(None, None))

    for item, item_games in first_item_games.items():
        if len(item_games) < 3: continue
        wr = item_wr_map.get(item)
        item_wins = [g for g in item_games if g["win"]]
        item_losses = [g for g in item_games if not g["win"]]
        if wr is not None and wr < 45 and len(item_losses) >= len(item_wins):
            effect = (50 - wr) / 50
            conf = confidence_score(len(item_games), effect)
            voice = confidence_voice(conf)
            if voice:
                best_name, best_wr = best_item
                comparison = ""
                if best_name and best_name != item and best_wr:
                    best_n = len(first_item_games[best_name])
                    comparison = f"{best_name} first: {best_n} games, {best_wr}% winrate."
                findings.append({
                    "category": "Build",
                    "type": "first_item_underperform",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": f"First Item: {item}",
                    "data": {
                        "item": item, "games": len(item_games),
                        "wins": len(item_wins), "losses": len(item_losses),
                        "winrate": wr, "comparison": comparison,
                    }
                })

    win_first = [g["first_item"] for g in wins if g.get("first_item")]
    loss_first = [g["first_item"] for g in losses if g.get("first_item")]
    if win_first and loss_first:
        win_top = Counter(win_first).most_common(1)
        loss_top = Counter(loss_first).most_common(1)
        if win_top and loss_top:
            wi, wc = win_top[0]
            li, lc = loss_top[0]
            if wi != li and wc >= 3 and lc >= 3:
                wi_wr = item_wr_map.get(wi, 50)
                li_wr = item_wr_map.get(li, 50)
                effect = abs(wi_wr - li_wr) / 100 if wi_wr and li_wr else 0.5
                conf = confidence_score(min(wc, lc), effect)
                voice = confidence_voice(conf)
                if voice:
                    findings.append({
                        "category": "Build", "type": "build_divergence",
                        "confidence": conf, "confidence_label": confidence_label(conf),
                        "voice": voice, "title": "Build Path Divergence",
                        "data": {"win_item": wi, "win_count": wc, "win_item_wr": wi_wr,
                                 "loss_item": li, "loss_count": lc, "loss_item_wr": li_wr}
                    })
    return findings

# ─────────────────────────────────────────────
# MODULE 2: PERFORMANCE DELTA
# ─────────────────────────────────────────────

def analyze_performance_delta(games):
    findings = []
    if len(games) < 5: return findings
    wins, losses = split_by_result(games)
    if not wins or not losses: return findings

    metrics = [
        ("cs_final",       "CS",                  "higher", 0.20),
        ("cs_per_min",     "CS/min",              "higher", 0.10),
        ("deaths",         "Deaths",              "lower",  0.20),
        ("early_deaths",   "Deaths before 15min", "lower",  0.15),
        ("vision_per_min", "Vision/min",          "higher", 0.10),
        ("damage_per_min", "Damage/min",          "higher", 0.20),
        ("gold_per_min",   "Gold/min",            "higher", 0.15),
        ("gold_lead_15",   "Gold Lead at 15min",  "higher", 0.15),
    ]

    for key, label, direction, threshold in metrics:
        win_vals = [g[key] for g in wins if g.get(key) is not None]
        loss_vals = [g[key] for g in losses if g.get(key) is not None]
        if len(win_vals) < 3 or len(loss_vals) < 3: continue
        win_avg = robust_avg(win_vals)
        loss_avg = robust_avg(loss_vals)
        if win_avg is None or loss_avg is None: continue
        d = delta_pct(win_avg, loss_avg)
        meaningful = (loss_avg > win_avg and d > threshold) if direction == "lower" else (win_avg > loss_avg and d > threshold)
        if not meaningful: continue
        conf = confidence_score(min(len(win_vals), len(loss_vals)), d)
        voice = confidence_voice(conf)
        if voice:
            # Mark timeline-dependent metrics
            requires_timeline = key in ("early_deaths", "gold_lead_15")
            findings.append({
                "category": "Performance", "type": f"delta_{key}",
                "confidence": conf, "confidence_label": confidence_label(conf),
                "voice": voice, "title": f"{label} Gap",
                "requires_timeline": requires_timeline,
                "data": {"metric": label, "win_avg": win_avg, "loss_avg": loss_avg,
                         "delta": round(abs(win_avg - loss_avg), 2), "direction": direction,
                         "win_sample": len(win_vals), "loss_sample": len(loss_vals)}
            })
    return findings

# ─────────────────────────────────────────────
# MODULE 3: EARLY GAME
# ─────────────────────────────────────────────

def analyze_early_game(games):
    findings = []
    if len(games) < 5: return findings
    wins, losses = split_by_result(games)
    if not losses: return findings

    short_losses = [g for g in losses if g["duration_min"] < 22]
    if len(short_losses) >= 3:
        pct = len(short_losses) / len(losses) * 100
        if pct > 35:
            conf = confidence_score(len(short_losses), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Early Game", "type": "short_loss_pattern",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Early Surrender Pattern",
                    "data": {
                        "short_losses": len(short_losses), "total_losses": len(losses),
                        "pct": round(pct, 1),
                        "avg_cs_15": robust_avg([g["cs_15"] for g in short_losses if g.get("cs_15")]),
                        "avg_early_deaths": robust_avg([g["early_deaths"] for g in short_losses if g.get("early_deaths") is not None]),
                    }
                })

    cs15_wins = [g["cs_15"] for g in wins if g.get("cs_15") is not None]
    cs15_losses = [g["cs_15"] for g in losses if g.get("cs_15") is not None]
    if len(cs15_wins) >= 3 and len(cs15_losses) >= 3:
        wc = robust_avg(cs15_wins)
        lc = robust_avg(cs15_losses)
        d = delta_pct(wc, lc)
        if wc > lc and d > 0.2:
            conf = confidence_score(min(len(cs15_wins), len(cs15_losses)), d)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Early Game", "type": "cs15_gap",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "CS at 15min Gap",
                    "requires_timeline": True,
                    "data": {"win_avg": wc, "loss_avg": lc, "delta": round(wc - lc, 1),
                             "win_sample": len(cs15_wins), "loss_sample": len(cs15_losses)}
                })
    return findings

# ─────────────────────────────────────────────
# MODULE 4: CHAMPION ANALYSIS
# ─────────────────────────────────────────────

def analyze_champions(games):
    findings = []
    if len(games) < 5: return findings
    champ_games = defaultdict(list)
    for g in games:
        champ_games[g["champion"]].append(g)
    champ_winrates = {
        c: (winrate(cg), len(cg))
        for c, cg in champ_games.items() if len(cg) >= 3
    }
    if len(champ_winrates) < 2: return findings
    sorted_champs = sorted(champ_winrates.items(), key=lambda x: x[1][0] if x[1][0] is not None else 0)
    worst_champ, (worst_wr, worst_n) = sorted_champs[0]
    best_champ, (best_wr, best_n) = sorted_champs[-1]
    if worst_champ == best_champ or worst_wr is None or best_wr is None: return findings
    if worst_wr < 40:
        effect = (best_wr - worst_wr) / 100
        conf = confidence_score(min(worst_n, best_n), effect)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Champion", "type": "champion_winrate_gap",
                "confidence": conf, "confidence_label": confidence_label(conf),
                "voice": voice, "title": "Champion Performance Gap",
                "data": {"worst_champ": worst_champ, "worst_wr": worst_wr, "worst_games": worst_n,
                         "best_champ": best_champ, "best_wr": best_wr, "best_games": best_n}
            })
    return findings

# ─────────────────────────────────────────────
# MODULE 5: ENEMY COMPARISON
# ─────────────────────────────────────────────

def analyze_enemy_comparison(games):
    findings = []
    games_e = [g for g in games if g.get("enemy")]
    if len(games_e) < 5: return findings
    wins_e = [g for g in games_e if g["win"]]
    losses_e = [g for g in games_e if not g["win"]]
    if not wins_e or not losses_e: return findings

    role = derive_primary_role(games)
    role_label = ROLE_DISPLAY.get(role, "Enemy Counterpart")

    for my_key, ekey, label, threshold in [
        ("cs_final", "cs", "CS", 0.20),
        ("damage", "damage", "Damage", 0.25),
        ("kills", "kills", "Kills", 0.30),
    ]:
        win_diff = [g[my_key] - g["enemy"][ekey] for g in wins_e if g.get(my_key) and g["enemy"].get(ekey) is not None]
        loss_diff = [g[my_key] - g["enemy"][ekey] for g in losses_e if g.get(my_key) and g["enemy"].get(ekey) is not None]
        win_d = robust_avg(win_diff)
        loss_d = robust_avg(loss_diff)
        if win_d is None or loss_d is None or win_d <= loss_d: continue
        d = delta_pct(win_d, loss_d)
        if d <= threshold: continue
        swing = round(abs(win_d) + abs(loss_d), 1) if loss_d < 0 else round(win_d - loss_d, 1)
        conf = confidence_score(min(len(win_diff), len(loss_diff)), d)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Enemy Matchup", "type": f"{label.lower()}_differential",
                "confidence": conf, "confidence_label": confidence_label(conf),
                "voice": voice, "title": f"{label} Differential vs Enemy",
                "data": {"label": label, "win_avg_diff": win_d, "loss_avg_diff": loss_d,
                         "total_swing": swing, "win_sample": len(win_diff), "loss_sample": len(loss_diff),
                         "role_label": role_label}
            })
    return findings

# ─────────────────────────────────────────────
# MODULE 6: PATTERN LIBRARY
# ─────────────────────────────────────────────

def analyze_patterns(games):
    findings = []
    if len(games) < 8: return findings
    wins, losses = split_by_result(games)
    if not losses: return findings

    # Invaded early
    invaded = [g for g in losses if
               g.get("early_deaths", 0) >= 2 and
               g.get("cs_15") is not None and g.get("cs_15", 999) < 65 and
               g.get("duration_min", 99) < 28]
    if len(invaded) >= 3:
        pct = round(len(invaded) / len(losses) * 100, 1)
        if pct >= 25:
            conf = confidence_score(len(invaded), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Pattern", "type": "pattern_invaded_early",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Early Invasion Pattern",
                    "requires_timeline": True,
                    "data": {"count": len(invaded), "total_losses": len(losses), "pct": pct,
                             "avg_early_deaths": robust_avg([g.get("early_deaths", 0) for g in invaded]),
                             "avg_cs_15": robust_avg([g.get("cs_15") for g in invaded if g.get("cs_15")]),
                             "avg_duration": robust_avg([g["duration_min"] for g in invaded])}
                })

    # Won jungle lost game
    won_jungle = [g for g in losses if
                  g.get("enemy") and
                  g.get("cs_final", 0) >= g["enemy"].get("cs", 9999) * 0.9 and
                  g.get("deaths", 0) >= 6 and g.get("duration_min", 0) >= 28]
    if len(won_jungle) >= 3:
        pct = round(len(won_jungle) / len(losses) * 100, 1)
        if pct >= 20:
            conf = confidence_score(len(won_jungle), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Pattern", "type": "pattern_won_jungle_lost_game",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Won Jungle, Lost Game",
                    "data": {"count": len(won_jungle), "total_losses": len(losses), "pct": pct,
                             "avg_deaths": robust_avg([g["deaths"] for g in won_jungle]),
                             "avg_cs_diff": robust_avg([g["cs_final"] - g["enemy"]["cs"] for g in won_jungle])}
                })

    # Pure stomp
    stomps = [g for g in losses if
              g.get("enemy") and
              g.get("cs_final", 999) < g["enemy"].get("cs", 0) * 0.8 and
              g.get("damage", 999999) < g["enemy"].get("damage", 0) * 0.7 and
              g.get("kills", 999) < g["enemy"].get("kills", 0) and
              g.get("duration_min", 99) < 25]
    if len(stomps) >= 3:
        pct = round(len(stomps) / len(losses) * 100, 1)
        if pct >= 20:
            conf = confidence_score(len(stomps), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Pattern", "type": "pattern_pure_stomp",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Pure Stomp Pattern",
                    "data": {"count": len(stomps), "total_losses": len(losses), "pct": pct,
                             "avg_duration": robust_avg([g["duration_min"] for g in stomps])}
                })

    # Scaled but misplayed
    scaled = [g for g in losses if
              g.get("cs_per_min", 0) >= 5.5 and
              (g.get("kills", 0) + g.get("assists", 0)) >= 8 and
              g.get("deaths", 0) >= 7 and g.get("duration_min", 0) >= 30]
    if len(scaled) >= 3:
        pct = round(len(scaled) / len(losses) * 100, 1)
        if pct >= 20:
            conf = confidence_score(len(scaled), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Pattern", "type": "pattern_scaled_misplayed",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Scaled But Misplayed",
                    "data": {"count": len(scaled), "total_losses": len(losses), "pct": pct,
                             "avg_kp": robust_avg([(g["kills"] + g["assists"]) for g in scaled]),
                             "avg_deaths": robust_avg([g["deaths"] for g in scaled])}
                })

    # Vision deficit
    vis_wins = [g.get("vision_per_min", 0) for g in wins if g.get("vision_per_min") is not None]
    vis_losses = [g.get("vision_per_min", 0) for g in losses if g.get("vision_per_min") is not None]
    if len(vis_wins) >= 5 and len(vis_losses) >= 5:
        wv = robust_avg(vis_wins)
        lv = robust_avg(vis_losses)
        if wv and lv and lv < wv * 0.75:
            d = delta_pct(wv, lv)
            conf = confidence_score(min(len(vis_wins), len(vis_losses)), d)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Pattern", "type": "pattern_vision_deficit",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Vision Deficit in Losses",
                    "data": {"win_avg": wv, "loss_avg": lv, "delta": round(wv - lv, 2)}
                })

    # Dragon correlation
    games_obj = [g for g in games if g.get("my_team") and g.get("enemy_team")]
    if len(games_obj) >= 10:
        dragon_wins = [g for g in games_obj if g["win"] and
                       g["my_team"].get("dragon_kills", 0) > g["enemy_team"].get("dragon_kills", 0)]
        dragon_losses = [g for g in games_obj if not g["win"] and
                         g["enemy_team"].get("dragon_kills", 0) > g["my_team"].get("dragon_kills", 0)]
        total = len(games_obj)
        dwp = round(len(dragon_wins) / total * 100, 1)
        dlp = round(len(dragon_losses) / total * 100, 1)
        if dwp >= 40 and dlp >= 30:
            conf = confidence_score(total, (dwp + dlp) / 200)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Vision-Objectives", "type": "pattern_dragon_control",
                    "confidence": conf, "confidence_label": confidence_label(conf),
                    "voice": voice, "title": "Dragon Control Correlation",
                    "data": {"games": total, "win_dragon_pct": dwp, "loss_dragon_pct": dlp}
                })

    return findings

# ─────────────────────────────────────────────
# MODULE 7: CAUSAL CHAINS
# ─────────────────────────────────────────────

def analyze_causal_chains(games):
    """
    Detects connected sequences of events — not individual metrics
    but chains where one thing caused another.
    """
    findings = []
    if len(games) < 8: return findings
    wins, losses = split_by_result(games)
    if not losses: return findings

    # ── CHAIN 1: Invaded → CS Deficit → Gold Deficit → Loss ──────
    # All three symptoms present in same loss = one root cause
    invasion_chain = [g for g in losses if
                      g.get("early_deaths", 0) >= 2 and
                      (g.get("cs_15") or 999) < 65 and
                      (g.get("gold_lead_15") or 0) < -400]
    if len(invasion_chain) >= 3:
        pct = round(len(invasion_chain) / len(losses) * 100, 1)
        if pct >= 20:
            avg_ed = robust_avg([g["early_deaths"] for g in invasion_chain])
            avg_cs = robust_avg([g.get("cs_15") for g in invasion_chain if g.get("cs_15")])
            avg_gold = robust_avg([g.get("gold_lead_15") for g in invasion_chain if g.get("gold_lead_15") is not None])
            conf = confidence_score(len(invasion_chain), pct / 100, 0.9)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Causal Chain",
                    "type": "causal_invaded_snowball",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "Invasion → Farm Loss → Gold Deficit",
                    "requires_timeline": True,
                    "data": {
                        "count": len(invasion_chain),
                        "total_losses": len(losses),
                        "pct": pct,
                        "avg_early_deaths": avg_ed,
                        "avg_cs_15": avg_cs,
                        "avg_gold_lead_15": avg_gold,
                        "chain": ["Early deaths", "CS deficit at 15", "Gold deficit at 15", "Loss"],
                    }
                })

    # ── CHAIN 2: Gold Lead at 15 → But Lost (Throw Chain) ────────
    throws = [g for g in losses if (g.get("gold_lead_15") or 0) > 500]
    if len(throws) >= 3:
        pct = round(len(throws) / len(losses) * 100, 1)
        if pct >= 15:
            avg_gold_lead = robust_avg([g.get("gold_lead_15") for g in throws if g.get("gold_lead_15")])
            avg_deaths = robust_avg([g["deaths"] for g in throws])
            avg_duration = robust_avg([g["duration_min"] for g in throws])
            # What did the throws have in common?
            high_death_throws = [g for g in throws if g.get("deaths", 0) >= 7]
            obj_throws = [g for g in throws if
                          g.get("enemy_team", {}) and
                          g["enemy_team"].get("dragon_kills", 0) >= 3]
            conf = confidence_score(len(throws), pct / 100, 0.85)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Causal Chain",
                    "type": "causal_ahead_threw",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "Gold Lead → Thrown",
                    "requires_timeline": True,
                    "data": {
                        "count": len(throws),
                        "total_losses": len(losses),
                        "pct": pct,
                        "avg_gold_lead_15": avg_gold_lead,
                        "avg_deaths": avg_deaths,
                        "avg_duration": avg_duration,
                        "death_related": len(high_death_throws),
                        "objective_related": len(obj_throws),
                    }
                })

    # ── CHAIN 3: No Vision → Conceded Objectives → Lost ──────────
    vision_obj_chain = [g for g in losses if
                        g.get("control_wards", 0) == 0 and
                        g.get("enemy_team", {}) and
                        g["enemy_team"].get("dragon_kills", 0) >= 2 and
                        g.get("duration_min", 0) >= 25]
    if len(vision_obj_chain) >= 3:
        pct = round(len(vision_obj_chain) / len(losses) * 100, 1)
        if pct >= 20:
            avg_enemy_drakes = robust_avg([g["enemy_team"].get("dragon_kills", 0) for g in vision_obj_chain if g.get("enemy_team")])
            conf = confidence_score(len(vision_obj_chain), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Causal Chain",
                    "type": "causal_no_vision_objectives",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "No Vision → Conceded Objectives",
                    "data": {
                        "count": len(vision_obj_chain),
                        "total_losses": len(losses),
                        "pct": pct,
                        "avg_enemy_drakes": avg_enemy_drakes,
                        "chain": ["0 control wards", "Enemy secured dragons", "Map control lost", "Loss"],
                    }
                })

    # ── CHAIN 4: Team Feeding → Unwinnable Jungle ────────────────
    team_feed_chain = [g for g in losses if
                       g.get("my_team", {}) and
                       g["my_team"].get("deaths", 0) >= 25 and
                       g.get("cs_final", 0) >= 150]  # You were farming fine
    if len(team_feed_chain) >= 3:
        pct = round(len(team_feed_chain) / len(losses) * 100, 1)
        if pct >= 20:
            avg_team_deaths = robust_avg([g["my_team"].get("deaths", 0) for g in team_feed_chain if g.get("my_team")])
            avg_my_cs = robust_avg([g["cs_final"] for g in team_feed_chain])
            conf = confidence_score(len(team_feed_chain), pct / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Causal Chain",
                    "type": "causal_team_feed_unwinnable",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "Team Feeding → Unwinnable",
                    "data": {
                        "count": len(team_feed_chain),
                        "total_losses": len(losses),
                        "pct": pct,
                        "avg_team_deaths": avg_team_deaths,
                        "avg_my_cs": avg_my_cs,
                        "chain": ["Lanes feeding", "Map unplayable", "No comeback possible"],
                    }
                })

    # ── COMEBACK DETECTION ────────────────────────────────────────
    comebacks = [g for g in wins if (g.get("gold_lead_15") or 0) < -300]
    if len(comebacks) >= 3:
        pct_of_wins = round(len(comebacks) / len(wins) * 100, 1) if wins else 0
        avg_deficit = robust_avg([g.get("gold_lead_15") for g in comebacks if g.get("gold_lead_15") is not None])
        if pct_of_wins >= 15:
            conf = confidence_score(len(comebacks), pct_of_wins / 100)
            voice = confidence_voice(conf)
            if voice:
                findings.append({
                    "category": "Causal Chain",
                    "type": "causal_comeback_wins",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "Comeback Wins",
                    "data": {
                        "count": len(comebacks),
                        "total_wins": len(wins),
                        "pct": pct_of_wins,
                        "avg_gold_deficit_15": avg_deficit,
                    }
                })

    # ── CS RECOVERY RATE ──────────────────────────────────────────
    behind_early = [g for g in games if g.get("cs_10") is not None and g["cs_10"] < 55]
    if len(behind_early) >= 5:
        recovered     = [g for g in behind_early if g.get("cs_15") is not None and
                         g["cs_15"] - g["cs_10"] >= 25]
        not_recovered = [g for g in behind_early if g.get("cs_15") is not None and
                         g["cs_15"] - g["cs_10"] < 25]
        if len(recovered) >= 3 and len(not_recovered) >= 3:
            rec_wr  = round(sum(1 for g in recovered     if g["win"]) / len(recovered)     * 100, 1)
            nrec_wr = round(sum(1 for g in not_recovered if g["win"]) / len(not_recovered) * 100, 1)
            gap = round(rec_wr - nrec_wr, 1)
            if gap >= 20:
                conf  = confidence_score(min(len(recovered), len(not_recovered)), gap / 100)
                voice = confidence_voice(conf)
                if voice:
                    findings.append({
                        "category": "Causal Chain",
                        "type": "causal_cs_recovery",
                        "confidence": conf,
                        "confidence_label": confidence_label(conf),
                        "voice": voice,
                        "title": "CS Recovery Determines Outcome",
                        "data": {
                            "behind_games": len(behind_early),
                            "recovered_games": len(recovered),   "recovered_wr": rec_wr,
                            "nrecovered_games": len(not_recovered), "nrecovered_wr": nrec_wr,
                            "gap": gap,
                        }
                    })

    return findings

# ─────────────────────────────────────────────
# MODULE 8: ENEMY MATCHUP INTELLIGENCE
# ─────────────────────────────────────────────

def analyze_enemy_matchups(games):
    """
    Track which enemy champions you consistently win or lose against.
    Surfaces specific matchup advantages and disadvantages.
    """
    findings = []
    games_e = [g for g in games if g.get("enemy")]
    if len(games_e) < 10: return findings

    enemy_champ_games = defaultdict(list)
    for g in games_e:
        enemy_champ = g["enemy"]["champion"]
        enemy_champ_games[enemy_champ].append(g)

    worst_matchups = []
    best_matchups = []

    for champ, champ_games in enemy_champ_games.items():
        if len(champ_games) < 3: continue
        wr = winrate(champ_games)
        if wr is None: continue

        # Stats in these games
        avg_cs_diff = robust_avg([g["cs_final"] - g["enemy"]["cs"] for g in champ_games])
        avg_dmg_diff = robust_avg([g["damage"] - g["enemy"]["damage"] for g in champ_games])

        if wr <= 30:
            worst_matchups.append({
                "champion": champ,
                "games": len(champ_games),
                "winrate": wr,
                "avg_cs_diff": avg_cs_diff,
                "avg_dmg_diff": avg_dmg_diff,
            })
        elif wr >= 65:
            best_matchups.append({
                "champion": champ,
                "games": len(champ_games),
                "winrate": wr,
                "avg_cs_diff": avg_cs_diff,
                "avg_dmg_diff": avg_dmg_diff,
            })

    worst_matchups.sort(key=lambda x: x["winrate"])
    best_matchups.sort(key=lambda x: x["winrate"], reverse=True)

    if worst_matchups:
        conf = confidence_score(sum(m["games"] for m in worst_matchups[:3]), 0.7)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Matchup Intelligence",
                "type": "matchup_bad",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Losing Matchups",
                "data": {"matchups": worst_matchups[:3]}
            })

    if best_matchups:
        conf = confidence_score(sum(m["games"] for m in best_matchups[:3]), 0.7)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Matchup Intelligence",
                "type": "matchup_good",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Winning Matchups",
                "data": {"matchups": best_matchups[:3]}
            })

    return findings

# ─────────────────────────────────────────────
# MODULE 9: TIME TREND
# ─────────────────────────────────────────────

def analyze_time_trend(games):
    """
    Compare recent performance vs historical baseline.
    Detects improvement, decline, and tilt streaks.
    """
    findings = []
    if len(games) < 15: return findings

    recent = games[:10]
    historical = games[10:]

    if len(historical) < 5: return findings

    recent_wr = winrate(recent)
    historical_wr = winrate(historical)

    if recent_wr is None or historical_wr is None: return findings

    diff = round(recent_wr - historical_wr, 1)

    # Significant decline
    if diff <= -15 and recent_wr < 45:
        # Look for tilt pattern — consecutive losses
        recent_results = [g["win"] for g in recent]
        max_streak = 0
        current = 0
        for r in recent_results:
            if not r:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0

        conf = confidence_score(len(recent), abs(diff) / 100)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Trend",
                "type": "trend_declining",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Performance Declining",
                "data": {
                    "recent_wr": recent_wr,
                    "historical_wr": historical_wr,
                    "diff": diff,
                    "recent_games": len(recent),
                    "max_loss_streak": max_streak,
                }
            })

    # Significant improvement
    elif diff >= 15 and recent_wr >= 55:
        conf = confidence_score(len(recent), abs(diff) / 100)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Trend",
                "type": "trend_improving",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Performance Improving",
                "data": {
                    "recent_wr": recent_wr,
                    "historical_wr": historical_wr,
                    "diff": diff,
                    "recent_games": len(recent),
                }
            })

    # Tilt streak detection even without large WR diff
    recent_results = [g["win"] for g in recent[:7]]
    loss_streak = 0
    for r in recent_results:
        if not r:
            loss_streak += 1
        else:
            break

    if loss_streak >= 4:
        conf = confidence_score(loss_streak, loss_streak / 7)
        voice = confidence_voice(conf)
        if voice and not any(f["type"] == "trend_declining" for f in findings):
            findings.append({
                "category": "Trend",
                "type": "trend_loss_streak",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": f"{loss_streak}-Game Loss Streak",
                "data": {
                    "streak": loss_streak,
                    "recent_wr": recent_wr,
                }
            })

    return findings

# ─────────────────────────────────────────────
# MODULE 10: VISION-OBJECTIVE CORRELATION
# ─────────────────────────────────────────────

def analyze_vision_objectives(games):
    """
    Does placing control wards correlate with your team's dragon control?
    Direct line from individual action to team outcome.
    """
    findings = []
    games_full = [g for g in games if g.get("my_team") and g.get("enemy_team") and g.get("control_wards") is not None]
    if len(games_full) < 10: return findings

    warded = [g for g in games_full if g.get("control_wards", 0) >= 2]
    unwarded = [g for g in games_full if g.get("control_wards", 0) == 0]

    if len(warded) < 5 or len(unwarded) < 5: return findings

    # Dragon control rate with vs without wards
    def dragon_control_pct(game_list):
        controlled = [g for g in game_list if
                      g["my_team"].get("dragon_kills", 0) >= g["enemy_team"].get("dragon_kills", 0)]
        return round(len(controlled) / len(game_list) * 100, 1) if game_list else 0

    warded_dragon_pct = dragon_control_pct(warded)
    unwarded_dragon_pct = dragon_control_pct(unwarded)
    warded_wr = winrate(warded)
    unwarded_wr = winrate(unwarded)

    if warded_dragon_pct > unwarded_dragon_pct + 15:
        diff = round(warded_dragon_pct - unwarded_dragon_pct, 1)
        conf = confidence_score(min(len(warded), len(unwarded)), diff / 100)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Vision-Objectives",
                "type": "vision_dragon_correlation",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Control Wards → Dragon Control",
                "data": {
                    "warded_games": len(warded),
                    "unwarded_games": len(unwarded),
                    "warded_dragon_pct": warded_dragon_pct,
                    "unwarded_dragon_pct": unwarded_dragon_pct,
                    "dragon_diff": diff,
                    "warded_wr": warded_wr,
                    "unwarded_wr": unwarded_wr,
                }
            })

    return findings

# ─────────────────────────────────────────────
# MODULE 11: GAME FINGERPRINT
# ─────────────────────────────────────────────

def analyze_game_fingerprint(games):
    """
    Find clusters of similar games and their outcomes.
    Groups games by key condition buckets and surfaces patterns
    within each cluster.
    """
    findings = []
    if len(games) < 15: return findings

    def fingerprint(g):
        return (
            "early_invaded" if g.get("early_deaths", 0) >= 2 else "early_clean",
            "gold_ahead" if (g.get("gold_lead_15") or 0) > 200 else "gold_behind",
            "cs_strong" if (g.get("cs_15") or 0) >= 80 else "cs_weak",
            g.get("first_item") or "unknown",
            g["champion"],
        )

    clusters = defaultdict(list)
    for g in games:
        clusters[fingerprint(g)].append(g)

    # Find clusters with at least 5 games and meaningful winrate split
    interesting = []
    for fp, cluster_games in clusters.items():
        if len(cluster_games) < 5: continue
        wr = winrate(cluster_games)
        if wr is None: continue
        if wr <= 30 or wr >= 70:
            interesting.append((fp, cluster_games, wr))

    if not interesting: return findings

    interesting.sort(key=lambda x: abs(x[2] - 50), reverse=True)

    # Surface up to 2 clusters — worst losing and best winning
    losing_clusters  = [(fp, cg, wr) for fp, cg, wr in interesting if wr <= 30]
    winning_clusters = [(fp, cg, wr) for fp, cg, wr in interesting if wr >= 70]
    to_surface = (losing_clusters[:1] + winning_clusters[:1]) or interesting[:1]

    for top_fp, top_games, top_wr in to_surface:
        early, gold, cs, item, champ = top_fp
        wins_c   = [g for g in top_games if g["win"]]
        losses_c = [g for g in top_games if not g["win"]]

        conf  = confidence_score(len(top_games), abs(top_wr - 50) / 50)
        voice = confidence_voice(conf)
        if voice:
            conditions = []
            if early == "early_invaded": conditions.append("invaded early (2+ deaths before 15)")
            if gold  == "gold_behind":   conditions.append("behind in gold at 15")
            if cs    == "cs_weak":       conditions.append("weak CS at 15 (<80)")
            if item and item != "unknown": conditions.append(f"starting {item}")
            conditions.append(f"on {champ}")

            findings.append({
                "category": "Game Fingerprint",
                "type": "fingerprint_cluster",
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": "Game Pattern Cluster",
                "data": {
                    "games": len(top_games),
                    "wins":  len(wins_c),
                    "losses": len(losses_c),
                    "winrate": top_wr,
                    "conditions": conditions,
                    "champion": champ,
                    "first_item": item,
                }
            })

    return findings

# ─────────────────────────────────────────────
# VALIDATION PASS
# ─────────────────────────────────────────────

def validate_findings(findings, games):
    if len(games) < 10:
        for f in findings:
            f["validated"] = None
        return findings

    durations = sorted([g["duration_min"] for g in games])
    trim = max(1, len(durations) // 10)
    min_dur = durations[trim]
    max_dur = durations[-(trim + 1)]
    trimmed = [g for g in games if min_dur <= g["duration_min"] <= max_dur]

    if len(trimmed) < 5:
        for f in findings:
            f["validated"] = None
        return findings

    tw, tl = split_by_result(trimmed)

    validated = []
    for finding in findings:
        ftype = finding["type"]
        downgrade = False

        if ftype == "first_item_underperform":
            item = finding["data"]["item"]
            ig = [g for g in trimmed if g.get("first_item") == item]
            if len(ig) >= 3:
                wr = winrate(ig)
                if wr is not None and wr >= 45:
                    downgrade = True
                    finding["validated"] = False
                else:
                    finding["validated"] = True
            else:
                finding["validated"] = None

        elif ftype.startswith("delta_") and tw and tl:
            key = ftype.replace("delta_", "")
            direction = finding["data"].get("direction", "higher")
            twv = [g[key] for g in tw if g.get(key) is not None]
            tlv = [g[key] for g in tl if g.get(key) is not None]
            if len(twv) >= 3 and len(tlv) >= 3:
                ta = robust_avg(twv)
                tb = robust_avg(tlv)
                if ta is not None and tb is not None:
                    if direction == "higher" and tb >= ta:
                        downgrade = True
                        finding["validated"] = False
                    elif direction == "lower" and ta >= tb:
                        downgrade = True
                        finding["validated"] = False
                    else:
                        finding["validated"] = True
            else:
                finding["validated"] = None
        else:
            finding["validated"] = None

        if downgrade:
            finding["confidence"] = max(0, finding["confidence"] - 0.2)
            finding["confidence_label"] = confidence_label(finding["confidence"])
            finding["voice"] = confidence_voice(finding["confidence"])

        if finding.get("voice"):
            validated.append(finding)

    return validated

# ─────────────────────────────────────────────
# MODULE 13: DERIVED METRICS (KP / DEATH SHARE / DAMAGE SHARE)
# ─────────────────────────────────────────────

def analyze_participation(games):
    findings = []
    if len(games) < 8:
        return findings

    wins, losses = split_by_result(games)
    if not wins or not losses:
        return findings

    def kp(g):
        tk = g.get("my_team", {}).get("kills", 0)
        return (g["kills"] + g["assists"]) / max(tk, 1) if tk else None

    def death_share(g):
        td = g.get("my_team", {}).get("deaths", 0)
        return g["deaths"] / max(td, 1) if td else None

    def dmg_share(g):
        ally_dmg = sum(p["damage"] for p in g.get("all_players", []) if p.get("team") == "ally")
        return g["damage"] / max(ally_dmg, 1) if ally_dmg else None

    for key_fn, fname, label, direction in [
        (kp,          "delta_kill_participation", "Kill Participation", "higher"),
        (death_share, "delta_death_share",         "Death Share",        "lower"),
        (dmg_share,   "delta_damage_share",        "Damage Share",       "higher"),
    ]:
        win_vals  = [v for g in wins   if (v := key_fn(g)) is not None]
        loss_vals = [v for g in losses if (v := key_fn(g)) is not None]
        if len(win_vals) < 5 or len(loss_vals) < 5:
            continue
        wa = robust_avg(win_vals)
        la = robust_avg(loss_vals)
        if wa is None or la is None:
            continue
        d = delta_pct(wa, la)
        meaningful = (la > wa and d > 0.15) if direction == "lower" else (wa > la and d > 0.15)
        if not meaningful:
            continue
        conf  = confidence_score(min(len(win_vals), len(loss_vals)), d)
        voice = confidence_voice(conf)
        if voice:
            findings.append({
                "category": "Performance",
                "type": fname,
                "confidence": conf,
                "confidence_label": confidence_label(conf),
                "voice": voice,
                "title": f"{label} Gap",
                "data": {
                    "metric": label,
                    "win_avg": round(wa, 2),
                    "loss_avg": round(la, 2),
                    "delta": round(abs(wa - la), 2),
                    "direction": direction,
                    "win_sample": len(win_vals),
                    "loss_sample": len(loss_vals),
                }
            })
    return findings

# ─────────────────────────────────────────────
# MODULE 14: RIFT HERALD CORRELATION
# ─────────────────────────────────────────────

def analyze_rift_herald(games):
    findings = []
    games_rh = [g for g in games if g.get("my_team", {}).get("rift_herald_kills") is not None]
    if len(games_rh) < 10:
        return findings

    took_rh    = [g for g in games_rh if g["my_team"].get("rift_herald_kills", 0) >= 1]
    skipped_rh = [g for g in games_rh if g["my_team"].get("rift_herald_kills", 0) == 0]

    if len(took_rh) < 5 or len(skipped_rh) < 5:
        return findings

    took_wr    = round(sum(1 for g in took_rh    if g["win"]) / len(took_rh)    * 100, 1)
    skipped_wr = round(sum(1 for g in skipped_rh if g["win"]) / len(skipped_rh) * 100, 1)
    gap = round(took_wr - skipped_wr, 1)

    if abs(gap) < 15:
        return findings

    conf  = confidence_score(min(len(took_rh), len(skipped_rh)), abs(gap) / 100)
    voice = confidence_voice(conf)
    if voice:
        findings.append({
            "category": "Vision-Objectives",
            "type": "rift_herald_correlation",
            "confidence": conf,
            "confidence_label": confidence_label(conf),
            "voice": voice,
            "title": "Rift Herald Correlation",
            "data": {
                "took_games": len(took_rh),    "took_wr": took_wr,
                "skipped_games": len(skipped_rh), "skipped_wr": skipped_wr,
                "gap": gap,
            }
        })
    return findings

# ─────────────────────────────────────────────
# MODULE 15: QUEUE SPLIT ANALYSIS
# ─────────────────────────────────────────────


def analyze_queue_split(games):
    from collections import defaultdict
    findings = []
    by_queue = defaultdict(list)
    for g in games:
        qid = g.get("queue_id")
        if qid in (420, 440):
            by_queue[qid].append(g)

    solo = by_queue.get(420, [])
    flex = by_queue.get(440, [])

    if len(solo) < 5 or len(flex) < 5:
        return findings

    solo_wr = round(sum(1 for g in solo if g["win"]) / len(solo) * 100, 1)
    flex_wr = round(sum(1 for g in flex if g["win"]) / len(flex) * 100, 1)
    gap = round(abs(solo_wr - flex_wr), 1)

    if gap < 10:
        return findings

    better = "Solo/Duo" if solo_wr > flex_wr else "Flex"
    worse  = "Flex" if solo_wr > flex_wr else "Solo/Duo"
    better_wr = max(solo_wr, flex_wr)
    worse_wr  = min(solo_wr, flex_wr)

    conf = confidence_score(min(len(solo), len(flex)), gap / 100)
    voice = confidence_voice(conf)
    if voice:
        findings.append({
            "category": "Queue Split",
            "type": "queue_split",
            "confidence": conf,
            "confidence_label": confidence_label(conf),
            "voice": voice,
            "title": "Queue Performance Gap",
            "data": {
                "solo_games": len(solo), "solo_wr": solo_wr,
                "flex_games": len(flex), "flex_wr": flex_wr,
                "gap": gap, "better": better, "worse": worse,
                "better_wr": better_wr, "worse_wr": worse_wr,
            }
        })
    return findings

# ─────────────────────────────────────────────
# MODULE 14: MAP SIDE ANALYSIS
# ─────────────────────────────────────────────

def analyze_map_side(games):
    findings = []
    blue = [g for g in games if g.get("side") == "blue"]
    red  = [g for g in games if g.get("side") == "red"]

    if len(blue) < 5 or len(red) < 5:
        return findings

    blue_wr = round(sum(1 for g in blue if g["win"]) / len(blue) * 100, 1)
    red_wr  = round(sum(1 for g in red  if g["win"]) / len(red)  * 100, 1)
    gap = round(abs(blue_wr - red_wr), 1)

    if gap < 15:
        return findings

    better = "blue" if blue_wr > red_wr else "red"
    conf  = confidence_score(min(len(blue), len(red)), gap / 100)
    voice = confidence_voice(conf)
    if voice:
        findings.append({
            "category": "Map Side",
            "type": "map_side",
            "confidence": conf,
            "confidence_label": confidence_label(conf),
            "voice": voice,
            "title": "Map Side Winrate Gap",
            "data": {
                "blue_games": len(blue), "blue_wr": blue_wr,
                "red_games": len(red),   "red_wr": red_wr,
                "gap": gap, "better": better,
            }
        })
    return findings

# ─────────────────────────────────────────────
# MODULE 16: STREAK TRACKING
# ─────────────────────────────────────────────

def analyze_streaks(games):
    findings = []
    if len(games) < 5:
        return findings

    results = [g["win"] for g in games]

    # Current streak
    current_type = results[0]
    current_len = 1
    for r in results[1:]:
        if r == current_type:
            current_len += 1
        else:
            break

    # Longest win/loss streaks
    longest_win = 0
    longest_loss = 0
    streak = 1
    for i in range(1, len(results)):
        if results[i] == results[i - 1]:
            streak += 1
        else:
            streak = 1
        if results[i]:
            longest_win = max(longest_win, streak)
        else:
            longest_loss = max(longest_loss, streak)
    # also count first game
    if results[0]:
        longest_win = max(longest_win, 1)
    else:
        longest_loss = max(longest_loss, 1)

    if current_len < 3:
        return findings

    current_label = "win" if current_type else "loss"
    effect = min(1.0, current_len / 7)
    conf = confidence_score(current_len, effect)
    voice = confidence_voice(conf)
    if voice:
        findings.append({
            "category": "Trend",
            "type": "streak_active",
            "confidence": conf,
            "confidence_label": confidence_label(conf),
            "voice": voice,
            "title": f"{current_len}-Game {current_label.capitalize()} Streak",
            "data": {
                "current_len": current_len,
                "current_type": current_label,
                "longest_win": longest_win,
                "longest_loss": longest_loss,
            }
        })
    return findings

# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────

def run_analysis(games, champion_filter=None):
    all_games = games  # preserve unfiltered for queue split
    if champion_filter:
        games = [g for g in games if g["champion"].lower() == champion_filter.lower()]
    if len(games) < 3:
        return []

    all_findings = []
    all_findings.extend(analyze_queue_split(all_games))
    all_findings.extend(analyze_map_side(all_games))
    all_findings.extend(analyze_participation(games))
    if champion_filter:
        all_findings.extend(analyze_builds(games))
    all_findings.extend(analyze_performance_delta(games))
    all_findings.extend(analyze_early_game(games))
    all_findings.extend(analyze_champions(games))
    all_findings.extend(analyze_enemy_comparison(games))
    all_findings.extend(analyze_patterns(games))
    all_findings.extend(analyze_causal_chains(games))
    all_findings.extend(analyze_enemy_matchups(games))
    all_findings.extend(analyze_time_trend(games))
    all_findings.extend(analyze_streaks(games))
    all_findings.extend(analyze_vision_objectives(games))
    all_findings.extend(analyze_rift_herald(games))
    all_findings.extend(analyze_game_fingerprint(games))
    all_findings.extend(analyze_early_game_tempo(games))

    all_findings = validate_findings(all_findings, games)
    all_findings = deduplicate_findings(all_findings)
    all_findings.sort(key=lambda x: x["confidence"], reverse=True)

    ACTION_TYPE_MAP = {
        "delta_gold_lead_15": "early_game", "delta_cs_per_min": "early_game",
        "delta_cs_final": "early_game", "cs15_gap": "early_game",
        "delta_early_deaths": "early_game", "delta_deaths": "systemic",
        "delta_damage": "mid_game", "delta_damage_per_min": "mid_game",
        "delta_vision_per_min": "systemic", "delta_gold_per_min": "early_game",
        "delta_kill_participation": "mid_game", "delta_death_share": "systemic",
        "delta_damage_share": "mid_game", "cs_differential": "early_game",
        "damage_differential": "mid_game", "kills_differential": "mid_game",
        "first_item_underperform": "pre_game", "build_divergence": "pre_game",
        "pattern_invaded_early": "early_game", "pattern_won_jungle": "mid_game",
        "pattern_scaled_misplayed": "late_game", "pattern_dragon_control": "mid_game",
        "causal_invaded_snowball": "early_game", "causal_ahead_threw": "mid_game",
        "causal_no_vision_obj": "systemic", "causal_team_feed": "context",
        "causal_cs_recovery": "early_game", "queue_split": "context",
        "map_side": "context", "matchup_bad": "draft", "matchup_good": "draft",
        "streak_active": "context", "rift_herald_correlation": "mid_game",
        "trend_declining": "context", "trend_improving": "context",
        "tempo_score": "early_game", "fingerprint_cluster": "systemic",
    }
    for f in all_findings:
        if "action_type" not in f:
            f["action_type"] = ACTION_TYPE_MAP.get(f["type"], "systemic")

    CONTROL_LEVEL_MAP = {
        "delta_gold_lead_15": "direct", "delta_cs_per_min": "direct",
        "delta_cs_final": "direct", "cs15_gap": "direct",
        "delta_early_deaths": "direct", "delta_deaths": "direct",
        "delta_damage": "direct", "delta_damage_per_min": "direct",
        "delta_vision_per_min": "direct", "delta_gold_per_min": "direct",
        "delta_kill_participation": "direct", "delta_death_share": "direct",
        "delta_damage_share": "direct", "cs_differential": "direct",
        "damage_differential": "direct", "kills_differential": "direct",
        "first_item_underperform": "direct", "build_divergence": "direct",
        "pattern_invaded_early": "direct", "pattern_won_jungle": "direct",
        "pattern_scaled_misplayed": "direct", "pattern_dragon_control": "indirect",
        "causal_invaded_snowball": "direct", "causal_ahead_threw": "direct",
        "causal_no_vision_obj": "direct", "causal_team_feed": "none",
        "causal_cs_recovery": "direct", "queue_split": "none", "map_side": "none",
        "matchup_bad": "direct", "matchup_good": "direct", "streak_active": "none",
        "rift_herald_correlation": "indirect", "trend_declining": "none",
        "trend_improving": "none", "tempo_score": "direct", "fingerprint_cluster": "direct",
    }
    for f in all_findings:
        if "control_level" not in f:
            f["control_level"] = CONTROL_LEVEL_MAP.get(f["type"], "indirect")

    return all_findings

# ─────────────────────────────────────────────
# MODULE 12: EARLY GAME TEMPO SCORING
# ─────────────────────────────────────────────

def analyze_early_game_tempo(games):
    """
    Composite early game score per game combining:
    - CS at 15min (normalized)
    - Gold lead vs enemy at 15min (normalized)
    - Early deaths inverted
    - First blood participation
    - Killed by enemy jungler inverted

    Score 0.0 - 1.0. Correlation to winrate surfaces as a finding.
    Also detects: strong early = expected win, weak early = expected loss,
    and divergence cases (strong early lost, weak early won).
    """
    findings = []
    if len(games) < 10:
        return findings

    # Establish normalization ranges from the dataset
    cs15_vals = [g["cs_15"] for g in games if g.get("cs_15") is not None]
    gold_vals = [g["gold_lead_15"] for g in games if g.get("gold_lead_15") is not None]

    if not cs15_vals or not gold_vals:
        return findings

    cs15_min, cs15_max = min(cs15_vals), max(cs15_vals)
    gold_min, gold_max = min(gold_vals), max(gold_vals)
    cs15_range = max(cs15_max - cs15_min, 1)
    gold_range = max(gold_max - gold_min, 1)

    def tempo_score(g):
        score = 0.0
        weight_total = 0.0

        # CS at 15 — weight 0.25
        if g.get("cs_15") is not None:
            cs_norm = (g["cs_15"] - cs15_min) / cs15_range
            score += cs_norm * 0.25
            weight_total += 0.25

        # Gold lead at 15 — weight 0.35 (highest weight, most predictive)
        if g.get("gold_lead_15") is not None:
            gold_norm = (g["gold_lead_15"] - gold_min) / gold_range
            score += gold_norm * 0.35
            weight_total += 0.35

        # Early deaths inverted — weight 0.25
        early_d = g.get("early_deaths", 0)
        # 0 deaths = 1.0, 1 = 0.75, 2 = 0.5, 3+ = 0.0
        death_score = max(0.0, 1.0 - (early_d * 0.33))
        score += death_score * 0.25
        weight_total += 0.25

        # First blood participation — weight 0.10
        if g.get("first_blood_kill") or g.get("first_blood_assist"):
            score += 1.0 * 0.10
        weight_total += 0.10

        # Killed by enemy jungler inverted — weight 0.05
        killed = g.get("killed_by_enemy_jungler", 0)
        killed_score = max(0.0, 1.0 - (killed * 0.5))
        score += killed_score * 0.05
        weight_total += 0.05

        return round(score / weight_total if weight_total > 0 else 0, 3)

    # Score every game
    scored_games = [(g, tempo_score(g)) for g in games]

    # Split into tempo tiers
    strong_early = [(g, s) for g, s in scored_games if s >= 0.65]
    weak_early = [(g, s) for g, s in scored_games if s <= 0.35]
    mid_early = [(g, s) for g, s in scored_games if 0.35 < s < 0.65]

    # Winrate per tier
    strong_wr = round(sum(1 for g, _ in strong_early if g["win"]) / len(strong_early) * 100, 1) if strong_early else None
    weak_wr = round(sum(1 for g, _ in weak_early if g["win"]) / len(weak_early) * 100, 1) if weak_early else None
    mid_wr = round(sum(1 for g, _ in mid_early if g["win"]) / len(mid_early) * 100, 1) if mid_early else None

    # Only fire if there's a meaningful spread between tiers
    if strong_wr is not None and weak_wr is not None:
        spread = strong_wr - weak_wr
        if spread >= 20 and len(strong_early) >= 5 and len(weak_early) >= 5:
            # Divergence cases
            threw_from_strong = [(g, s) for g, s in strong_early if not g["win"]]
            won_from_weak = [(g, s) for g, s in weak_early if g["win"]]

            avg_strong_score = round(sum(s for _, s in strong_early) / len(strong_early), 2)
            avg_weak_score = round(sum(s for _, s in weak_early) / len(weak_early), 2)

            conf = confidence_score(min(len(strong_early), len(weak_early)), spread / 100)
            voice = confidence_voice(conf)

            if voice:
                findings.append({
                    "category": "Early Game Tempo",
                    "type": "tempo_score",
                    "confidence": conf,
                    "confidence_label": confidence_label(conf),
                    "voice": voice,
                    "title": "Early Game Tempo Score",
                    "data": {
                        "strong_games": len(strong_early),
                        "strong_wr": strong_wr,
                        "avg_strong_score": avg_strong_score,
                        "weak_games": len(weak_early),
                        "weak_wr": weak_wr,
                        "avg_weak_score": avg_weak_score,
                        "mid_games": len(mid_early),
                        "mid_wr": mid_wr,
                        "spread": round(spread, 1),
                        "threw_from_strong": len(threw_from_strong),
                        "won_from_weak": len(won_from_weak),
                    }
                })

    return findings
