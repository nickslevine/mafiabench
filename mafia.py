from enum import Enum
import json
import time
from typing import NewType, Optional
from dataclasses import dataclass

# Type alias for player names
PlayerName = NewType("PlayerName", str)


class Role(Enum):
    MAFIA = "mafia"
    TOWNSPERSON = "townsperson"

    def __str__(self):
        return self.value


class Phase(Enum):
    DAY = "day"
    NIGHT = "night"
    INTRO = "intro"

    def next(self):
        if self == Phase.INTRO:
            return Phase.DAY
        elif self == Phase.DAY:
            return Phase.NIGHT
        elif self == Phase.NIGHT:
            return Phase.DAY


class EventType(Enum):
    MAFIA_VOTE = "mafia_vote"
    TOWNSPERSON_VOTE = "townsperson_vote"
    NIGHT_VOTE_SUMMARY = "night_vote_summary"
    DAY_VOTE_SUMMARY = "day_vote_summary"
    INTRO_STATEMENT = "intro_statement"
    DAY_STATEMENT = "day_statement"
    NIGHT_STATEMENT = "night_statement"
    MAFIA_KILL = "mafia_kill"


class Event:
    def __init__(self, event_type: EventType, phase: Phase, day_count: int):
        self.event_type = str(event_type)
        self.phase = str(phase)
        self.day_count = day_count

    def to_dict(self):
        return self.__dict__


class VotingEvent(Event):
    def __init__(
        self,
        event_type: EventType,
        voter: PlayerName,
        target: PlayerName,
        phase: Phase,
        day_count: int,
    ):
        super().__init__(event_type, phase, day_count)
        self.voter = voter
        self.target = target


class StatementEvent(Event):
    def __init__(
        self,
        event_type: EventType,
        speaker: PlayerName,
        statement: str,
        phase: Phase,
        day_count: int,
    ):
        super().__init__(event_type, phase, day_count)
        self.speaker = speaker
        self.statement = statement

    def __str__(self):
        return f"<{self.speaker}>{self.statement.replace('\n', ' ')}</{self.speaker}>"


class VoteSummaryEvent(Event):
    def __init__(
        self,
        event_type: EventType,
        votes: dict[PlayerName, PlayerName],
        result: PlayerName,
        phase: Phase,
        day_count: int,
    ):
        super().__init__(event_type, phase, day_count)
        self.votes = votes
        self.result = result

    def __str__(self):
        if self.phase == Phase.DAY:
            return f"The players have voted on who to eliminate as follows: {self.votes}. The player who was eliminated was {self.result}."
        else:
            return f"The mafia have voted on who to eliminate as follows: {self.votes}. The player who was eliminated was {self.result}."


class MafiaKillEvent(Event):
    def __init__(
        self,
        event_type: EventType,
        victim: PlayerName,
        phase: Phase,
        day_count: int,
    ):
        super().__init__(event_type, phase, day_count)
        self.victim = victim

    def __str__(self):
        return f"Last night, the mafia killed {self.victim}."


class EventLog:
    def __init__(self):
        self.events = []

    def add(self, event: Event):
        self.events.append(event)

    def __str__(self):
        return "\n".join([str(event) for event in self.events])

    @property
    def empty(self):
        return len(self.events) == 0

    def __len__(self):
        return len(self.events)

    def to_dict(self):
        return [x.to_dict() for x in self.events]


@dataclass
class GameStats:
    model_mafia: str
    model_townsperson: str
    winner: str
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

    def to_dict(self):
        return self.__dict__


@dataclass
class ModelContestStats:
    model_name: str
    n_wins_mafia: int
    n_wins_townsperson: int
    n_invalid_votes: int
    total_time: float
    total_messages: int

    def to_dict(self):
        return self.__dict__


