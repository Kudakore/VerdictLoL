"""
Verdict — CLI entry point and mode dispatch.

Display functions live in verdict_display.py
Aggregate analysis in verdict_aggregate.py
Specialized modes in verdict_special.py
Data layer in verdict_data.py
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Data layer
from verdict_data import load_cache, get_current_rank_string, get_ranked_games, fetch_player_games, get_current_game, resolve_puuid_to_riot_id, get_puuid

# Game model
from verdict_game_model import Game

# Display
from verdict_display import print_full_game, print_compact_game

# Aggregate
from verdict_aggregate import print_worst, print_best, print_pool, synthesize_games_with_engines

# Specialized modes
from verdict_special import (
    run_select, print_matchups, print_guide,
    print_bans, print_heatmap, print_pathing, print_scout, print_compare, print_recent, print_enemy
)

# Champion Intelligence — optional, graceful fallback
try:
    from verdict_champ_intel import (
        print_counter_command, print_intel_profile
    )
    INTEL_AVAILABLE = True
except Exception:
    INTEL_AVAILABLE = False


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    cache = load_cache()

    if not cache.get("games"):
        print("No cached games found. Run: verdict fetch")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: verdict lastgame | verdict game N | verdict games [N] | verdict recent [solo|flex] [N] | verdict pool | verdict matchups | verdict counter [champ] | verdict intel [champ] | verdict guide | verdict scout Name#Tag | verdict compare Name#Tag | verdict enemy | verdict worst [champ] | verdict best [champ] | verdict item [name] | verdict components [name] | verdict champ [name] | verdict builds [champ] | verdict impact")
        sys.exit(1)

    mode = args[0]

    # Parse optional champion, count, and result_filter
    # Join all non-digit args — handles PowerShell splatting single chars
    champion = None
    count = None
    result_filter = None
    champ_parts = []
    digit_parts = []
    for arg in args[1:]:
        if arg == "--legacy":
            continue
        if arg.isdigit():
            digit_parts.append(arg)
        elif arg.lower() in ("wins", "losses"):
            result_filter = arg.lower()
        elif not arg.startswith("--"):
            champ_parts.append(arg)
    # PowerShell char-splits multi-digit numbers (e.g. "10" → ["1","0"]).
    # If all parts are single chars AND all are digits, rejoin them first.
    if digit_parts:
        digit_str = "".join(digit_parts) if all(len(d) == 1 for d in digit_parts) else digit_parts[0]
        count = int(digit_str)
    if champ_parts:
        # If all parts are single chars, PowerShell passed a string as chars — rejoin
        if all(len(p) == 1 for p in champ_parts):
            champion = "".join(champ_parts)
        else:
            champion = " ".join(champ_parts)

    ranked = get_ranked_games(cache, champion=champion)
    historical = get_ranked_games(cache)  # unfiltered for context
    from verdict_config import ensure_config, MY_GAME_NAME, MY_TAG_LINE
    if not ensure_config():
        sys.exit(1)
    player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"

    if mode in ("last", "lastgame"):
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_full_game(ranked[0], game_number=1, historical_games=historical, player_id=player_id, cache=cache)

    elif mode == "game":
        n = count or 1
        if n < 1 or n > len(ranked):
            print(f"Game {n} not found. You have {len(ranked)} ranked games cached.")
            sys.exit(1)
        print_full_game(ranked[n - 1], game_number=n, historical_games=historical, player_id=player_id, cache=cache)

    elif mode == "games":
        n = count or 5
        games_to_show = ranked[:n]
        if not games_to_show:
            print("No ranked games found.")
            sys.exit(1)
        print(f"\n  Verdict — Last {len(games_to_show)} Games{f' ({champion})' if champion else ''}")
        for i, g in enumerate(games_to_show, 1):
            print_compact_game(g, i, historical_games=historical)

    elif mode == "select":
        run_select(cache, champion=champion, result_filter=result_filter)

    elif mode == "recent":
        # Queue filter: solo, flex, or all
        queue_map = {"solo": 420, "flex": 440}
        queue_arg = champion  # reuse champion arg for queue keyword
        queue_filter = queue_map.get((queue_arg or "").lower()) if queue_arg else None
        # Count: if champion is a number (no queue keyword), that's the count
        n = count or 20
        if queue_arg and queue_arg.lower() not in queue_map:
            # Try parsing queue_arg as a count
            try:
                n = int(queue_arg)
                queue_filter = None
            except ValueError:
                print(f"Unknown queue filter: {queue_arg}. Use: solo, flex, or a number.")
                sys.exit(1)
        print_recent(historical, queue_filter=queue_filter, count=n, cache=cache)

    elif mode == "worst":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_worst(ranked, champion=champion, player_id=player_id)

    elif mode == "best":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_best(ranked, champion=champion, player_id=player_id)

    elif mode == "pool":
        min_g = count or 3
        print_pool(historical, min_games=min_g, player_id=player_id)

    elif mode == "matchups":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_matchups(ranked, champion=champion)

    elif mode == "counter":
        if not champion:
            print("Usage: verdict counter [champion]")
            print("Example: verdict counter Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'verdict update' to populate the vault.")
            sys.exit(1)
        print_counter_command(champion, game_history=historical)

    elif mode == "intel":
        if not champion:
            print("Usage: verdict intel [champion]")
            print("Example: verdict intel Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'verdict update' to populate the vault.")
            sys.exit(1)
        print_intel_profile(champion)

    elif mode == "guide":
        print_guide()

    elif mode == "bans":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_bans(ranked)

    elif mode == "heatmap":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_heatmap(ranked)

    elif mode == "pathing":
        if not ranked:
            print("No ranked games found.")
            sys.exit(1)
        print_pathing(ranked)

    elif mode == "scout":
        # Scout takes a Riot ID (Name#Tag) as the champion arg
        riot_id = champion
        if not riot_id:
            print("Usage: verdict scout Name#Tag [count]")
            print("Example: verdict scout Faker#KR1 10")
            sys.exit(1)
        scout_count = count or 20
        result = fetch_player_games(riot_id, count=scout_count)
        if result and result[0]:
            games, scout_player_id = result
            ranked_games = [g for g in games if g.queue_id in (420, 440)]
            if not ranked_games:
                print(f"No ranked games found for {riot_id}.")
                sys.exit(1)
            print_scout(ranked_games, scout_player_id, riot_id)
        else:
            print(f"Could not fetch games for {riot_id}.")

    elif mode == "compare":
        # Compare takes a Riot ID (Name#Tag) as the champion arg
        riot_id = champion
        if not riot_id:
            print("Usage: verdict compare Name#Tag [count]")
            print("Example: verdict compare Faker#KR1 10")
            sys.exit(1)
        if not cache.get("games"):
            print("No cached games found. Run: verdict fetch")
            sys.exit(1)

        compare_count = count or 20
        result = fetch_player_games(riot_id, count=compare_count)
        if not result or not result[0]:
            print(f"Could not fetch games for {riot_id}.")
            sys.exit(1)

        ref_games, ref_player_id = result
        ref_ranked = [g for g in ref_games if g.queue_id in (420, 440)]
        if not ref_ranked:
            print(f"No ranked games found for {riot_id}.")
            sys.exit(1)

        if len(ref_ranked) < 3:
            print(f"Not enough ranked games for {riot_id} (need 3+, have {len(ref_ranked)}).")
            sys.exit(1)

        # Synthesize both players
        my_pairs, my_engines = synthesize_games_with_engines(ranked, player_id)
        ref_pairs, ref_engines = synthesize_games_with_engines(ref_ranked, ref_player_id)

        if not my_pairs:
            print("Not enough data for your games (need 3+).")
            sys.exit(1)
        if not ref_pairs:
            print(f"Not enough data for {riot_id} (need 3+).")
            sys.exit(1)

        print_compare(ranked, my_pairs, my_engines, ref_ranked, ref_pairs, ref_engines, player_id, ref_player_id)

    elif mode == "enemy":
        # Auto-detect same-position enemy in current game via Spectator API
        # If no game found, wait for one (champ select / loading screen)
        puuid = get_puuid()
        game = get_current_game(puuid)

        if not game:
            import time
            print("\n  No game detected. Waiting...", end="", flush=True)
            start = time.time()
            while time.time() - start < 120:
                time.sleep(5)
                print(".", end="", flush=True)
                game = get_current_game(puuid)
                if game:
                    break
            print()
            if not game:
                print("\n  No game detected after 2 minutes. Aborting.\n")
                sys.exit(1)

        # Parse game — find our position and team
        participants = game.get("participants", [])
        if not participants:
            print("\n  Could not read game participants.\n")
            sys.exit(1)

        # Find ourselves
        my_team = None
        my_position = None
        for p in participants:
            if p.get("puuid") == puuid:
                my_team = p.get("teamId")
                pos = (p.get("individualPosition") or p.get("teamPosition") or "").strip()
                from verdict_special import SPECTATOR_ROLES
                my_position = SPECTATOR_ROLES.get(pos, pos)
                break

        if not my_team:
            print("\n  Could not find you in the current game.\n")
            sys.exit(1)

        # Find enemy same-position
        enemies = [p for p in participants if p.get("teamId") != my_team]
        enemy = None

        if my_position and my_position != "N/A":
            for p in enemies:
                pos = (p.get("individualPosition") or p.get("teamPosition") or "").strip()
                enemy_pos = SPECTATOR_ROLES.get(pos, pos)
                if enemy_pos == my_position:
                    enemy = p
                    break

        if not enemy:
            # Position not matched — show all enemies and let user pick
            # For now, just show the list
            if not my_position or my_position == "N/A":
                print(f"\n  Could not determine your position in this game.")
            else:
                print(f"\n  No enemy {my_position} found.")
            print(f"  Enemy team:")
            for p in enemies:
                champ = p.get("championName", "?")
                pos = SPECTATOR_ROLES.get((p.get("individualPosition") or "").strip(), "?")
                print(f"    {champ} ({pos})")
            print()
            sys.exit(1)

        enemy_champion = enemy.get("championName", "?")
        enemy_puuid = enemy.get("puuid")
        enemy_riot_id = resolve_puuid_to_riot_id(enemy_puuid)

        if not enemy_riot_id:
            print(f"\n  Could not identify enemy {enemy_champion}. Riot ID lookup failed.\n")
            sys.exit(1)

        # Fetch their ranked games
        print(f"\n  Scouting {enemy_riot_id} ({enemy_champion})...")
        result = fetch_player_games(enemy_riot_id, count=20)
        if not result or not result[0]:
            print(f"  Could not fetch games for {enemy_riot_id}.\n")
            sys.exit(1)

        enemy_games, enemy_player_id = result
        enemy_ranked = [g for g in enemy_games if g.queue_id in (420, 440)]

        if len(enemy_ranked) < 3:
            print(f"  Not enough ranked games for {enemy_riot_id} (need 3+, have {len(enemy_ranked)}).\n")
            sys.exit(1)

        print_enemy(enemy_ranked, enemy_player_id, enemy_riot_id,
                     champion=enemy_champion, role=my_position,
                     my_games=ranked, my_player_id=player_id)

    elif mode == "item":
        from verdict_item import show_item
        query = champion or " ".join(args[1:])
        show_item(query)

    elif mode == "components":
        from verdict_item import show_components
        query = champion or " ".join(args[1:])
        show_components(query)

    elif mode == "champ":
        from verdict_champ_intel import print_champ_stats
        if not champion:
            print("Usage: verdict champ [champion]")
            print("Example: verdict champ Warwick")
            sys.exit(1)
        print_champ_stats(champion)

    elif mode == "builds":
        from verdict_item import print_champ_builds
        if not champion:
            print("Usage: verdict builds [champion]")
            print("Example: verdict builds Viego")
            sys.exit(1)
        print_champ_builds(historical, champion)

    elif mode == "impact":
        from verdict_win_impact import run_win_impact_engine
        output = run_win_impact_engine(games=ranked, player_id=player_id)
        if not output:
            print("Not enough data for win impact analysis.")
            sys.exit(1)

        print(f"\n  Win Impact Analysis — {output.player_id[:20]}")
        print(f"  Baseline WR: {output.baseline_win_rate:.1%} across {output.total_games} games")
        print(f"  Confidence: {output.confidence:.0%}")
        print()

        for cls in ["loss_guarantor", "recoverable", "neutral", "lever"]:
            group = output.get_by_classification(cls)
            if not group:
                continue
            print(f"  ══ {cls.upper().replace('_', ' ')} ══")
            for sig in group:
                print(f"  {sig.signature_type}")
                print(f"    {sig.games_affected} games | WR: {sig.win_rate_when_present:.1%} | Δ: {sig.delta:+.1%}")
                if sig.compensating_factors:
                    print(f"    Compensating factors:")
                    for cf in sig.compensating_factors:
                        print(f"      {cf.factor_label}: +{cf.delta_vs_problem:.0%} ({cf.games_with_both} games)")
            print()

    else:
        print(f"Unknown mode: {mode}")