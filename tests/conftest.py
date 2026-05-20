"""Shared test fixtures — loaded once per session for speed."""

import json
import os
import sys

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from verdict_game_model import Game
from verdict_synthesis import MultiEngineOutput
from verdict_player_model import get_or_create_player_model
from verdict_similarity import SimilarityEngine
from verdict_synthesis import SynthesisLayer


CACHE_PATH = os.path.join(PROJECT_ROOT, "verdict_cache.json")
ENGINE_CACHE_PATH = os.path.join(PROJECT_ROOT, "engine_cache", "Kuda_MIST_engines.json")


@pytest.fixture(scope="session")
def cache_data():
    """Load verdict_cache.json once per test session."""
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def games(cache_data):
    """Load games as Game objects from cache data."""
    raw_games = cache_data.get("games", [])
    return [Game.from_dict(g) for g in raw_games]


@pytest.fixture(scope="session")
def player_id(cache_data):
    """Get player_id from cache — use puuid for engine lookups."""
    return cache_data.get("puuid", "test_player")


@pytest.fixture(scope="session")
def engine_data():
    """Load raw engine cache JSON once per test session."""
    with open(ENGINE_CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def engines(engine_data):
    """Load MultiEngineOutput from engine cache data."""
    return MultiEngineOutput.from_dict(engine_data["engines"])


@pytest.fixture(scope="session")
def player_model(games):
    """Build PlayerModel from games."""
    return get_or_create_player_model("Kuda#MIST", games)


@pytest.fixture(scope="session")
def similarity_output(games):
    """Build SimilarityOutput from games."""
    engine = SimilarityEngine()
    return engine.analyze(games)


@pytest.fixture(scope="session")
def synthesis_layer(player_model, similarity_output):
    """Build SynthesisLayer with real data."""
    return SynthesisLayer(player_model, similarity_output=similarity_output)


@pytest.fixture
def a_game(games):
    """Return the most recent game (first in list)."""
    return games[0]