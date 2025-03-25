import asyncio
import datetime
import logging
import time
from collections import Counter
from mafia import (
    EventLog,
    EventType,
    MafiaKillEvent,
    Phase,
    PlayerName,
    Role,
    StatementEvent,
    VoteSummaryEvent,
    GameStats,
)
from player import Player
import random
import os
import json
import prompts

from rate_limiter import GlobalRateLimiter


class Game:
    def __init__(
        self,
        n_players: int,
        n_mafia: int,
        model_mafia: str,
        model_townsperson: str,
        player_names: list[str],
        temperature: float = 0.7,
        limiter_requests_per_second: float = 60.0,
        game_id=None,
    ):
        # Set up logger
        self.logger = logging.getLogger(
            __name__ + (f"_{game_id}" if str(game_id) else "")
        )
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        if len(player_names) < n_players:
            raise ValueError(
                f"Not enough player names provided. "
                f"Must provide at least {n_players} player names"
            )

        self.phase = Phase.INTRO
        self.players = {}
        self.n_players = n_players
        self.n_mafia = n_mafia
        self.model_mafia = model_mafia
        self.model_townsperson = model_townsperson
        self.temperature = temperature
        self.player_names = player_names[0 : self.n_players]
        self.day_count = 0
        self.event_log: EventLog = EventLog()
        self.game_id = game_id

        self.start_time = None
        self.end_time = None
        self.validate()

        self.initialize_players()

        GlobalRateLimiter.initialize(limiter_requests_per_second)

    def validate(self):
        # Validate game setup
        if self.n_players < 4:
            raise ValueError("Game requires at least 4 players")
        if self.n_mafia < 1 or self.n_mafia >= self.n_players // 2:
            raise ValueError(
                f"Invalid number of mafia: {self.n_mafia}. "
                f"Must be between 1 and {self.n_players // 2 - 1}"
            )

        if len(self.player_names) < self.n_players:
            raise ValueError(
                f"Not enough player names provided. "
                f"Must provide at least {self.n_players} player names"
            )

    def initialize_players(self):
        roles = [Role.MAFIA] * self.n_mafia + [Role.TOWNSPERSON] * (
            self.n_players - self.n_mafia
        )
        random.shuffle(roles)

        for name, role in zip(self.player_names, roles):
            if role == Role.MAFIA:
                model = self.model_mafia
            else:
                model = self.model_townsperson
            self.players[name] = Player(name, role, model, self.temperature)

        print(self.players)

    def next_phase(self):
        self.phase = self.phase.next()

    @property
    def n_mafia_alive(self):
        return sum(
            player.role == Role.MAFIA and player.alive
            for player in self.players.values()
        )

    @property
    def n_townsperson_alive(self):
        return sum(
            player.role == Role.TOWNSPERSON and player.alive
            for player in self.players.values()
        )

    @property
    def mafia_names(self):
        return [
            player.name for player in self.players.values() if player.role == Role.MAFIA
        ]

    @property
    def mafia_names_alive(self):
        return [
            player.name
            for player in self.players.values()
            if player.role == Role.MAFIA and player.alive
        ]

    @property
    def is_game_over(self):
        return (self.n_townsperson_alive <= self.n_mafia_alive) or (
            self.n_mafia_alive == 0
        )

    @property
    def alive_players(self):
        return [player.name for player in self.players.values() if player.alive]

    @property
    def eliminated_players(self):
        return [player.name for player in self.players.values() if not player.alive]

    @property
    def eliminated_mafia(self):
        return [
            player.name
            for player in self.players.values()
            if player.role == Role.MAFIA and not player.alive
        ]

    async def run_phase(self):
        self.logger.info(f"Running phase: {self.phase} on day {self.day_count}")
        if self.phase == Phase.DAY:
            await self.run_day()
        elif self.phase == Phase.NIGHT:
            await self.run_night()
        elif self.phase == Phase.INTRO:
            await self.run_intro()
        else:
            raise ValueError(f"Invalid phase: {self.phase}")

    async def run(self):
        self.start_time = time.perf_counter()
        while not self.is_game_over:
            await self.run_phase()
            self.next_phase()
        return await self.game_over()

    async def run_intro(self):
        """
        Execute the introduction phase where all players introduce themselves
        and make the case for why they are not mafia.

        This happens on day 1 before any eliminations.
        """

        player_order = random.sample(self.alive_players, len(self.alive_players))

        messages: EventLog = EventLog()

        for player in player_order:
            p: Player = self.players[player]
            role_prompt = self.get_role_prompt(p)

            response = await p.get_response(
                prompts.get_intro_phase_prompt(
                    role_prompt,
                    player_order,
                    "You are the first to speak\n" if messages.empty else str(messages),
                    p.name,
                )
            )

            evt = StatementEvent(
                EventType.INTRO_STATEMENT,
                p.name,
                response,
                Phase.INTRO,
                self.day_count,
            )
            messages.add(evt)
            self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.INTRO, str(messages))

    async def update_knowledge_bases(self, phase: Phase, phase_context: str):
        summary_tasks = []
        if phase == Phase.NIGHT:
            players_to_update = self.mafia_names_alive
        else:
            players_to_update = self.alive_players

        for player in players_to_update:
            p: Player = self.players[player]
            summary_tasks.append(
                self.get_and_update_player_summary(p, phase, phase_context)
            )
        await asyncio.gather(*summary_tasks)

    async def get_and_update_player_summary(
        self, player: Player, phase: str, phase_context: str
    ) -> str:
        """
        Get player's response to the summary prompt and update their knowledge base.

        Args:
            player: The player to get response from
            phase: Current game phase
            phase_context: Context for the current phase

        Returns:
            str: The player's response
        """
        response = await player.get_response(
            prompts.get_summary_prompt(
                player.name,
                str(player.role),
                phase,
                self.day_count,
                phase_context,
                player.knowledge_base,
                self.mafia_names,
            )
        )

        player.update_knowledge_base(response)

        return response

    async def run_day(self):
        await self.run_day_discussion()
        await self.run_day_vote()

    async def run_day_discussion(self):
        player_order = random.sample(self.alive_players, len(self.alive_players))

        messages: EventLog = EventLog()
        for player in player_order:
            p: Player = self.players[player]
            role_prompt = self.get_role_prompt(p)

            response = await p.get_response(
                prompts.get_day_discussion_phase_prompt(
                    role_prompt,
                    player_order,
                    self.alive_players,
                    self.eliminated_players,
                    p.knowledge_base,
                    "You are the first to speak\n" if messages.empty else str(messages),
                    self.day_count,
                    p.name,
                )
            )

            evt = StatementEvent(
                EventType.DAY_STATEMENT,
                p.name,
                response,
                Phase.DAY,
                self.day_count,
            )
            messages.add(evt)
            self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.DAY, str(messages))

    async def get_day_vote(self, player: Player):
        role_prompt = self.get_role_prompt(player)
        response = await player.get_response(
            prompts.get_day_vote_phase_prompt(
                role_prompt,
                self.alive_players,
                self.eliminated_players,
                player.knowledge_base,
                player.name,
            )
        )

        return dict(player=player.name, vote=response)

    async def get_night_vote(self, player: Player):
        response = await player.get_response(
            prompts.get_night_vote_phase_prompt(
                player.name,
                self.mafia_names_alive,
                self.alive_players,
                self.eliminated_players,
                self.eliminated_mafia,
                player.knowledge_base,
                self.day_count,
            )
        )

        return dict(player=player.name, vote=response)

    async def run_day_vote(self):
        vote_tasks = []
        for player in self.alive_players:
            p: Player = self.players[player]

            vote_tasks.append(self.get_day_vote(p))
        results = await asyncio.gather(*vote_tasks)

        votes: dict[PlayerName, PlayerName] = {}

        for result in results:
            player = self.players[result["player"]]
            # Split on whitespace and take the last entry as the vote
            vote = result["vote"].strip().split()[-1] if result["vote"].strip() else ""
            if vote not in self.alive_players and vote != player.name:
                player.invalid_response_count += 1
                self.logger.info(f"{player.name} made an invalid vote: {vote}")
            else:
                votes[player.name] = vote

        if not votes:
            self.logger.warning("No valid votes cast")
            return

        vote_counts = Counter(votes.values())
        top_votes = vote_counts.most_common()
        if not top_votes:
            self.logger.warning("No votes to count")
            return

        max_votes = top_votes[0][1]
        tied_choices = [
            choice for choice, vote_count in top_votes if vote_count == max_votes
        ]
        eliminated_player = random.choice(tied_choices)

        self.logger.info(f"Eliminated player: {eliminated_player}")

        self.players[eliminated_player].alive = False

        evt = VoteSummaryEvent(
            EventType.DAY_VOTE_SUMMARY,
            votes,
            eliminated_player,
            Phase.DAY,
            self.day_count,
        )
        self.event_log.add(evt)

        print(evt)

        await self.update_knowledge_bases(Phase.DAY, str(evt))

    def get_role_prompt(self, player: Player):
        if player.role == Role.MAFIA:
            return prompts.get_mafia_role_prompt(player.name, self.mafia_names)
        else:
            return prompts.get_townsperson_role_prompt(player.name)

    async def run_night(self):
        await self.run_night_discussion()
        await self.run_night_vote()
        self.day_count += 1

    async def run_night_discussion(self):
        mafia_names = random.sample(self.mafia_names_alive, len(self.mafia_names_alive))
        messages: EventLog = EventLog()
        for player in mafia_names:
            p: Player = self.players[player]
            response = await p.get_response(
                prompts.get_night_discussion_phase_prompt(
                    p.name,
                    mafia_names,
                    self.alive_players,
                    self.eliminated_players,
                    self.eliminated_mafia,
                    p.knowledge_base,
                    str(messages),
                )
            )

            evt = StatementEvent(
                EventType.NIGHT_STATEMENT,
                p.name,
                response,
                Phase.NIGHT,
                self.day_count,
            )

            messages.add(evt)
            self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.NIGHT, str(messages))

    async def run_night_vote(self):
        vote_tasks = []
        for player in self.mafia_names_alive:
            p: Player = self.players[player]

            vote_tasks.append(self.get_night_vote(p))
        results = await asyncio.gather(*vote_tasks)

        votes: dict[PlayerName, PlayerName] = {}

        for result in results:
            player = self.players[result["player"]]
            # Split on whitespace and take the last entry as the vote
            vote = result["vote"].strip().split()[-1] if result["vote"].strip() else ""
            if vote not in self.alive_players and vote != player.name:
                player.invalid_response_count += 1
                self.logger.info(f"{player.name} made an invalid vote: {vote}")
            else:
                votes[player.name] = vote

        if not votes:
            self.logger.warning("No valid votes cast")
            return

        vote_counts = Counter(votes.values())
        top_votes = vote_counts.most_common()
        if not top_votes:
            self.logger.warning("No votes to count")
            return

        max_votes = top_votes[0][1]
        tied_choices = [
            choice for choice, vote_count in top_votes if vote_count == max_votes
        ]
        eliminated_player = random.choice(tied_choices)

        self.logger.info(f"Eliminated player: {eliminated_player}")

        self.players[eliminated_player].alive = False

        evt = MafiaKillEvent(
            EventType.MAFIA_KILL,
            eliminated_player,
            Phase.NIGHT,
            self.day_count,
        )
        self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.DAY, str(evt))
        if self.is_game_over:
            self.logger.info("Game over!")

    def calc_stats(self) -> GameStats:
        winner = Role.MAFIA if self.n_mafia_alive > 0 else Role.TOWNSPERSON
        return GameStats(
            model_mafia=self.model_mafia,
            model_townsperson=self.model_townsperson,
            winner=str(winner),
            mafia_invalid_votes=sum(
                player.invalid_response_count
                for player in self.players.values()
                if player.role == Role.MAFIA
            ),
            townsperson_invalid_votes=sum(
                player.invalid_response_count
                for player in self.players.values()
                if player.role == Role.TOWNSPERSON
            ),
            mafia_total_time=sum(
                player.total_response_time
                for player in self.players.values()
                if player.role == Role.MAFIA
            ),
            townsperson_total_time=sum(
                player.total_response_time
                for player in self.players.values()
                if player.role == Role.TOWNSPERSON
            ),
            mafia_total_messages=sum(
                player.message_count
                for player in self.players.values()
                if player.role == Role.MAFIA
            ),
            townsperson_total_messages=sum(
                player.message_count
                for player in self.players.values()
                if player.role == Role.TOWNSPERSON
            ),
            n_players=self.n_players,
            n_mafia=self.n_mafia,
            game_duration=self.end_time - self.start_time,
            game_rounds=self.day_count,
        )

    def serialize(self, stats: GameStats):
        os.makedirs("results", exist_ok=True)
        os.makedirs("logs", exist_ok=True)

        print(f"Game over. Results: {stats.to_dict()}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        with open(
            f"results/{self.model_mafia.replace('/', '_')}_{self.model_townsperson.replace('/', '_')}_{self.n_players}_{self.n_mafia}_{timestamp}_{self.game_id if self.game_id else ''}.json",
            "w",
        ) as f:
            json.dump(stats.to_dict(), f)

        with open(
            f"logs/{self.model_mafia.replace('/', '_')}_{self.model_townsperson.replace('/', '_')}_{self.n_players}_{self.n_mafia}_{timestamp}_{self.game_id if self.game_id else ''}.json",
            "w",
        ) as f:
            json.dump(self.event_log.to_dict(), f)

    async def game_over(self) -> GameStats:
        self.end_time = time.perf_counter()
        stats = self.calc_stats()
        self.serialize(stats)
        return stats
