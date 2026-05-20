"""Tests 9-12: Typed profiles, synthesis verdict, render_verdict, observation producers."""

from verdict_synthesis import (
    SynthesisLayer, Verdict, Observation, Summary, SummarySection,
    Divergence, CombatProfile, DurabilityProfile, VisionProfile,
)
from verdict_display import render_verdict


class TestTypedProfiles:
    """Test 9: CombatProfile, DurabilityProfile, VisionProfile from_signatures."""

    def test_combat_profile_from_signatures(self, games, engines):
        game = games[0]
        all_sigs = []
        for engine in [engines.death, engines.economy, engines.combat,
                       engines.durability, engines.vision, engines.objective, engines.draft]:
            if engine and engine.signatures:
                all_sigs.extend(engine.signatures)

        profile = CombatProfile.from_signatures(all_sigs, game)
        assert isinstance(profile, CombatProfile)
        assert profile.deaths >= 0
        assert profile.damage >= 0
        assert profile.dpm >= 0
        assert profile.kills >= 0
        assert profile.assists >= 0

    def test_durability_profile_from_signatures(self, games, engines):
        game = games[0]
        all_sigs = []
        for engine in [engines.death, engines.economy, engines.combat,
                       engines.durability, engines.vision, engines.objective, engines.draft]:
            if engine and engine.signatures:
                all_sigs.extend(engine.signatures)

        profile = DurabilityProfile.from_signatures(all_sigs, game)
        assert isinstance(profile, DurabilityProfile)
        assert profile.total_heal >= 0
        assert profile.damage_mitigated >= 0
        assert profile.cc_time >= 0

    def test_vision_profile_from_signatures(self, games, engines):
        game = games[0]
        all_sigs = []
        for engine in [engines.death, engines.economy, engines.combat,
                       engines.durability, engines.vision, engines.objective, engines.draft]:
            if engine and engine.signatures:
                all_sigs.extend(engine.signatures)

        profile = VisionProfile.from_signatures(all_sigs, game)
        assert isinstance(profile, VisionProfile)
        assert profile.vision_score >= 0
        assert profile.wards_killed >= 0

    def test_combat_profile_uses_game_fallbacks(self, games):
        """When no combat_profile signature exists, game fields are used."""
        game = games[0]
        profile = CombatProfile.from_signatures([], game)  # no signatures
        assert profile.deaths == game.deaths
        assert profile.damage == game.damage
        assert profile.kills == game.kills

    def test_durability_profile_uses_game_fallbacks(self, games):
        game = games[0]
        profile = DurabilityProfile.from_signatures([], game)
        assert profile.total_heal == game.total_heal
        assert profile.damage_mitigated == game.damage_mitigated


class TestSynthesisVerdict:
    """Test 10: SynthesisLayer.analyze_single_game produces valid Verdict."""

    def test_produces_verdict(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        assert isinstance(verdict, Verdict)

    def test_verdict_has_summary(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        assert isinstance(verdict.summary, Summary)
        assert len(verdict.summary.sections) > 0
        assert verdict.summary.to_text()  # non-empty string

    def test_verdict_summary_sections_are_typed(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        for section in verdict.summary.sections:
            assert isinstance(section, SummarySection)
            assert section.domain in ("death", "combat", "economy", "durability", "vision", "draft")
            assert section.statement  # non-empty

    def test_verdict_has_divergences(self, synthesis_layer, a_game, engines):
        # Not every game produces divergences, but the field should be a list
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        assert isinstance(verdict.divergences, list)
        for d in verdict.divergences:
            assert isinstance(d, Divergence)
            assert isinstance(d.statement, str)
            assert isinstance(d.win, bool)
            assert isinstance(d.data, dict)

    def test_verdict_has_observations(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        assert isinstance(verdict.observations, list)
        assert len(verdict.observations) > 0
        for obs in verdict.observations:
            assert isinstance(obs, Observation)
            assert obs.obs_type  # non-empty type string
            assert 0 <= obs.score <= 1

    def test_verdict_confidence_range(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        assert 0 <= verdict.confidence <= 1


class TestRenderVerdict:
    """Test 11: render_verdict returns structured output dict."""

    def test_render_verdict_keys(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        result = render_verdict(verdict)

        required_keys = [
            "statement", "confidence", "summary", "summary_sections",
            "evidence", "lessons", "divergences", "divergence_details",
            "matched_patterns", "similar_games",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_render_verdict_summary_is_string(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        result = render_verdict(verdict)
        assert isinstance(result["summary"], str)
        assert result["summary"]  # non-empty

    def test_render_verdict_summary_sections_are_dicts(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        result = render_verdict(verdict)
        assert isinstance(result["summary_sections"], list)
        for section in result["summary_sections"]:
            assert "domain" in section
            assert "statement" in section
            assert "data" in section

    def test_render_verdict_divergence_details_are_dicts(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        result = render_verdict(verdict)
        assert isinstance(result["divergences"], list)
        assert isinstance(result["divergence_details"], list)
        for detail in result["divergence_details"]:
            assert "type" in detail
            assert "statement" in detail
            assert "data" in detail
            assert "win" in detail

    def test_render_verdict_confidence(self, synthesis_layer, a_game, engines):
        verdict = synthesis_layer.analyze_single_game(a_game, engines)
        result = render_verdict(verdict)
        assert isinstance(result["confidence"], float)
        assert 0 <= result["confidence"] <= 1


class TestObservationProducers:
    """Test 12: All 12 observation producers return Observation or None."""

    def test_collect_observations(self, synthesis_layer, a_game, engines):
        # Collect all signatures from engines
        all_sigs = []
        for engine in [engines.death, engines.economy, engines.combat,
                       engines.durability, engines.vision, engines.objective, engines.draft]:
            if engine and engine.signatures:
                all_sigs.extend(engine.signatures)

        # Build baseline from player model
        baseline = synthesis_layer.player_model.baselines

        observations = synthesis_layer.collect_observations(
            a_game, all_sigs, baseline, engines
        )

        assert isinstance(observations, list)
        # At least some observations should fire for a real game
        assert len(observations) > 0

        for obs in observations:
            assert isinstance(obs, Observation), f"Expected Observation, got {type(obs)}"
            assert isinstance(obs.obs_type, str)
            assert obs.obs_type  # non-empty type
            assert isinstance(obs.statement, str)
            assert isinstance(obs.score, float)
            assert 0 <= obs.score <= 1

    def test_each_producer_returns_observation_or_none(self, synthesis_layer, a_game, engines):
        """Run each producer individually to catch crashes."""
        all_sigs = []
        for engine in [engines.death, engines.economy, engines.combat,
                       engines.durability, engines.vision, engines.objective, engines.draft]:
            if engine and engine.signatures:
                all_sigs.extend(engine.signatures)

        baseline = synthesis_layer.player_model.baselines

        producers = [
            synthesis_layer.observe_death_cluster,
            synthesis_layer.observe_death_chain,
            synthesis_layer.observe_efficient_combat,
            synthesis_layer.observe_inefficient_combat,
            synthesis_layer.observe_champion_repetition,
            synthesis_layer.observe_countered,
            synthesis_layer.observe_blind_pick,
            synthesis_layer.observe_death_assessment,
            synthesis_layer.observe_economy_pattern,
            synthesis_layer.observe_vision_control,
            synthesis_layer.observe_objective_control,
            synthesis_layer.observe_kill_participation,
        ]

        for producer in producers:
            result = producer(a_game, all_sigs, baseline, engines)
            assert result is None or isinstance(result, Observation), \
                f"{producer.__name__} returned {type(result)}, expected Observation or None"