"""Tests 3-4: Distribution and EngineOutput serialization."""

from verdict_engine_base import Distribution, EngineOutput, EngineSignature
from verdict_synthesis import MultiEngineOutput


class TestDistribution:
    """Test 3: Distribution.from_values and from_dict/to_dict round-trip."""

    def test_from_values_basic_stats(self):
        d = Distribution.from_values([1.0, 2.0, 3.0, 4.0, 5.0])
        assert d.mean == 3.0
        assert d.median == 3.0
        assert d.min == 1.0
        assert d.max == 5.0
        assert d.sample_size == 5

    def test_from_values_percentiles(self):
        d = Distribution.from_values([1.0, 2.0, 3.0, 4.0, 5.0])
        assert d.percentiles[25] == 2.0   # p25
        assert d.percentiles[50] == 3.0   # median
        assert d.percentiles[75] == 4.0    # p75

    def test_from_values_single_value(self):
        d = Distribution.from_values([5.0])
        assert d.mean == 5.0
        assert d.median == 5.0
        assert d.std_dev == 0.0
        assert d.sample_size == 1

    def test_round_trip_preserves_values(self):
        d = Distribution.from_values([10.0, 20.0, 30.0, 40.0, 50.0])
        data = d.to_dict()
        restored = Distribution.from_dict(data)

        assert restored.mean == d.mean
        assert restored.median == d.median
        assert restored.std_dev == d.std_dev
        assert restored.min == d.min
        assert restored.max == d.max
        assert restored.sample_size == d.sample_size
        assert restored.percentiles[25] == d.percentiles[25]
        assert restored.percentiles[75] == d.percentiles[75]

    def test_round_trip_preserves_distribution_key(self):
        """Distribution values survive dict serialization (int keys ↔ string keys)."""
        d = Distribution.from_values([1.0, 2.0, 3.0])
        data = d.to_dict()

        # Percentiles keys should be strings in the dict
        assert all(isinstance(k, str) for k in data["percentiles"].keys())

        # from_dict should convert back to int keys
        restored = Distribution.from_dict(data)
        assert all(isinstance(k, int) for k in restored.percentiles.keys())


class TestMultiEngineOutputSerialization:
    """Test 4: MultiEngineOutput from_dict/to_dict round-trip with real data."""

    def test_round_trip_preserves_engine_names(self, engines, engine_data):
        restored = MultiEngineOutput.from_dict(engines.to_dict())

        assert restored.death.engine_name == "death"
        assert restored.economy.engine_name == "economy"
        assert restored.combat.engine_name == "combat"
        assert restored.durability.engine_name == "durability"
        assert restored.vision.engine_name == "vision"
        assert restored.objective.engine_name == "objective"
        assert restored.draft.engine_name == "draft"

    def test_round_trip_preserves_distribution_keys(self, engines):
        original_keys = set(engines.death.distributions.keys())
        restored = MultiEngineOutput.from_dict(engines.to_dict())
        restored_keys = set(restored.death.distributions.keys())

        assert original_keys == restored_keys

    def test_round_trip_preserves_signature_types(self, engines):
        original_types = {s.signature_type for s in engines.death.signatures}
        restored = MultiEngineOutput.from_dict(engines.to_dict())
        restored_types = {s.signature_type for s in restored.death.signatures}

        assert original_types == restored_types

    def test_round_trip_preserves_confidence(self, engines):
        restored = MultiEngineOutput.from_dict(engines.to_dict())

        assert restored.death.confidence == engines.death.confidence
        assert restored.combat.confidence == engines.combat.confidence

    def test_round_trip_preserves_source_games(self, engines):
        restored = MultiEngineOutput.from_dict(engines.to_dict())

        assert restored.death.source_games == engines.death.source_games
        assert len(restored.death.source_games) > 0