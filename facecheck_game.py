"""
FaceCheck — CLI entry point and mode dispatch.

Display functions live in facecheck_display.py
Aggregate analysis in facecheck_aggregate.py
Specialized modes in facecheck_special.py
Data layer in facecheck_data.py
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Data layer
from facecheck_data import load_cache, get_current_rank_string, get_ranked_games, fetch_player_games, get_current_game, resolve_puuid_to_riot_id, get_puuid

# Display
from facecheck_display import print_full_game, print_compact_game

# Aggregate
from facecheck_aggregate import print_worst, print_best, print_pool, synthesize_games_with_engines

# Specialized modes
from facecheck_special import (
    run_select, print_matchups, print_guide,
    print_bans, print_heatmap, print_pathing, print_scout, print_compare, print_recent, print_enemy
)

# Champion Intelligence — optional, graceful fallback
try:
    sys.path.insert(0, "C:\\Facecheck")
    from facecheck_champ_intel import (
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
        print("No cached games found. Run: face fetch")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: face lastgame | face game N | face games [N] | face recent [solo|flex] [N] | face pool | face matchups | face counter [champ] | face intel [champ] | face guide | face scout Name#Tag | face compare Name#Tag | face enemy | face worst [champ] | face best [champ]")
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
    from config import MY_GAME_NAME, MY_TAG_LINE
    player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"

    if mode == "last":
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
        print(f"\n  FaceCheck — Last {len(games_to_show)} Games{f' ({champion})' if champion else ''}")
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
            print("Usage: facecheck counter [champion]")
            print("Example: facecheck counter Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'league-update' to populate the vault.")
            sys.exit(1)
        print_counter_command(champion, game_history=historical)

    elif mode == "intel":
        if not champion:
            print("Usage: facecheck intel [champion]")
            print("Example: facecheck intel Warwick")
            sys.exit(1)
        if not INTEL_AVAILABLE:
            print("Champion intel unavailable. Run 'league-update' to populate the vault.")
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
            print("Usage: facecheck scout Name#Tag [count]")
            print("Example: facecheck scout Faker#KR1 10")
            sys.exit(1)
        scout_count = count or 20
        result = fetch_player_games(riot_id, count=scout_count)
        if result and result[0]:
            games, scout_player_id = result
            ranked_games = [g for g in games if g.get("queue_id") in (420, 440)]
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
            print("Usage: facecheck compare Name#Tag [count]")
            print("Example: facecheck compare Faker#KR1 10")
            sys.exit(1)
        if not cache.get("games"):
            print("No cached games found. Run: face fetch")
            sys.exit(1)

        compare_count = count or 20
        result = fetch_player_games(riot_id, count=compare_count)
        if not result or not result[0]:
            print(f"Could not fetch games for {riot_id}.")
            sys.exit(1)

        ref_games, ref_player_id = result
        ref_ranked = [g for g in ref_games if g.get("queue_id") in (420, 440)]
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
                from facecheck_special import SPECTATOR_ROLES
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
        enemy_ranked = [g for g in enemy_games if g.get("queue_id") in (420, 440)]

        if len(enemy_ranked) < 3:
            print(f"  Not enough ranked games for {enemy_riot_id} (need 3+, have {len(enemy_ranked)}).\n")
            sys.exit(1)

        print_enemy(enemy_ranked, enemy_player_id, enemy_riot_id,
                     champion=enemy_champion, role=my_position,
                     my_games=ranked, my_player_id=player_id)

    else:
        print(f"Unknown mode: {mode}")