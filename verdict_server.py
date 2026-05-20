"""
Verdict Server — FastAPI HTTP interface for the Verdict analysis engine.

Exposes the CLI's analysis pipeline over REST for the Tauri desktop app.
All synchronous analysis runs in a thread executor to avoid blocking the event loop.
Own-player AnalysisService is cached and invalidated on fetch.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from verdict_config import ensure_config, API_KEY, REGION, PLATFORM, MY_GAME_NAME, MY_TAG_LINE
from verdict_data import (
    load_cache, save_cache, fetch_and_cache, fetch_player_games,
    resolve_riot_id, get_current_game, get_ranked_games, get_current_rank_string,
    get_puuid,
)
from verdict_game_model import Game
from verdict_service import AnalysisService
from verdict_display import render_game, render_compact_game
from verdict_special import (
    analyze_matchups, analyze_bans, analyze_heatmap, analyze_pathing,
    analyze_recent, analyze_scout, analyze_enemy, analyze_compare, analyze_guide,
    get_select_games, get_select_page,
)
from verdict_win_impact import WinImpactEngine

try:
    from verdict_champ_intel import analyze_counter_command, analyze_intel_profile
    INTEL_AVAILABLE = True
except Exception:
    INTEL_AVAILABLE = False

try:
    from verdict_item import analyze_champ_builds
    BUILDS_AVAILABLE = True
except Exception:
    BUILDS_AVAILABLE = False


logger = logging.getLogger("verdict_server")


# ── App State ────────────────────────────────────────────────────────

class AppState:
    """Mutable server state stored on app.state."""
    own_service: Optional[AnalysisService] = None
    own_player_id: Optional[str] = None
    own_games: list = []
    cache: Optional[dict] = None
    fetch_status: str = "idle"
    fetch_error: Optional[str] = None
    config_valid: bool = False
    _pipeline_lock: asyncio.Lock = None

    def __init__(self):
        self._pipeline_lock = asyncio.Lock()


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    state: AppState = app.state
    state.config_valid = ensure_config()
    if not state.config_valid:
        logger.warning("Config incomplete — analysis endpoints will return 503 until configured")

    cache = load_cache()
    state.cache = cache
    games = get_ranked_games(cache)
    if games:
        player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"
        state.own_games = games
        state.own_player_id = player_id
        logger.info(f"Loaded {len(games)} ranked games for {player_id}")
        loop = asyncio.get_event_loop()
        try:
            state.own_service = await loop.run_in_executor(
                None, AnalysisService, player_id, games
            )
            await loop.run_in_executor(None, state.own_service._ensure_pipeline)
            logger.info("Pipeline warmed up")
        except Exception as e:
            logger.warning(f"Pipeline warm-up failed: {e}")
            state.own_service = None
    else:
        logger.info("No cached games found. Run /api/v1/fetch to download match history.")

    yield

    logger.info("Server shutting down")


app = FastAPI(title="Verdict", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "https://tauri.localhost", "http://localhost:1420", "http://127.0.0.1:1420"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.state = AppState()


# ── Helpers ──────────────────────────────────────────────────────────

async def run_sync(func, *args, **kwargs):
    """Run a synchronous function in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def require_service(state: AppState) -> AnalysisService:
    """Return own-player service or raise 404."""
    if not state.config_valid:
        raise HTTPException(503, "Config incomplete. Set VERDICT_API_KEY and player identity.")
    if not state.own_service:
        raise HTTPException(404, "No cached games. Run /api/v1/fetch first.")
    return state.own_service


def require_games(state: AppState) -> list:
    """Return own-player games or raise 404."""
    if not state.own_games:
        raise HTTPException(404, "No cached games. Run /api/v1/fetch first.")
    return state.own_games


# ── Health & Config ─────────────────────────────────────────────────

@app.get("/api/v1/health")
async def health():
    state: AppState = app.state
    return {
        "status": "ok",
        "version": "1.0.0",
        "player_id": state.own_player_id,
        "cached_games": len(state.own_games),
        "pipeline_ready": state.own_service._pipeline_ready if state.own_service else False,
    }


@app.get("/api/v1/config")
async def config():
    state: AppState = app.state
    return {
        "player_id": f"{MY_GAME_NAME}#{MY_TAG_LINE}" if MY_GAME_NAME else None,
        "region": REGION,
        "platform": PLATFORM,
        "has_api_key": bool(API_KEY) and API_KEY != "YOUR_RIOT_API_KEY_HERE",
    }


