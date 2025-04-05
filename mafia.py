from __future__ import annotations
from enum import Enum
from typing import NewType, Dict, Any, List
from dataclasses import dataclass, asdict

# Type alias for player names
PlayerName = NewType("PlayerName", str)


class Role(Enum):
    MAFIA = "mafia"
    TOWNSPERSON = "townsperson"

    def __str__(self):
        return self.value


class Phase(Enum):
    INTRO = "intro"
    DAY = "day"
    NIGHT = "night"

    def next(self) -> "Phase":
        if self == Phase.INTRO:
            return Phase.DAY
        elif self == Phase.DAY:
            return Phase.NIGHT
        elif self == Phase.NIGHT:
            return Phase.DAY
        else:
            raise ValueError(f"Invalid phase transition from {self}")

    def __str__(self) -> str:
        return self.value


class EventType(Enum):
    INTRO_STATEMENT = "intro_statement"
    DAY_STATEMENT = "day_statement"
    NIGHT_STATEMENT = "night_statement"
    DAY_VOTE_SUMMARY = "day_vote_summary"
    MAFIA_KILL = "mafia_kill"


@dataclass
class BaseEvent:
    event_type: EventType
    phase: Phase
    day_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "phase": str(self.phase),
            "day_count": self.day_count,
        }


@dataclass
class StatementEvent(BaseEvent):
    player: PlayerName
    statement: str

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({"player": self.player, "statement": self.statement})
        return base_dict


@dataclass
class VoteSummaryEvent(BaseEvent):
    votes: Dict[PlayerName, PlayerName]
    eliminated_player: PlayerName

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update(
            {
                # Convert votes dict keys/values to strings if they aren't already
                "votes": {str(k): str(v) for k, v in self.votes.items()},
                "eliminated_player": self.eliminated_player,
            }
        )
        return base_dict


@dataclass
class MafiaKillEvent(BaseEvent):
    eliminated_player: PlayerName

    def to_dict(self) -> Dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({"eliminated_player": self.eliminated_player})
        return base_dict


class EventLog:
    def __init__(self):
        self.events: List[BaseEvent] = []

    def add(self, event: BaseEvent):
        self.events.append(event)

    def __str__(self):
        return "\n".join(str(event) for event in self.events)

    def to_dict(self) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in self.events]

    @property
    def empty(self) -> bool:
        return len(self.events) == 0


@dataclass
class GameStats:
    model_mafia: str
    model_townsperson: str
    winner: str  # Role enum converted to string
    mafia_invalid_votes: int
    townsperson_invalid_votes: int
    mafia_total_time: float
    townsperson_total_time: float
    mafia_total_messages: int
    townsperson_total_messages: int
    n_players: int
    n_mafia: int
    game_duration: float
    game_rounds: int
    mafia_timeout_count: int
    townsperson_timeout_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert GameStats to a dictionary suitable for JSON serialization."""
        return asdict(self)


@dataclass
class ContestStats:
    name: str
    model_a: str
    model_b: str
    games_played: int
    wins_model_a_as_mafia: int
    wins_model_a_as_town: int
    wins_model_b_as_mafia: int
    wins_model_b_as_town: int
    avg_game_duration: float
    total_duration: float
    n_concurrent_games: int
    avg_rounds_per_game: float
    # Add other fields if needed

    @classmethod
    def from_stats_list(
        cls,
        stats_list: List[GameStats],
        total_duration: float,
        n_concurrent_games: int,
        contest_name: str,
    ) -> "ContestStats":
        # ... existing calculation logic ...
        # Ensure model_a and model_b are determined correctly, perhaps from the first game?
        if not stats_list:
            # Handle case with no games - needs default models
            # This is tricky, maybe Contest should pass models explicitly?
            # For now, let's assume stats_list is never empty for a real contest
            # Or pass model_a/b to this class method? Let's try passing.
            raise ValueError(
                "Cannot create ContestStats from empty stats list without model info"
            )

        # Determine model roles based on first game (assuming balanced contest)
        first_game = stats_list[0]
        # Assume first game's mafia is model_a for consistency, but this might need refinement
        # if contests aren't perfectly balanced or only have one game.
        model_a = first_game.model_mafia
        model_b = first_game.model_townsperson

        wins_model_a_as_mafia = sum(
            1
            for game in stats_list
            if game.model_mafia == model_a and game.winner == Role.MAFIA.value
        )
        wins_model_a_as_town = sum(
            1
            for game in stats_list
            if game.model_townsperson == model_a
            and game.winner == Role.TOWNSPERSON.value
        )
        wins_model_b_as_mafia = sum(
            1
            for game in stats_list
            if game.model_mafia == model_b and game.winner == Role.MAFIA.value
        )
        wins_model_b_as_town = sum(
            1
            for game in stats_list
            if game.model_townsperson == model_b
            and game.winner == Role.TOWNSPERSON.value
        )
        # ... rest of calculations ...

        avg_game_duration = (
            sum(game.game_duration for game in stats_list) / len(stats_list)
            if stats_list
            else 0
        )
        avg_rounds_per_game = (
            sum(game.game_rounds for game in stats_list) / len(stats_list)
            if stats_list
            else 0
        )

        return cls(
            name=contest_name,
            model_a=model_a,
            model_b=model_b,
            games_played=len(stats_list),
            wins_model_a_as_mafia=wins_model_a_as_mafia,
            wins_model_a_as_town=wins_model_a_as_town,
            wins_model_b_as_mafia=wins_model_b_as_mafia,
            wins_model_b_as_town=wins_model_b_as_town,
            avg_game_duration=avg_game_duration,
            total_duration=total_duration,
            n_concurrent_games=n_concurrent_games,
            avg_rounds_per_game=avg_rounds_per_game,
        )

    def summary(self) -> Dict[str, Any]:
        """Return a dictionary summary suitable for JSON serialization."""
        return asdict(self)
