"""
Verdict Game Model — Typed dataclasses for game data.

Replaces untyped dicts throughout the codebase. Every game record returned by
verdict_data.build_match_record() is now a Game instance. Nested dicts are
replaced by EnemyPlayer, PlayerStats, TeamObjectives, and JunglePathing.

This prevents silent bugs from typos (e.g. cs_at_15 vs cs_15) and gives
IDE autocompletion for every field.

Usage:
    from verdict_game_model import Game
    game = Game.from_dict(cached_dict)
    game.champion  # attribute access, not game.get("champion")
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class JunglePathing:
    cs_by_minute: Dict[str, int] = field(default_factory=dict)
    cs_at_5: int = 0
    cs_at_10: int = 0
    cs_at_15: int = 0
    first_clear_min: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "cs_by_minute": self.cs_by_minute,
            "cs_at_5": self.cs_at_5,
            "cs_at_10": self.cs_at_10,
            "cs_at_15": self.cs_at_15,
            "first_clear_min": self.first_clear_min,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JunglePathing":
        if d is None:
            return None
        return cls(
            cs_by_minute=d.get("cs_by_minute", {}),
            cs_at_5=d.get("cs_at_5", 0),
            cs_at_10=d.get("cs_at_10", 0),
            cs_at_15=d.get("cs_at_15", 0),
            first_clear_min=d.get("first_clear_min"),
        )


@dataclass
class EnemyPlayer:
    champion: str = ""
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    damage: int = 0
    win: bool = False
    gold: int = 0
    gold_15: Optional[float] = None
    vision: int = 0
    wards_placed: int = 0
    control_wards: int = 0
    first_blood_kill: bool = False
    turret_kills: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EnemyPlayer":
        if d is None:
            return None
        return cls(
            champion=d.get("champion", ""),
            kills=d.get("kills", 0),
            deaths=d.get("deaths", 0),
            assists=d.get("assists", 0),
            cs=d.get("cs", 0),
            damage=d.get("damage", 0),
            win=d.get("win", False),
            gold=d.get("gold", 0),
            gold_15=d.get("gold_15"),
            vision=d.get("vision", 0),
            wards_placed=d.get("wards_placed", 0),
            control_wards=d.get("control_wards", 0),
            first_blood_kill=d.get("first_blood_kill", False),
            turret_kills=d.get("turret_kills", 0),
        )


@dataclass
class PlayerStats:
    champion: str = ""
    role: str = ""
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    cs_per_min: float = 0.0
    damage: int = 0
    damage_per_min: float = 0.0
    gold: int = 0
    gold_per_min: float = 0.0
    vision: int = 0
    vision_per_min: float = 0.0
    wards_placed: int = 0
    wards_killed: int = 0
    control_wards: int = 0
    first_blood_kill: bool = False
    first_blood_assist: bool = False
    turret_kills: int = 0
    inhibitor_kills: int = 0
    total_heal: int = 0
    damage_mitigated: int = 0
    cc_time: int = 0
    longest_living: int = 0
    largest_killing_spree: int = 0
    time_spent_dead: int = 0
    heals_on_teammates: int = 0
    damage_shielded: int = 0
    total_damage_taken: int = 0
    physical_damage_taken: int = 0
    magic_damage_taken: int = 0
    objectives_stolen: int = 0
    bounty_level: int = 0
    spell1_casts: int = 0
    spell2_casts: int = 0
    spell3_casts: int = 0
    spell4_casts: int = 0
    double_kills: int = 0
    triple_kills: int = 0
    quadra_kills: int = 0
    penta_kills: int = 0
    build_order: List = field(default_factory=list)
    final_items: List = field(default_factory=list)
    win: bool = False
    puuid: str = ""
    # Added by build_match_record, not in Riot data
    team: str = ""
    is_me: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerStats":
        if d is None:
            return None
        return cls(
            champion=d.get("champion", ""),
            role=d.get("role", ""),
            kills=d.get("kills", 0),
            deaths=d.get("deaths", 0),
            assists=d.get("assists", 0),
            cs=d.get("cs", 0),
            cs_per_min=d.get("cs_per_min", 0.0),
            damage=d.get("damage", 0),
            damage_per_min=d.get("damage_per_min", 0.0),
            gold=d.get("gold", 0),
            gold_per_min=d.get("gold_per_min", 0.0),
            vision=d.get("vision", 0),
            vision_per_min=d.get("vision_per_min", 0.0),
            wards_placed=d.get("wards_placed", 0),
            wards_killed=d.get("wards_killed", 0),
            control_wards=d.get("control_wards", 0),
            first_blood_kill=d.get("first_blood_kill", False),
            first_blood_assist=d.get("first_blood_assist", False),
            turret_kills=d.get("turret_kills", 0),
            inhibitor_kills=d.get("inhibitor_kills", 0),
            total_heal=d.get("total_heal", 0),
            damage_mitigated=d.get("damage_mitigated", 0),
            cc_time=d.get("cc_time", 0),
            longest_living=d.get("longest_living", 0),
            largest_killing_spree=d.get("largest_killing_spree", 0),
            time_spent_dead=d.get("time_spent_dead", 0),
            heals_on_teammates=d.get("heals_on_teammates", 0),
            damage_shielded=d.get("damage_shielded", 0),
            total_damage_taken=d.get("total_damage_taken", 0),
            physical_damage_taken=d.get("physical_damage_taken", 0),
            magic_damage_taken=d.get("magic_damage_taken", 0),
            objectives_stolen=d.get("objectives_stolen", 0),
            bounty_level=d.get("bounty_level", 0),
            spell1_casts=d.get("spell1_casts", 0),
            spell2_casts=d.get("spell2_casts", 0),
            spell3_casts=d.get("spell3_casts", 0),
            spell4_casts=d.get("spell4_casts", 0),
            double_kills=d.get("double_kills", 0),
            triple_kills=d.get("triple_kills", 0),
            quadra_kills=d.get("quadra_kills", 0),
            penta_kills=d.get("penta_kills", 0),
            build_order=d.get("build_order", []),
            final_items=d.get("final_items", []),
            win=d.get("win", False),
            puuid=d.get("puuid", ""),
            team=d.get("team", ""),
            is_me=d.get("is_me", False),
        )


@dataclass
class TeamObjectives:
    kills: int = 0
    deaths: int = 0
    dragon_kills: int = 0
    baron_kills: int = 0
    tower_kills: int = 0
    rift_herald_kills: int = 0
    first_blood: bool = False
    first_tower: bool = False
    first_dragon: bool = False
    first_baron: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TeamObjectives":
        if d is None:
            return cls()
        return cls(
            kills=d.get("kills", 0),
            deaths=d.get("deaths", 0),
            dragon_kills=d.get("dragon_kills", 0),
            baron_kills=d.get("baron_kills", 0),
            tower_kills=d.get("tower_kills", 0),
            rift_herald_kills=d.get("rift_herald_kills", 0),
            first_blood=d.get("first_blood", False),
            first_tower=d.get("first_tower", False),
            first_dragon=d.get("first_dragon", False),
            first_baron=d.get("first_baron", False),
        )


@dataclass
class Game:
    # Identity
    match_id: str = ""
    queue: str = ""
    queue_id: int = 0
    side: str = ""
    win: bool = False
    champion: str = ""
    role: str = ""
    duration_min: float = 0.0
    puuid: str = ""

    # KDA
    kills: int = 0
    deaths: int = 0
    assists: int = 0

    # CS
    cs_final: int = 0
    cs_10: Optional[int] = None
    cs_15: Optional[int] = None
    cs_per_min: float = 0.0

    # Death stats
    early_deaths: int = 0
    death_minutes: List[float] = field(default_factory=list)
    longest_living: int = 0
    time_spent_dead: int = 0

    # Jungle pathing (None for non-junglers)
    jungle_pathing: Optional[JunglePathing] = None
    killed_by_enemy_jungler: int = 0

    # Damage
    damage: int = 0
    damage_per_min: float = 0.0

    # Vision
    vision: int = 0
    vision_per_min: float = 0.0
    wards_placed: int = 0
    wards_killed: int = 0
    control_wards: int = 0

    # Gold
    gold: int = 0
    gold_per_min: float = 0.0
    gold_15: Optional[float] = None
    gold_lead_15: Optional[float] = None

    # Durability
    total_heal: int = 0
    damage_mitigated: int = 0
    cc_time: int = 0
    heals_on_teammates: int = 0
    damage_shielded: int = 0
    total_damage_taken: int = 0
    physical_damage_taken: int = 0
    magic_damage_taken: int = 0

    # Combat
    largest_killing_spree: int = 0
    first_blood_kill: bool = False
    first_blood_assist: bool = False
    turret_kills: int = 0
    inhibitor_kills: int = 0
    objectives_stolen: int = 0
    bounty_level: int = 0
    double_kills: int = 0
    triple_kills: int = 0
    quadra_kills: int = 0
    penta_kills: int = 0
    spell1_casts: int = 0
    spell2_casts: int = 0
    spell3_casts: int = 0
    spell4_casts: int = 0

    # Build
    build_order: List = field(default_factory=list)
    first_item: Optional[str] = None
    final_items: List = field(default_factory=list)
    pick_order: Optional[int] = None
    enemy_pick_order: Optional[int] = None

    # Kill participation (computed: (kills + assists) / max(team_kills, 1))
    kp_pct: float = 0.0

    # Enemy same-position player
    enemy: Optional[EnemyPlayer] = None

    # All 10 players
    all_players: List[PlayerStats] = field(default_factory=list)

    # Team context
    my_team: TeamObjectives = field(default_factory=TeamObjectives)
    enemy_team: TeamObjectives = field(default_factory=TeamObjectives)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert None values to JSON-safe defaults for nested optionals
        if self.jungle_pathing is None:
            d["jungle_pathing"] = None
        if self.enemy is None:
            d["enemy"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Game":
        if d is None:
            return cls()
        g = cls(
            match_id=d.get("match_id", ""),
            queue=d.get("queue", ""),
            queue_id=d.get("queue_id", 0),
            side=d.get("side", ""),
            win=d.get("win", False),
            champion=d.get("champion", ""),
            role=d.get("role", ""),
            duration_min=d.get("duration_min", 0.0),
            puuid=d.get("puuid", ""),
            kills=d.get("kills", 0),
            deaths=d.get("deaths", 0),
            assists=d.get("assists", 0),
            cs_final=d.get("cs_final", 0),
            cs_10=d.get("cs_10"),
            cs_15=d.get("cs_15"),
            cs_per_min=d.get("cs_per_min", 0.0),
            early_deaths=d.get("early_deaths", 0),
            death_minutes=d.get("death_minutes", []),
            longest_living=d.get("longest_living", 0),
            time_spent_dead=d.get("time_spent_dead", 0),
            jungle_pathing=JunglePathing.from_dict(d.get("jungle_pathing")),
            killed_by_enemy_jungler=d.get("killed_by_enemy_jungler", 0),
            damage=d.get("damage", 0),
            damage_per_min=d.get("damage_per_min", 0.0),
            vision=d.get("vision", 0),
            vision_per_min=d.get("vision_per_min", 0.0),
            wards_placed=d.get("wards_placed", 0),
            wards_killed=d.get("wards_killed", 0),
            control_wards=d.get("control_wards", 0),
            gold=d.get("gold", 0),
            gold_per_min=d.get("gold_per_min", 0.0),
            gold_15=d.get("gold_15"),
            gold_lead_15=d.get("gold_lead_15"),
            total_heal=d.get("total_heal", 0),
            damage_mitigated=d.get("damage_mitigated", 0),
            cc_time=d.get("cc_time", 0),
            heals_on_teammates=d.get("heals_on_teammates", 0),
            damage_shielded=d.get("damage_shielded", 0),
            total_damage_taken=d.get("total_damage_taken", 0),
            physical_damage_taken=d.get("physical_damage_taken", 0),
            magic_damage_taken=d.get("magic_damage_taken", 0),
            largest_killing_spree=d.get("largest_killing_spree", 0),
            first_blood_kill=d.get("first_blood_kill", False),
            first_blood_assist=d.get("first_blood_assist", False),
            turret_kills=d.get("turret_kills", 0),
            inhibitor_kills=d.get("inhibitor_kills", 0),
            objectives_stolen=d.get("objectives_stolen", 0),
            bounty_level=d.get("bounty_level", 0),
            double_kills=d.get("double_kills", 0),
            triple_kills=d.get("triple_kills", 0),
            quadra_kills=d.get("quadra_kills", 0),
            penta_kills=d.get("penta_kills", 0),
            spell1_casts=d.get("spell1_casts", 0),
            spell2_casts=d.get("spell2_casts", 0),
            spell3_casts=d.get("spell3_casts", 0),
            spell4_casts=d.get("spell4_casts", 0),
            build_order=d.get("build_order", []),
            first_item=d.get("first_item"),
            final_items=d.get("final_items", []),
            pick_order=d.get("pick_order"),
            enemy_pick_order=d.get("enemy_pick_order"),
            kp_pct=d.get("kp_pct", 0.0),
            enemy=EnemyPlayer.from_dict(d.get("enemy")),
            all_players=[PlayerStats.from_dict(p) for p in d.get("all_players", [])],
            my_team=TeamObjectives.from_dict(d.get("my_team")),
            enemy_team=TeamObjectives.from_dict(d.get("enemy_team")),
        )
        # Compute kp_pct if missing or zero (backward compat with old caches)
        if g.kp_pct == 0.0 and g.my_team.kills > 0:
            g.kp_pct = round((g.kills + g.assists) / g.my_team.kills * 100, 1)
        return g