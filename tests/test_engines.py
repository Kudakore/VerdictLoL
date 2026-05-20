"""Tests 7-8: Engine output shapes and distribution key contracts."""

from verdict_engine_death import DeathEngine
from verdict_engine_economy import EconomyEngine
from verdict_engine_combat import CombatEngine
from verdict_engine_durability import DurabilityEngine
from verdict_engine_vision import VisionEngine
from verdict_engine_objective import ObjectiveEngine
from verdict_engine_draft import DraftEngine


# Expected distribution keys per engine (from docs/engine-contracts.md)
ENGINE_DISTRIBUTION_KEYS = {
    "death": ["deaths_per_game", "death_timing", "early_deaths", "longest_living"],
    "economy": ["cs_at_10", "cs_at_15", "cs_per_min", "gold_lead_15", "gold_15", "gold_per_min", "first_clear_timing"],
    "combat": ["damage_per_min", "total_damage", "kill_participation", "damage_per_gold", "damage_per_death", "killing_spree", "multi_kills"],
    "durability": ["total_heal", "damage_mitigated", "cc_time", "heals_on_teammates", "damage_shielded", "damage_taken", "physical_damage_taken"],
    "vision": ["vision_score", "vision_per_min", "wards_placed", "wards_killed", "control_wards"],
    "objective": [
        "turret_kills", "inhibitor_kills", "objectives_stolen",
        "team_dragon_kills", "team_baron_kills", "team_tower_kills", "team_rift_herald_kills",
        "enemy_dragon_kills", "enemy_baron_kills", "enemy_tower_kills", "enemy_rift_herald_kills",
    ],
    "draft": ["pick_order"],
}

ENGINE_CLASSES = {
    "death": DeathEngine,
    "economy": EconomyEngine,
    "combat": CombatEngine,
    "durability": DurabilityEngine,
    "vision": VisionEngine,
    "objective": ObjectiveEngine,
    "draft": DraftEngine,
}


class TestEngineOutputShapes:
    """Test 7: All 7 engines produce valid EngineOutput with real data."""

    def test_death_engine_shape(self, games, player_id):
        engine = DeathEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "death"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert isinstance(output.signatures, list)
        assert 0 < output.confidence <= 1
        assert len(output.source_games) > 0

    def test_economy_engine_shape(self, games, player_id):
        engine = EconomyEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "economy"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert 0 < output.confidence <= 1

    def test_combat_engine_shape(self, games, player_id):
        engine = CombatEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "combat"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert 0 < output.confidence <= 1

    def test_durability_engine_shape(self, games, player_id):
        engine = DurabilityEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "durability"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert 0 < output.confidence <= 1

    def test_vision_engine_shape(self, games, player_id):
        engine = VisionEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "vision"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert 0 < output.confidence <= 1

    def test_objective_engine_shape(self, games, player_id):
        engine = ObjectiveEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "objective"
        assert isinstance(output.distributions, dict)
        assert len(output.distributions) > 0
        assert 0 < output.confidence <= 1

    def test_draft_engine_shape(self, games, player_id):
        engine = DraftEngine(player_id)
        output = engine.analyze(games)
        assert output.engine_name == "draft"
        assert isinstance(output.distributions, dict)
        assert 0 < output.confidence <= 1


class TestEngineDistributionKeys:
    """Test 8: Engine distribution keys match documented contracts."""

    def test_death_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["death"])
        actual = set(engines.death.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_economy_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["economy"])
        actual = set(engines.economy.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_combat_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["combat"])
        actual = set(engines.combat.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_durability_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["durability"])
        actual = set(engines.durability.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_vision_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["vision"])
        actual = set(engines.vision.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_objective_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["objective"])
        actual = set(engines.objective.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"

    def test_draft_distribution_keys(self, engines):
        expected = set(ENGINE_DISTRIBUTION_KEYS["draft"])
        actual = set(engines.draft.distributions.keys())
        assert expected.issubset(actual), f"Missing keys: {expected - actual}"