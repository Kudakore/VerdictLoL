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
from facecheck_data import load_cache, get_current_rank_string, get_ranked_games

# Display
from facecheck_display import print_full_game, print_compact_game

# Aggregate
from facecheck_aggregate import print_worst, print_best, print_pool

# Specialized modes
from facecheck_special import (
    run_select, print_matchups, print_guide,
    print_bans, print_heatmap, print_pathing
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
        print("No cached games found. Run: facecheck-fetch")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: face lastgame | face game N | face games [N] | face pool | face matchups | face counter [champ] | face intel [champ] | face guide | face scout Name#Tag | face worst [champ] | face best [champ]")
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
        print_pool(historical, min_games=min_g)

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

    else:
        print(f"Unknown mode: {mode}")