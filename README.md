# Verdict

A personal League of Legends diagnostic system. Analyzes your match history to surface causal relationships between early-game decisions and outcomes — not just stats, but *why* you lost.

Designed for junglers at heart. Works for any role just the same.

## What It Does

Verdict runs your ranked games through 7 domain engines (Death, Economy, Combat, Durability, Vision, Objective, Draft) and synthesizes the results into actionable verdicts relative to your personal baselines.

- **Verdict per game** — names the primary loss factor or win enabler, with evidence and lessons
- **Worst / Best patterns** — mines observations across all your games to find what's costing you the most
- **Champion pool health** — rates each champion as PLAY / SOLID / CONDITIONAL / AVOID
- **Scout any player** — analyze another player by Riot ID with the same pipeline
- **Enemy scout** — live Spectator API integration for pre-game intelligence
- **Matchup breakdowns** — per-champion win rates, stat diffs, and counter-pick data
- **Win impact analysis** — statistical impact of each pattern on your win rate

## Quick Start

### Prerequisites

- Python 3.10+
- A Riot API key from [developer.riotgames.com](https://developer.riotgames.com/)

### Setup

```bash
git clone https://github.com/Kudakore/Verdict.git
cd Verdict
pip install requests fastapi uvicorn
```

Create a `.env` file in the project root:

```
VERDICT_API_KEY=RGAPI-your-key-here
VERDICT_REGION=americas
VERDICT_PLATFORM=na1
VERDICT_GAME_NAME=YourName
VERDICT_TAG_LINE=YourTag
```

### Fetch your games

```powershell
python verdict_game.py fetch
```

### CLI Commands

```
verdict fetch [N] [--force]    Fetch and cache ranked games
verdict lastgame                Deep dive on most recent game
verdict game N                  Deep dive on game N
verdict games [N]               Last N games with compact synthesis
verdict worst [champ]           What is costing you games
verdict best [champ]            What is working
verdict pool [N]                Champion pool health report
verdict matchups [champ]        Matchup breakdown
verdict bans                    Counter pool tracker
verdict heatmap                 Time-of-game death analysis
verdict pathing                 Jungle camp efficiency
verdict impact                  Win impact analysis
verdict scout Name#Tag [N]      Analyze any player
verdict compare Name#Tag [N]    Delta comparison vs another player
verdict enemy                   Live enemy scout (Spectator API)
verdict counter [champ]         How to beat a champion
verdict intel [champ]           Full champion intel profile
verdict item [name]             Item stats and build path
verdict builds [champ]          Item winrate analysis
verdict recent [solo|flex] [N]  Match history table
verdict select [champ]          Browse and pick a game
```

### API Server

```powershell
python verdict_server.py
```

Starts a FastAPI server on `localhost:8420` with 24 endpoints under `/api/v1/`. Built for the upcoming Tauri desktop app, but works with any HTTP client.

```
GET  /api/v1/health          Server status
GET  /api/v1/config          Player identity and region
GET  /api/v1/cache           Cached game summary
POST /api/v1/fetch           Fetch games from Riot API
GET  /api/v1/worst           Worst patterns analysis
GET  /api/v1/best            Best patterns analysis
GET  /api/v1/pool            Champion pool health
GET  /api/v1/game/{n}        Single game verdict
GET  /api/v1/games           Compact game list
GET  /api/v1/matchups        Matchup breakdown
GET  /api/v1/bans            Ban recommendations
GET  /api/v1/heatmap         Death timing heatmap
GET  /api/v1/pathing         Jungle pathing efficiency
GET  /api/v1/recent          Match history
GET  /api/v1/impact          Win impact analysis
POST /api/v1/scout           Scout any player
POST /api/v1/compare         Compare two players
POST /api/v1/enemy           Enemy scout
GET  /api/v1/live            Current Spectator game
GET  /api/v1/counter/{champ} Counter recommendations
GET  /api/v1/intel/{champ}   Champion intel profile
GET  /api/v1/builds/{champ}  Item winrate analysis
GET  /api/v1/select          Paginated game browser
GET  /api/v1/guide           Playing guide
```

## Architecture

```
Riot API
    |
    v
verdict_data.py              Game fetching, caching, Riot API calls
    |
    v
7 Domain Engines              Pure extraction — describe what happened
    |                          (Death, Economy, Combat, Durability, Vision, Objective, Draft)
    v
verdict_synthesis.py          Correlates all engine outputs into verdicts
    |                          relative to personal baselines (not generic thresholds)
    v
verdict_service.py            AnalysisService — single pipeline entry point
    |                          Runs engines once, caches all results
    v
verdict_server.py             FastAPI HTTP interface (localhost:8420)
    |
    v
Tauri Desktop App (upcoming)
```

Engines are purely extractive — they describe what happened structurally, they do not judge whether it was good or bad. The synthesis layer consumes all engine outputs and generates verdicts relative to your personal baselines.

## Project Structure

| File | Purpose |
|------|---------|
| `verdict_server.py` | FastAPI HTTP server (Phase 4) |
| `verdict_service.py` | AnalysisService — cached pipeline entry point |
| `verdict_game.py` | CLI entry point and mode dispatch |
| `verdict_game_model.py` | Game dataclass with from_dict/to_dict |
| `verdict_data.py` | Riot API, cache management, match record building |
| `verdict_synthesis.py` | SynthesisLayer, Verdict, MultiEngineOutput |
| `verdict_engine_*.py` | 7 domain-pure extraction engines |
| `verdict_engine_base.py` | Distribution, EngineOutput, run_engine_from_cache |
| `verdict_engine_cache.py` | Engine output caching (24h auto-invalidation) |
| `verdict_similarity.py` | Behavioral fingerprinting and game similarity |
| `verdict_player_model.py` | Per-player baselines and pattern memory |
| `verdict_win_impact.py` | Statistical win impact analysis |
| `verdict_aggregate.py` | Observation mining, worst/best/pool analysis |
| `verdict_special.py` | Specialized modes (matchups, bans, heatmap, scout, etc.) |
| `verdict_display.py` | Rendering functions (data/display split) |
| `verdict_champ_intel.py` | Champion intelligence and counter recommendations |
| `verdict_item.py` | Item lookup and build analysis |
| `verdict_config.py` | Config single source of truth (env > .env > config.py) |
| `verdict_paths.py` | Centralized path configuration |
| `league_vault.py` | Champion data vault builder (Data Dragon) |
| `LeagueVault/` | Generated champion knowledge base |
| `tests/` | 60 integration tests |

## License

MIT