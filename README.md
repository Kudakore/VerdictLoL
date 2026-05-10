# FaceCheck

A personal League of Legends diagnostic system. Analyzes your match history to surface causal relationships between early-game decisions and outcomes — not just stats, but *why* you lost.

Designed for junglers at heart. Works for any role just the same.

Status: Work in Progress (Super Duper Alpha)
- As a CLI tool, it pretty much works. It is being configured and refined every day. The goal is to have a coaching companion app that does what no other companion app comes close to, besides sitting down and watching your gameplay with you.

## Features

- **Deep game analysis** across 7 domain engines: Death, Economy, Combat, Durability, Vision, Objective, Draft
- **Synthesis layer** that correlates engine outputs into actionable verdicts
- **Scout any player** by Riot ID with matchup breakdowns
- **Champion pool health report** with verdict ratings (PLAY / SOLID / CONDITIONAL / AVOID)
- **Champion intel vault** with matchup context and counter recommendations
- **Item and Component intel** with an entire breakdown of stats, costs, passives, etc

## Setup

### 1. Prerequisites

- Python 3.10+
- A Riot API key — get one at [developer.riotgames.com](https://developer.riotgames.com/)

### 2. Clone the repo

```bash
git clone https://github.com/YOURUSER/facecheck.git
cd facecheck
```

### 3. Configure your API key

```bash
copy config.py config.py
# Edit config.py and set:
#   API_KEY = "RGAPI-..."
#   MY_GAME_NAME = "YourSummonerName"
#   MY_TAG_LINE  = "YourTag"
```

### 4. Install dependencies

```bash
pip install requests
```

### 5. Run

```powershell
python facecheck_game.py lastgame
python facecheck_game.py pool
python facecheck_game.py scout YourName#YourTag
```

## Project Structure

| File | Purpose |
|------|---------|
| `facecheck_data.py` | Riot API calls, cache read/write |
| `facecheck_game.py` | CLI entry point |
| `facecheck_engine_*.py` | 7 domain-pure extraction engines |
| `facecheck_synthesis.py` | Correlates engine outputs into verdicts |
| `facecheck_analysis.py` | Legacy analysis system |
| `facecheck_diagnosis.py` | Human-readable output formatting |
| `facecheck_champ_intel.py` | Champion vault reader |
| `facecheck_scout.py` | Scout any player by Riot ID |
| `facecheck_player_model.py` | Persistent personal baselines |
| `config.py` | API key and player identity |

## Architecture

Engines are **purely extractive** — they describe what happened structurally, they do not judge whether it was good or bad. Synthesis layer consumes all engine outputs and generates verdicts relative to your personal baselines.

## License

MIT