# ── Cache ────────────────────────────────────────────────────────────

@app.get("/api/v1/cache")
async def cache_status():
    state: AppState = app.state
    cache = state.cache
    if not cache:
        return {"total_games": 0, "ranked_games": 0, "last_updated": None, "rank": None}
    games = cache.get("games", [])
    ranked = [g for g in games if isinstance(g, Game) and g.queue_id in (420, 440)]
    return {
        "total_games": len(games),
        "ranked_games": len(ranked),
        "last_updated": cache.get("last_updated"),
        "rank": get_current_rank_string(cache),
    }


# ── Fetch ────────────────────────────────────────────────────────────

@app.post("/api/v1/fetch")
async def fetch_games(count: int = 50, force: bool = False, background: bool = True):
    state: AppState = app.state
    if not state.config_valid:
        raise HTTPException(503, "Config incomplete. Set VERDICT_API_KEY and player identity.")

    if background:
        if state.fetch_status == "running":
            return {"status": "already_fetching", "message": "Fetch already in progress. Poll /api/v1/fetch/status."}
        state.fetch_status = "running"
        state.fetch_error = None
        asyncio.create_task(_do_fetch(state, count, force))
        return {"status": "fetching", "message": f"Fetching up to {count} games. Poll /api/v1/fetch/status for progress."}

    # Blocking fetch
    try:
        await run_sync(fetch_and_cache, count=count, force=force)
        await _rebuild_service(state)
        cache = load_cache()
        games = get_ranked_games(cache)
        return {
            "status": "complete",
            "games_fetched": len(games),
            "total_games": len(cache.get("games", [])),
            "last_updated": cache.get("last_updated"),
        }
    except Exception as e:
        raise HTTPException(500, f"Fetch failed: {str(e)}")


@app.get("/api/v1/fetch/status")
async def fetch_status():
    state: AppState = app.state
    result = {
        "status": state.fetch_status,
        "total_games": len(state.own_games),
    }
    if state.fetch_error:
        result["error"] = state.fetch_error
    return result


async def _do_fetch(state: AppState, count: int, force: bool):
    """Background task: fetch games and rebuild service."""
    try:
        await run_sync(fetch_and_cache, count=count, force=force)
        await _rebuild_service(state)
        state.fetch_status = "idle"
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        state.fetch_status = "error"
        state.fetch_error = str(e)


async def _rebuild_service(state: AppState):
    """Reload cache and rebuild own-player AnalysisService."""
    cache = load_cache()
    state.cache = cache
    games = get_ranked_games(cache)
    player_id = f"{MY_GAME_NAME}#{MY_TAG_LINE}"
    state.own_games = games
    state.own_player_id = player_id
    if games:
        state.own_service = await run_sync(AnalysisService, player_id, games)
    else:
        state.own_service = None


# ── Pipeline Analysis (own player) ──────────────────────────────────

@app.get("/api/v1/worst")
async def worst(champion: Optional[str] = None):
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_worst, champion)


@app.get("/api/v1/best")
async def best(champion: Optional[str] = None):
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_best, champion)


@app.get("/api/v1/pool")
async def pool(min_games: int = 3):
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_pool, min_games)


@app.get("/api/v1/matchups")
async def matchups(champion: Optional[str] = None):
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_matchups, champion)


@app.get("/api/v1/bans")
async def bans():
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_bans)


@app.get("/api/v1/heatmap")
async def heatmap():
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_heatmap)


@app.get("/api/v1/pathing")
async def pathing():
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_pathing)


@app.get("/api/v1/recent")
async def recent(queue: Optional[str] = None, count: int = 20):
    state: AppState = app.state
    service = require_service(state)
    return await run_sync(service.analyze_recent, queue, count, state.cache)


@app.get("/api/v1/impact")
async def impact():
    state: AppState = app.state
    service = require_service(state)
    result = await run_sync(service.analyze_win_impact)
    if hasattr(result, "__dataclass_fields__"):
        return asdict(result)
    return result


# ── Game Detail ──────────────────────────────────────────────────────