@dataclass
class ContestStats:
    name: str
    n_games: int
    n_players: int
    n_mafia: int
    contest_duration: float
    avg_game_duration: float
    game_parallelism: int
    time_finished: float
    model_a_stats: ModelContestStats
    model_b_stats: Optional[ModelContestStats] = None

    @staticmethod
    def games_list_to_model_stats(stats_list: list[GameStats], model: str):
        n_wins_mafia = 0
        n_wins_townsperson = 0
        n_invalid_votes = 0
        total_time = 0
        total_messages = 0
        for game in stats_list:
            if game.model_mafia == model:
                if game.winner == "mafia":
                    n_wins_mafia += 1
                n_invalid_votes += game.mafia_invalid_votes
                total_time += game.mafia_total_time
                total_messages += game.mafia_total_messages
            if game.model_townsperson == model:
                if game.winner == "townsperson":
                    n_wins_townsperson += 1
                n_invalid_votes += game.townsperson_invalid_votes
                total_time += game.townsperson_total_time
                total_messages += game.townsperson_total_messages

        model_stats = ModelContestStats(
            model_name=model,
            n_wins_mafia=n_wins_mafia,
            n_wins_townsperson=n_wins_townsperson,
            n_invalid_votes=n_invalid_votes,
            total_time=total_time,
            total_messages=total_messages,
        )
        return model_stats

    @staticmethod
    def from_stats_list(
        stats_list: list[GameStats], duration: float, n_concurrent_games: int, name: str
    ):
        model_a = stats_list[0].model_mafia
        model_b = stats_list[0].model_townsperson
        multi_model = model_a != model_b

        model_a_stats = ContestStats.games_list_to_model_stats(stats_list, model_a)

        if multi_model:
            model_b_stats = ContestStats.games_list_to_model_stats(stats_list, model_b)
        else:
            model_b_stats = None

        return ContestStats(
            name=name,
            n_games=len(stats_list),
            n_players=stats_list[0].n_players,
            n_mafia=stats_list[0].n_mafia,
            model_a_stats=model_a_stats,
            model_b_stats=model_b_stats,
            contest_duration=duration,
            avg_game_duration=sum([game.game_duration for game in stats_list])
            / len(stats_list),
            game_parallelism=n_concurrent_games,
            time_finished=time.time(),
        )

    def summary(self):
        summary = {
            "model_win_rates": {},
            "role_win_rates": {},
            "model_invalid_votes": {},
            "model_latency": {},
            "contest_duration": self.contest_duration,
            "avg_game_duration": self.avg_game_duration,
        }

        multi_model = self.model_b_stats is not None

        summary["model_win_rates"][self.model_a_stats.model_name] = (
            self.model_a_stats.n_wins_mafia + self.model_a_stats.n_wins_townsperson
        ) / self.n_games

        summary["model_invalid_votes"][self.model_a_stats.model_name] = (
            self.model_a_stats.n_invalid_votes
        )

        summary["model_latency"][self.model_a_stats.model_name] = round(
            self.model_a_stats.total_time / self.model_a_stats.total_messages, 2
        )

        summary["role_win_rates"]["mafia"] = (
            self.model_a_stats.n_wins_mafia
            + (self.model_b_stats.n_wins_mafia if multi_model else 0)
        ) / self.n_games

        summary["role_win_rates"]["townsperson"] = (
            self.model_a_stats.n_wins_townsperson
            + (self.model_b_stats.n_wins_townsperson if multi_model else 0)
        ) / self.n_games

        if multi_model:
            summary["model_win_rates"][self.model_b_stats.model_name] = (
                self.model_b_stats.n_wins_mafia + self.model_b_stats.n_wins_townsperson
            ) / self.n_games

            summary["model_invalid_votes"][self.model_b_stats.model_name] = (
                self.model_b_stats.n_invalid_votes
            )

            summary["model_latency"][self.model_b_stats.model_name] = round(
                self.model_b_stats.total_time / self.model_b_stats.total_messages, 2
            )

        return summary
