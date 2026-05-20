"""Tests 1-2: Game dataclass round-trip and field access."""

from verdict_game_model import Game


class TestGameRoundTrip:
    """Test 1: Game.from_dict → to_dict → from_dict preserves all fields."""

    def test_round_trip_preserves_identity(self, games, cache_data):
        raw = cache_data["games"][0]
        game = Game.from_dict(raw)
        round_tripped = Game.from_dict(game.to_dict())

        assert game.match_id == round_tripped.match_id
        assert game.champion == round_tripped.champion
        assert game.win == round_tripped.win
        assert game.side == round_tripped.side
        assert game.role == round_tripped.role
        assert game.queue == round_tripped.queue

    def test_round_trip_preserves_kda(self, games):
        game = games[0]
        round_tripped = Game.from_dict(game.to_dict())

        assert game.kills == round_tripped.kills
        assert game.deaths == round_tripped.deaths
        assert game.assists == round_tripped.assists

    def test_round_trip_preserves_nested(self, games):
        game = games[0]
        round_tripped = Game.from_dict(game.to_dict())

        assert game.my_team.kills == round_tripped.my_team.kills
        assert game.my_team.dragon_kills == round_tripped.my_team.dragon_kills
        assert game.enemy_team.kills == round_tripped.enemy_team.kills

    def test_round_trip_preserves_floats(self, games):
        game = games[0]
        round_tripped = Game.from_dict(game.to_dict())

        assert game.damage_per_min == round_tripped.damage_per_min
        assert game.vision_per_min == round_tripped.vision_per_min
        assert game.cs_per_min == round_tripped.cs_per_min


class TestGameFieldAccess:
    """Test 2: Key fields have correct types and reasonable values."""

    def test_identity_fields(self, games):
        game = games[0]
        assert isinstance(game.win, bool)
        assert isinstance(game.champion, str)
        assert isinstance(game.match_id, str)
        assert game.champion  # non-empty

    def test_kda_fields(self, games):
        game = games[0]
        assert isinstance(game.kills, int)
        assert isinstance(game.deaths, int)
        assert isinstance(game.assists, int)
        assert game.kills >= 0
        assert game.deaths >= 0

    def test_kp_pct(self, games):
        game = games[0]
        assert isinstance(game.kp_pct, float)
        assert 0 <= game.kp_pct <= 100

    def test_team_objectives(self, games):
        game = games[0]
        assert isinstance(game.my_team.dragon_kills, int)
        assert isinstance(game.my_team.baron_kills, int)
        assert isinstance(game.my_team.tower_kills, int)
        assert game.my_team.dragon_kills >= 0

    def test_death_minutes_is_list(self, games):
        game = games[0]
        assert isinstance(game.death_minutes, list)
        if game.death_minutes:
            assert all(isinstance(m, (int, float)) for m in game.death_minutes)

    def test_game_has_enemy(self, games):
        # Not all games have enemy data, but most ranked games should
        game = games[0]
        if game.enemy is not None:
            assert isinstance(game.enemy.champion, str)
            assert game.enemy.champion  # non-empty