import datetime
import json
from mafia import ContestStats, GameStats, PlayerName
from rate_limiter import GlobalRateLimiter
from game import Game
import asyncio
import time
import logging
import os
from typing import Optional, Coroutine, Any, List, Tuple

# Suppress httpx info logs
logging.getLogger("httpx").setLevel(logging.WARNING)


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
    ):
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
        self.start_time = None
        self.end_time = None

        GlobalRateLimiter.initialize(self.limiter_requests_per_second)

    async def run(self) -> Tuple[ContestStats, List[GameStats]]:
        self.start_time = time.perf_counter()
        self.mafia_models = [
            self.model_a if i % 2 == 0 else self.model_b for i in range(self.n_games)
        ]
        game_tasks: List[Coroutine[Any, Any, GameStats]] = []

        for i, mafia_model in enumerate(self.mafia_models):
            if mafia_model == self.model_a:
                townsperson_model = self.model_b
            else:
                townsperson_model = self.model_a

            game = Game(
                self.n_players,
                self.n_mafia,
                mafia_model,
                townsperson_model,
                [str(name) for name in self.player_names],
                self.temperature,
                game_id=i,
            )
            game_tasks.append(game.run())

            # We'll use a semaphore to limit concurrent games
            # Continue collecting all game tasks, but we'll control execution with the semaphore

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
        stats_list: List[GameStats] = await asyncio.gather(*wrapped_tasks)
        self.end_time = time.perf_counter()
        duration = self.end_time - self.start_time
        stats = ContestStats.from_stats_list(
            stats_list, duration, self.n_concurrent_games, self.name
        )
        self.serialize(stats)
        # Return both the summary stats and the list of individual game stats
        return stats, stats_list

    def serialize(self, stats: ContestStats):
        os.makedirs("contest_results", exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        with open(
            f"contest_results/{self.name}_{self.model_a.replace('/', '_')}_{self.model_b.replace('/', '_')}_{self.n_players}_{self.n_mafia}_{timestamp}.json",
            "w",
        ) as f:
            json.dump(stats.summary(), f)
