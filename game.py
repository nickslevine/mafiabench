import asyncio
import datetime
from loguru import logger
import sys
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
from typing import Callable, Optional, List, Any, Coroutine, Dict
from rate_limiter import GlobalRateLimiter

# Define the type for the progress callback
ProgressCallback = Callable[..., None]  # Simple type hint, refine if needed
# --- Define the type for the event callback ---
EventCallback = Callable[[Dict[str, Any]], None]


class Game:
    def __init__(
        self,
        contest_name: str,
        n_players: int,
        n_mafia: int,
        model_mafia: str,
        model_townsperson: str,
        player_names: list[PlayerName],
        temperature: float = 0.7,
        limiter_requests_per_second: float = 60.0,
        game_id: int | None = None,
        verbose: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
        event_callback: Optional[EventCallback] = None,  # Add event_callback parameter
        tournament_dir: Optional[str] = None,  # Add tournament_dir parameter
    ):
        if len(player_names) < n_players:
            raise ValueError(
                f"Not enough player names provided. "
                f"Must provide at least {n_players} player names"
            )

        self.contest_name = contest_name
        self.phase: Phase = Phase.INTRO
        self.players: dict[PlayerName, Player] = {}
        self.n_players = n_players
        self.n_mafia = n_mafia
        self.model_mafia = model_mafia
        self.model_townsperson = model_townsperson
        self.temperature = temperature
        self.player_names: list[PlayerName] = player_names[0 : self.n_players]
        self.day_count = 0
        self.event_log: EventLog = EventLog()
        self.game_index: int = (
            game_id if game_id is not None else random.randint(1000, 9999)
        )
        self.game_id: str = f"game_{self.game_index}"
        self.progress_callback = progress_callback
        self.event_callback = event_callback  # Store event_callback
        self.game_over_reported = False  # Add flag to track if game over was reported
        self.tournament_dir = tournament_dir

        self.start_time = None
        self.end_time = None
        self.validate()

        logger.remove()
        log_level = "INFO" if verbose else "WARNING"
        logger.add(sys.stderr, level=log_level)

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

        # print(self.players)

    def next_phase(self):
        self.phase = self.phase.next()

    @property
    def n_mafia_alive(self) -> int:
        return sum(
            player.role == Role.MAFIA and player.alive
            for player in self.players.values()
        )

    @property
    def n_townsperson_alive(self) -> int:
        return sum(
            player.role == Role.TOWNSPERSON and player.alive
            for player in self.players.values()
        )

    @property
    def mafia_names(self) -> List[PlayerName]:
        return [
            player.name for player in self.players.values() if player.role == Role.MAFIA
        ]

    @property
    def mafia_names_alive(self) -> List[PlayerName]:
        return [
            player.name
            for player in self.players.values()
            if player.role == Role.MAFIA and player.alive
        ]

    @property
    def is_game_over(self) -> bool:
        return (self.n_townsperson_alive <= self.n_mafia_alive) or (
            self.n_mafia_alive == 0
        )

    @property
    def alive_players(self) -> List[PlayerName]:
        return [player.name for player in self.players.values() if player.alive]

    @property
    def eliminated_players(self) -> List[PlayerName]:
        return [player.name for player in self.players.values() if not player.alive]

    @property
    def eliminated_mafia(self) -> List[PlayerName]:
        return [
            player.name
            for player in self.players.values()
            if player.role == Role.MAFIA and not player.alive
        ]

    def _report_event(self, event_type: str, data: Dict[str, Any]):
        """Helper method to safely call the event callback."""
        if self.game_over_reported:
            return  # Don't report events after game over

        if self.event_callback:
            event_data = {
                "internal_game_id": self.game_id,
                "contest_name": self.contest_name,
                "game_index": self.game_index,
                "event_type": event_type,
                "data": data,  # Nested dictionary for specific event info
            }
            try:
                self.event_callback(event_data)
            except Exception as e:
                logger.error(f"Event callback failed for game {self.game_id}: {e}")

    def _report_progress(
        self,
        phase_name: str,
        step: Optional[int],
        total: Optional[int],
        text: Optional[str] = None,
        updating_kb: bool = False,
        kb_player_type: Optional[str] = None,
        clear_kb_status: bool = False,
    ):
        """Helper method to safely call the progress callback.
        Will not report anything if game_over_reported is True.
        """
        # Do not report any progress if the game over signal has already been sent.
        if self.game_over_reported:
            return

        if self.progress_callback:
            # Always prepare the full data dict
            full_data = {
                "mafia_model": self.model_mafia,
                "town_model": self.model_townsperson,
                "phase": str(self.phase),
                "day_count": self.day_count,
                "mafia_alive": self.n_mafia_alive,
                "townspeople_alive": self.n_townsperson_alive,
            }

            try:
                self.progress_callback(
                    # Identifiers
                    internal_game_id=self.game_id,  # Use internal ID for callback key
                    contest_name=self.contest_name,
                    game_index=self.game_index,
                    # Progress info
                    phase_name=phase_name,
                    step=step,
                    total=total,
                    text=text,
                    # Full state data (optional)
                    full_data=full_data,
                    # Additional info
                    updating_kb=updating_kb,
                    kb_player_type=kb_player_type,
                    clear_kb_status=clear_kb_status,
                )
            except Exception as e:
                logger.error(f"Progress callback failed for game {self.game_id}: {e}")

    async def run(self) -> GameStats:
        """Run the game until completion."""
        self.start_time = time.perf_counter()
        while not self.is_game_over:
            await self.run_phase()
            self.next_phase()
        return await self.game_over()

    async def run_phase(self):
        """Run a single phase of the game."""
        logger.info(f"Running phase: {self.phase} on day {self.day_count}")
        if self.phase == Phase.DAY:
            await self.run_day()
        elif self.phase == Phase.NIGHT:
            await self.run_night()
        elif self.phase == Phase.INTRO:
            await self.run_intro()
        else:
            raise ValueError(f"Invalid phase: {self.phase}")

        # Check for game over after each phase
        if self.is_game_over:
            logger.info("Game over detected after phase completion")
            self._report_game_over()

    async def run_intro(self):
        """
        Execute the introduction phase where all players introduce themselves
        and make the case for why they are not mafia.

        This happens on day 1 before any eliminations.
        """

        player_order = random.sample(self.alive_players, len(self.alive_players))
        num_players = len(player_order)
        messages: EventLog = EventLog()

        for i, player_name in enumerate(player_order):
            self._report_progress(
                "Intro",
                step=i + 1,
                total=num_players,
                text=f"Speaking: {player_name} ({i + 1}/{num_players})",
            )

            p: Player = self.players[player_name]
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
                event_type=EventType.INTRO_STATEMENT,
                player=p.name,
                statement=response,
                phase=Phase.INTRO,
                day_count=self.day_count,
            )
            messages.add(evt)
            self.event_log.add(evt)

            # --- Report Speech Event ---
            self._report_event("SPEECH", {"player": p.name, "text": response})
            # -------------------------

        self._report_progress("Intro", step=None, total=None, text=None)
        await self.update_knowledge_bases(Phase.INTRO, str(messages))

    async def update_knowledge_bases(self, phase: Phase, phase_context: str):
        """Update knowledge bases for all relevant players after a phase."""
        summary_tasks: List[Coroutine[Any, Any, str]] = []  # Correct type hint
        if phase == Phase.NIGHT:
            players_to_update = self.mafia_names_alive
            player_type = "Mafia"
        else:
            players_to_update = self.alive_players
            player_type = "Players"

        # Report start of KB updates with new phrasing
        self._report_progress(
            phase_name=str(phase),
            step=None,
            total=None,
            text=f"{player_type} updating their notes...",  # New phrasing
            updating_kb=True,
            kb_player_type=player_type,
        )

        for player in players_to_update:
            p: Player = self.players[player]
            summary_tasks.append(
                self.get_and_update_player_summary(p, phase, phase_context)
            )
        await asyncio.gather(*summary_tasks)

        # Clear KB update status and text
        self._report_progress(
            phase_name=str(phase),
            step=None,
            total=None,
            text=None,
            clear_kb_status=True,
        )

    async def get_and_update_player_summary(
        self, player: Player, phase: Phase, phase_context: str
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
                str(phase),  # Convert Phase enum to string
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
        self._report_progress("Day Vote", step=None, total=None, text=None)

    async def run_day_discussion(self):
        player_order = random.sample(self.alive_players, len(self.alive_players))
        num_players = len(player_order)
        messages: EventLog = EventLog()

        for i, player_name in enumerate(player_order):
            self._report_progress(
                "Day Discussion",
                step=i + 1,
                total=num_players,
                text=f"Speaking: {player_name} ({i + 1}/{num_players})",
            )

            p: Player = self.players[player_name]
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
                event_type=EventType.DAY_STATEMENT,
                player=p.name,
                statement=response,
                phase=Phase.DAY,
                day_count=self.day_count,
            )
            messages.add(evt)
            self.event_log.add(evt)

            # --- Report Speech Event ---
            self._report_event("SPEECH", {"player": p.name, "text": response})
            # -------------------------

        self._report_progress("Day Discussion", step=None, total=None, text=None)
        await self.update_knowledge_bases(Phase.DAY, str(messages))

    async def get_day_vote(self, player: Player) -> Dict[str, str]:
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
        # Consider reporting progress *after* vote received?
        # self._report_progress("Day Vote", step=?, total=?, text=f"Vote received from {player.name}")
        return dict(player=player.name, vote=response)

    async def get_night_vote(self, player: Player) -> Dict[str, str]:
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
        # Consider reporting progress *after* vote received?
        # self._report_progress("Night Vote", step=?, total=?, text=f"Vote received from {player.name}")
        return dict(player=player.name, vote=response)

    async def run_day_vote(self):
        vote_tasks: List[Coroutine[Any, Any, Dict[str, str]]] = []
        num_voters = len(self.alive_players)
        self._report_progress(
            "Day Vote", step=0, total=num_voters, text="Collecting votes..."
        )

        for player_name in self.alive_players:
            p: Player = self.players[player_name]
            vote_tasks.append(self.get_day_vote(p))

        results: List[Dict[str, str]] = await asyncio.gather(*vote_tasks)

        self._report_progress(
            "Day Vote", step=num_voters, total=num_voters, text="Tallying votes..."
        )

        votes: dict[PlayerName, PlayerName] = {}
        for result in results:
            player_name = result["player"]
            player = self.players[PlayerName(player_name)]
            vote = result["vote"].strip().split()[-1] if result["vote"].strip() else ""
            if vote not in self.alive_players and vote != player_name:
                player.invalid_response_count += 1
                logger.info(f"{player.name} made an invalid vote: {vote}")
            else:
                votes[player.name] = PlayerName(vote)

        if not votes:
            logger.warning("No valid votes cast")
            self._report_progress("Day Vote", step=None, total=None, text=None)
            return
        vote_counts = Counter(votes.values())
        top_votes = vote_counts.most_common()
        if not top_votes:
            logger.warning("No votes to count")
            self._report_progress("Day Vote", step=None, total=None, text=None)
            return

        max_votes = top_votes[0][1]
        tied_choices = [
            choice for choice, vote_count in top_votes if vote_count == max_votes
        ]
        eliminated_player = random.choice(tied_choices)
        logger.info(f"Eliminated player: {eliminated_player}")
        self.players[eliminated_player].alive = False

        # --- Report Day Elimination Event ---
        self._report_event("VOTE_SUMMARY", {"eliminated": eliminated_player})
        # ---------------------------------

        # Check for game over immediately after elimination
        if self.is_game_over:
            logger.info("Game over detected after day vote elimination")
            self._report_game_over()
            return

        evt = VoteSummaryEvent(
            event_type=EventType.DAY_VOTE_SUMMARY,
            votes=votes,
            eliminated_player=eliminated_player,
            phase=Phase.DAY,
            day_count=self.day_count,
        )
        self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.DAY, str(evt))

    def get_role_prompt(self, player: Player) -> str:
        """Get the appropriate role prompt for a player."""
        if player.role == Role.MAFIA:
            return prompts.get_mafia_role_prompt(player.name, self.mafia_names)
        else:
            return prompts.get_townsperson_role_prompt(player.name)

    async def run_night(self):
        """Run the night phase."""
        await self.run_night_discussion()
        await self.run_night_vote()
        self._report_progress("Night Vote", step=None, total=None, text=None)
        self.day_count += 1

    async def run_night_discussion(self):
        mafia_names_alive = self.mafia_names_alive
        if not mafia_names_alive:
            self._report_progress("Night Discussion", step=None, total=None, text=None)
            return

        mafia_order = random.sample(mafia_names_alive, len(mafia_names_alive))
        num_mafia = len(mafia_order)
        messages: EventLog = EventLog()

        for i, player_name in enumerate(mafia_order):
            self._report_progress(
                "Night Discussion",
                step=i + 1,
                total=num_mafia,
                text=f"Mafia speaking: {player_name} ({i + 1}/{num_mafia})",
            )

            p: Player = self.players[player_name]
            response = await p.get_response(
                prompts.get_night_discussion_phase_prompt(
                    p.name,
                    mafia_names_alive,
                    self.alive_players,
                    self.eliminated_players,
                    self.eliminated_mafia,
                    p.knowledge_base,
                    str(messages),
                )
            )

            evt = StatementEvent(
                event_type=EventType.NIGHT_STATEMENT,
                player=p.name,
                statement=response,
                phase=Phase.NIGHT,
                day_count=self.day_count,
            )

            messages.add(evt)
            self.event_log.add(evt)

            # --- Report Speech Event (Mafia only) ---
            self._report_event("SPEECH", {"player": p.name, "text": response})
            # --------------------------------------

        self._report_progress("Night Discussion", step=None, total=None, text=None)
        await self.update_knowledge_bases(Phase.NIGHT, str(messages))

    async def run_night_vote(self):
        """Run the night voting phase."""
        mafia_names_alive = self.mafia_names_alive
        if not mafia_names_alive:
            self._report_progress("Night Vote", step=None, total=None, text=None)
            return

        vote_tasks: List[Coroutine[Any, Any, Dict[str, str]]] = []
        num_voters = len(mafia_names_alive)
        self._report_progress(
            "Night Vote", step=0, total=num_voters, text="Mafia collecting votes..."
        )

        for player_name in mafia_names_alive:
            p: Player = self.players[player_name]
            vote_tasks.append(self.get_night_vote(p))

        results: List[Dict[str, str]] = await asyncio.gather(*vote_tasks)

        self._report_progress(
            "Night Vote",
            step=num_voters,
            total=num_voters,
            text="Mafia tallying votes...",
        )

        votes: dict[PlayerName, PlayerName] = {}
        for result in results:
            player_name = result["player"]
            player = self.players[PlayerName(player_name)]
            vote = result["vote"].strip().split()[-1] if result["vote"].strip() else ""
            if vote not in self.alive_players and vote != player_name:
                player.invalid_response_count += 1
                logger.info(f"{player.name} made an invalid vote: {vote}")
            else:
                votes[player.name] = PlayerName(vote)

        if not votes:
            logger.warning("No valid mafia votes cast")
            self._report_progress("Night Vote", step=None, total=None, text=None)
            return
        vote_counts = Counter(votes.values())
        top_votes = vote_counts.most_common()
        if not top_votes:
            logger.warning("No votes to count")
            self._report_progress("Night Vote", step=None, total=None, text=None)
            return

        max_votes = top_votes[0][1]
        tied_choices = [
            choice for choice, vote_count in top_votes if vote_count == max_votes
        ]
        eliminated_player = random.choice(tied_choices)
        logger.info(f"Eliminated player: {eliminated_player}")
        self.players[eliminated_player].alive = False

        # --- Report Night Elimination Event ---
        self._report_event("MAFIA_KILL", {"eliminated": eliminated_player})
        # ----------------------------------

        # Check for game over immediately after elimination
        if self.is_game_over:
            logger.info("Game over detected after night vote elimination")
            self._report_game_over()
            return

        evt = MafiaKillEvent(
            event_type=EventType.MAFIA_KILL,
            eliminated_player=eliminated_player,
            phase=Phase.NIGHT,
            day_count=self.day_count,
        )
        self.event_log.add(evt)

        await self.update_knowledge_bases(Phase.DAY, str(evt))

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
            mafia_timeout_count=sum(
                player.timeout_count
                for player in self.players.values()
                if player.role == Role.MAFIA
            ),
            townsperson_timeout_count=sum(
                player.timeout_count
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
            game_duration=self.end_time - self.start_time,  # type: ignore
            game_rounds=self.day_count,
        )

    def serialize(self, stats: GameStats):
        if self.tournament_dir:
            # Use tournament's directory structure
            results_dir = os.path.join(self.tournament_dir, "results")
            logs_dir = os.path.join(self.tournament_dir, "logs")
            os.makedirs(results_dir, exist_ok=True)
            os.makedirs(logs_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"game_{self.contest_name}_{self.model_mafia.replace('/', '_')}_{self.model_townsperson.replace('/', '_')}_{self.n_players}_{self.n_mafia}_{timestamp}_{self.game_id}"

            # Save game results
            with open(os.path.join(results_dir, f"{base_filename}.json"), "w") as f:
                json.dump(stats.to_dict(), f)

            # Save game logs
            with open(os.path.join(logs_dir, f"{base_filename}_log.json"), "w") as f:
                json.dump(self.event_log.to_dict(), f)

    async def game_over(self) -> GameStats:
        """Handle game completion and return final stats."""
        self.end_time = time.perf_counter()
        stats = self.calc_stats()
        self.serialize(stats)
        # Game Over progress already reported in run_phase when is_game_over first became true
        return stats

    def _report_game_over(self):
        """Helper method to report game over exactly once."""
        # Check flag *before* logging or reporting
        if not self.game_over_reported:
            self.game_over_reported = True  # Set flag immediately
            logger.info(f"Reporting game over for {self.game_id}")  # Log with ID
            # Directly call progress callback - bypasses the check in _report_progress
            if self.progress_callback:
                try:
                    self.progress_callback(
                        phase_name="Game Over",
                        internal_game_id=self.game_id,
                        contest_name=self.contest_name,
                        game_index=self.game_index,
                        full_data={
                            "mafia_alive": len(self.mafia_names_alive),
                            "townspeople_alive": len(self.alive_players)
                            - len(self.mafia_names_alive),
                            "phase": "Game Over",
                            "day_count": self.day_count,
                            "mafia_model": self.model_mafia,
                            "town_model": self.model_townsperson,
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Game Over progress callback failed for game {self.game_id}: {e}"
                    )
