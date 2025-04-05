import datetime
import json
from mafia import ContestStats, GameStats, PlayerName
from rate_limiter import GlobalRateLimiter
from game import Game, ProgressCallback, EventCallback
import asyncio
import time

# import logging
import os
from typing import Optional, Coroutine, Any, List, Tuple

# Suppress httpx info logs
# logging.getLogger("httpx").setLevel(logging.WARNING)


class Contest:
    def __init__(
        self,
        name: str,
        n_games: int,
        n_players: int,
        n_mafia: int,
        player_names: List[PlayerName],
        model_a: str,
        model_b: Optional[str] = None,
        temperature: float = 0.7,
        limiter_requests_per_second: float = 60.0,
        n_concurrent_games: int = 5,
        progress_callback: Optional[ProgressCallback] = None,
        event_callback: Optional[EventCallback] = None,
        tournament_dir: Optional[str] = None,
    ):
        """Initialize a new contest instance.

        Args:
            name (str): Name of the contest
            n_games (int): Number of games to run
            n_players (int): Number of players per game
            n_mafia (int): Number of mafia roles per game
            player_names (List[PlayerName]): List of player names to use
            model_a (str): First model to use
            model_b (Optional[str]): Second model to use, defaults to model_a if None
            temperature (float): Temperature for model generation
            limiter_requests_per_second (float): Rate limit for API calls
            n_concurrent_games (int): Maximum number of concurrent games
            progress_callback (Optional[ProgressCallback]): Callback for progress updates
            event_callback (Optional[EventCallback]): Callback for game events
            tournament_dir (Optional[str]): Directory for tournament results
        """
        self.name = name
        self.n_games = n_games
        self.n_players = n_players
        self.n_mafia = n_mafia
        self.player_names = player_names
        self.model_a = model_a
        self.model_b = model_b if model_b is not None else model_a
        self.temperature = temperature
        self.limiter_requests_per_second = limiter_requests_per_second
        self.n_concurrent_games = n_concurrent_games
        self.progress_callback = progress_callback
        self.event_callback = event_callback
        self.tournament_dir = tournament_dir
        self.start_time = None
        self.end_time = None

        GlobalRateLimiter.initialize(self.limiter_requests_per_second)

    async def run(self) -> Tuple[ContestStats, List[GameStats]]:
        self.start_time = time.perf_counter()
        self.mafia_models = [
            self.model_a if i % 2 == 0 else self.model_b for i in range(self.n_games)
        ]
        game_tasks: List[Coroutine[Any, Any, GameStats]] = []

        for i, mafia_model_for_game in enumerate(self.mafia_models):
            if mafia_model_for_game == self.model_a:
                townsperson_model_for_game = self.model_b
            else:
                townsperson_model_for_game = self.model_a

            game = Game(
                contest_name=self.name,
                n_players=self.n_players,
                n_mafia=self.n_mafia,
                model_mafia=mafia_model_for_game,
                model_townsperson=townsperson_model_for_game,
                player_names=[name for name in self.player_names],
                temperature=self.temperature,
                game_id=i,
                progress_callback=self.progress_callback,
                event_callback=self.event_callback,
                tournament_dir=self.tournament_dir,
            )
            game_tasks.append(game.run())

        # Create a semaphore to limit concurrent games
        semaphore = asyncio.Semaphore(self.n_concurrent_games)

        # Wrap each game task with semaphore control
        async def run_game_with_semaphore(
            game_task: Coroutine[Any, Any, GameStats],
        ) -> GameStats:
            async with semaphore:
                return await game_task

        # Create wrapped tasks for all games
        wrapped_tasks = [run_game_with_semaphore(task) for task in game_tasks]

        # Run all games with concurrency controlled by the semaphore
        individual_game_stats: List[GameStats] = await asyncio.gather(*wrapped_tasks)
        self.end_time = time.perf_counter()
        duration = self.end_time - self.start_time

        # Calculate overall contest stats using the individual results
        contest_summary_stats = ContestStats.from_stats_list(
            individual_game_stats, duration, self.n_concurrent_games, self.name
        )

        self.serialize(contest_summary_stats)
        # Return both the summary stats and the list of individual game stats
        return contest_summary_stats, individual_game_stats

    def serialize(self, stats: ContestStats):
        if self.tournament_dir:
            # Use tournament's results directory
            results_dir = os.path.join(self.tournament_dir, "results")
            os.makedirs(results_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"contest_{self.name}_{self.model_a.replace('/', '_')}_{self.model_b.replace('/', '_')}_{self.n_players}_{self.n_mafia}_{timestamp}.json"
            filepath = os.path.join(results_dir, filename)

            with open(filepath, "w") as f:
                json.dump(stats.summary(), f)