@app.get("/api/v1/game/{game_number}")
async def game_detail(game_number: int):
    state: AppState = app.state
    service = require_service(state)
    games = require_games(state)
    if game_number < 1 or game_number > len(games):
        raise HTTPException(404, f"Game {game_number} not found. Valid range: 1-{len(games)}")
    game = games[game_number - 1]
    result = await run_sync(
        service.analyze_game, game, game_number=game_number,
        historical_games=games, cache=state.cache
    )
    # Strip internal _verdict_obj if present
    if isinstance(result, dict) and "_verdict_obj" in result:
        del result["_verdict_obj"]
    return result


@app.get("/api/v1/games")
async def games_list(champion: Optional[str] = None, count: int = 5):
    state: AppState = app.state
    games = require_games(state)
    if champion:
        games = [g for g in games if g.champion.lower() == champion.lower()]
    games = games[:count]
    results = []
    for i, game in enumerate(games, 1):
        r = await run_sync(render_compact_game, game, i, games)
        results.append(r)
    return results


# ── Select ───────────────────────────────────────────────────────────

@app.get("/api/v1/select")
async def select_games(champion: Optional[str] = None, result: Optional[str] = None, page: int = 0, page_size: int = 10):
    state: AppState = app.state
    cache = state.cache
    if not cache:
        raise HTTPException(404, "No cached games. Run /api/v1/fetch first.")
    games = await run_sync(get_select_games, cache, champion, result)
    return await run_sync(get_select_page, games, page, page_size)


# ── Scout / Enemy / Compare ──────────────────────────────────────────

@app.post("/api/v1/scout")
async def scout(riot_id: str, count: int = 20):
    result_games, player_id = await run_sync(fetch_player_games, riot_id, count)
    if result_games is None:
        raise HTTPException(404, f"Player not found: {riot_id}")
    service = await run_sync(AnalysisService, player_id, result_games)
    return await run_sync(service.analyze_scout, riot_id)


@app.post("/api/v1/compare")
async def compare(riot_id: str, count: int = 20):
    state: AppState = app.state
    my_service = require_service(state)
    result_games, ref_player_id = await run_sync(fetch_player_games, riot_id, count)
    if result_games is None:
        raise HTTPException(404, f"Player not found: {riot_id}")
    ref_service = await run_sync(AnalysisService, ref_player_id, result_games)
    return await run_sync(
        AnalysisService.analyze_compare, my_service, ref_service,
        state.own_player_id, ref_player_id
    )


@app.post("/api/v1/enemy")
async def enemy(riot_id: str, champion: Optional[str] = None, role: Optional[str] = None):
    state: AppState = app.state
    result_games, player_id = await run_sync(fetch_player_games, riot_id)
    if result_games is None:
        raise HTTPException(404, f"Player not found: {riot_id}")
    enemy_service = await run_sync(AnalysisService, player_id, result_games)
    return await run_sync(
        enemy_service.analyze_enemy, riot_id,
        champion=champion, role=role,
        my_games=state.own_games, my_player_id=state.own_player_id
    )


@app.get("/api/v1/live")
async def live_game():
    state: AppState = app.state
    if not state.config_valid:
        raise HTTPException(503, "Config incomplete.")
    result = await run_sync(get_current_game)
    if result is None:
        return {"in_game": False}
    return {"in_game": True, "data": result}


# ── Champion Intelligence ────────────────────────────────────────────

@app.get("/api/v1/counter/{champion}")
async def counter(champion: str):
    if not INTEL_AVAILABLE:
        raise HTTPException(503, "Champion intelligence not available.")
    state: AppState = app.state
    games = require_games(state)
    return await run_sync(analyze_counter_command, champion, games)


@app.get("/api/v1/intel/{champion}")
async def intel(champion: str):
    if not INTEL_AVAILABLE:
        raise HTTPException(503, "Champion intelligence not available.")
    return await run_sync(analyze_intel_profile, champion)


@app.get("/api/v1/builds/{champion}")
async def builds(champion: str):
    if not BUILDS_AVAILABLE:
        raise HTTPException(503, "Build analysis not available.")
    state: AppState = app.state
    games = require_games(state)
    return await run_sync(analyze_champ_builds, games, champion)


# ── Guide ────────────────────────────────────────────────────────────

@app.get("/api/v1/guide")
async def guide():
    return await run_sync(analyze_guide)


# ── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("verdict_server:app", host="127.0.0.1", port=8420, reload=True)