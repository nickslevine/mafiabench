import asyncio
import random
import time
from loguru import logger
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Coroutine, Any
import numpy as np
from scipy.stats import spearmanr  # type: ignore

from contest import Contest, ContestStats
from mafia import GameStats, PlayerName, Role
from elo_ratings import ELOSystem  # Import the new ELO system

# Set up logger
# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
# logger = logging.getLogger(__name__)


class Tournament:
    """
    Manages a series of Contests between models using a Swiss system
    to efficiently determine relative rankings using the ELO rating system.
    """

    def __init__(
        self,
        model_names: List[str],
        player_names: List[PlayerName],
        num_rounds: int,
        games_per_contest: int = 4,
        n_players_per_game: int = 7,
        n_mafia_per_game: int = 2,
        temperature: float = 0.7,
        limiter_requests_per_second: float = 60.0,
        n_concurrent_contests: int = 1,
        n_concurrent_games_per_contest: int = 5,
        elo_k_factor: float = 32,  # K-factor for ELO updates
        elo_initial_rating: float = 1500,  # Initial ELO rating
    ):
        """
        Initializes the Tournament with ELO rating system.

        Args:
            model_names (List[str]): List of unique names for the participating models.
            player_names (List[PlayerName]): List of names to be used for players in games.
            num_rounds (int): The number of rounds to run in the Swiss tournament.
            games_per_contest (int): Number of games played in each Contest. Defaults to 4.
            n_players_per_game (int): Number of players in each game. Defaults to 7.
            n_mafia_per_game (int): Number of mafia roles in each game. Defaults to 2.
            temperature (float): Temperature setting for model generation. Defaults to 0.7.
            limiter_requests_per_second (float): Global rate limit for API calls. Defaults to 60.0.
            n_concurrent_contests (int): Max number of Contests to run in parallel per round. Defaults to 1.
            n_concurrent_games_per_contest (int): Max number of Games to run in parallel within each Contest. Defaults to 5.
            elo_k_factor (float): K-factor for the ELO system. Defaults to 32.
            elo_initial_rating (float): Initial ELO rating for all models. Defaults to 1500.
        """
        if len(model_names) < 2:
            raise ValueError("Tournament requires at least two models.")
        if len(set(model_names)) != len(model_names):
            raise ValueError("Model names must be unique.")
        if len(player_names) < n_players_per_game:
            raise ValueError(
                f"Not enough player names ({len(player_names)}) for games needing {n_players_per_game}."
            )

        self.model_names = model_names
        self.player_names = player_names
        self.num_rounds = num_rounds
        self.games_per_contest = games_per_contest
        self.n_players_per_game = n_players_per_game
        self.n_mafia_per_game = n_mafia_per_game
        self.temperature = temperature
        self.limiter_requests_per_second = limiter_requests_per_second
        self.n_concurrent_contests = n_concurrent_contests
        self.n_concurrent_games_per_contest = n_concurrent_games_per_contest

        # ELO setup
        self.elo_system = ELOSystem(model_names, elo_k_factor, elo_initial_rating)
        self.rating_history: Dict[str, List[float]] = defaultdict(
            list
        )  # Stores ELO rating per round
        self.match_history: Dict[str, List[str]] = {name: [] for name in model_names}

        self.current_round = 0
        self.all_results: List[
            GameStats
        ] = []  # Store all game stats across the tournament
        self.previous_rankings: Optional[List[str]] = (
            None  # Store previous round's ranking by ELO
        )
        self.stability_stats: List[
            Dict[str, Optional[float]]
        ] = []  # Store {rank_corr} per round

    def _get_model_ratings_sorted(self) -> List[Tuple[str, float]]:
        """Returns models sorted by their current ELO rating."""
        ratings = self.elo_system.get_all_ratings()
        return sorted(ratings.items(), key=lambda item: item[1], reverse=True)

    def _pair_round(self) -> List[Tuple[str, str]]:
        """
        Generates pairings for the next round using Swiss system logic based on ELO.
        Pairs models with similar ratings that haven't played yet, if possible.
        Handles byes for odd numbers of players.
        """
        if self.current_round == 0:
            # Random pairing for the first round
            shuffled_models = random.sample(self.model_names, len(self.model_names))
        else:
            # Sort by rating for subsequent rounds
            sorted_models = [name for name, _ in self._get_model_ratings_sorted()]
            shuffled_models = sorted_models  # Use sorted list directly

        pairings = []
        paired_models: set[str] = set()
        models_to_pair: List[str] = list(
            shuffled_models
        )  # Explicit type hint for the list

        # Handle potential bye
        bye_model = None
        if len(models_to_pair) % 2 != 0:
            # Give bye to the lowest-rated player who hasn't had one (simplification: just lowest rated)
            # A more robust implementation would track byes explicitly.
            bye_model = models_to_pair.pop(-1)
            paired_models.add(bye_model)
            logger.info(f"Round {self.current_round + 1}: {bye_model} receives a bye.")
            # ELO typically doesn't change for a bye.

        # Basic Swiss pairing: pair adjacent players in the sorted list
        i = 0
        while i < len(models_to_pair):
            model_a = models_to_pair[i]
            # Find the best match for model_a among remaining players
            best_match_idx = -1
            for j in range(i + 1, len(models_to_pair)):
                model_b = models_to_pair[j]
                # Check if they haven't played before
                if model_b not in self.match_history[model_a]:
                    best_match_idx = j
                    break  # Found the highest-rated available opponent they haven't played

            if best_match_idx != -1:
                model_b = models_to_pair.pop(best_match_idx)  # Remove paired model B
                pairings.append((model_a, model_b))  # type: ignore
                paired_models.add(model_a)
                paired_models.add(model_b)
                self.match_history[model_a].append(model_b)
                self.match_history[model_b].append(model_a)
                models_to_pair.pop(i)  # Remove paired model A (indices shift)
                # Don't increment i, as the list shortened
            else:
                # If no new opponent found, allow rematch with the closest rated opponent
                # (Simple approach: pair with next in list even if rematch)
                if i + 1 < len(models_to_pair):
                    model_b = models_to_pair.pop(i + 1)  # Remove paired model B
                    logger.warning(
                        f"Round {self.current_round + 1}: Allowing rematch between {model_a} and {model_b}"
                    )
                    pairings.append((model_a, model_b))  # type: ignore
                    paired_models.add(model_a)
                    paired_models.add(model_b)
                    # Update match history even for rematches if needed for tracking
                    if model_b not in self.match_history[model_a]:
                        self.match_history[model_a].append(model_b)
                        self.match_history[model_b].append(model_a)
                    models_to_pair.pop(i)  # Remove paired model A
                    # Don't increment i
                else:
                    # Should not happen with correct logic, but handle gracefully
                    logger.error(f"Could not find pair for {model_a}")
                    i += 1  # Move to next potential model A

        logger.info(f"Round {self.current_round + 1} pairings: {pairings}")
        return pairings  # type: ignore

    async def run_round(self) -> List[GameStats]:
        """
        Runs one round of the tournament: gets pairings, runs contests, returns results.
        """
        self.current_round += 1
        logger.info(f"--- Starting Round {self.current_round} --- ")
        pairings = self._pair_round()

        if not pairings:
            logger.info("No pairings generated for this round.")
            return []

        # Explicitly type contest_tasks
        contest_tasks: List[
            Coroutine[Any, Any, Tuple[ContestStats, List[GameStats]]]
        ] = []
        for i, (model_a, model_b) in enumerate(pairings):
            contest_name = f"R{self.current_round}_M{i + 1}_{model_a.replace('/', '_')}_vs_{model_b.replace('/', '_')}"
            contest = Contest(
                name=contest_name,
                n_games=self.games_per_contest,
                n_players=self.n_players_per_game,
                n_mafia=self.n_mafia_per_game,
                player_names=self.player_names,  # Pass PlayerName list
                model_a=model_a,
                model_b=model_b,
                temperature=self.temperature,
                limiter_requests_per_second=self.limiter_requests_per_second,
                n_concurrent_games=self.n_concurrent_games_per_contest,
            )
            # contest.run returns (ContestStats, List[GameStats])
            contest_tasks.append(contest.run())

        # Limit concurrent contests
        semaphore = asyncio.Semaphore(self.n_concurrent_contests)
        # Explicitly type round_game_stats
        round_game_stats: List[
            GameStats
        ] = []  # Collect GameStats from all contests in the round

        # Define type hints for the async helper function
        async def run_contest_with_semaphore(
            task: Coroutine[Any, Any, Tuple[ContestStats, List[GameStats]]],
        ) -> List[GameStats]:
            async with semaphore:
                contest_stats, game_stats_list = await task
                logger.info(f"Contest {contest_stats.name} finished.")
                return game_stats_list  # Return only the list of GameStats

        # Run contests with concurrency control
        results_list: List[List[GameStats]] = await asyncio.gather(
            *(run_contest_with_semaphore(task) for task in contest_tasks)
        )

        # Flatten the list of lists of GameStats
        for game_list in results_list:
            round_game_stats.extend(game_list)

        self.all_results.extend(round_game_stats)
        return round_game_stats

    def _update_ratings(self, round_results: List[GameStats]):
        """
        Updates ELO ratings based on the results of a completed round.
        """
        if not round_results:
            logger.warning(
                f"No results to process for Round {self.current_round}. Skipping rating update."
            )
        else:
            # Prepare results in the format needed by ELOSystem
            # (model_a, model_b, score_a)
            game_updates: List[Tuple[str, str, float]] = []
            for game in round_results:
                model_mafia = game.model_mafia
                model_town = game.model_townsperson

                if game.winner == Role.MAFIA.value:
                    score_mafia = 1.0
                elif game.winner == Role.TOWNSPERSON.value:
                    score_mafia = 0.0
                else:
                    logger.warning(
                        f"Unexpected winner value '{game.winner}' in GameStats. Treating as draw."
                    )
                    score_mafia = 0.5

                game_updates.append((model_mafia, model_town, score_mafia))

            # Update ratings using the ELO system
            self.elo_system.record_batch_games(game_updates)

            logger.info(f"--- Ratings after Round {self.current_round} --- ")
            current_ratings = self.elo_system.get_all_ratings()
            sorted_ratings = sorted(
                current_ratings.items(), key=lambda item: item[1], reverse=True
            )
            for name, rating in sorted_ratings:
                logger.info(f"  {name}: Rating={rating:.2f}")

        # Record history (even if no games were played this round for some models)
        current_ratings_all = self.elo_system.get_all_ratings()
        for name in self.model_names:
            self.rating_history[name].append(
                current_ratings_all.get(
                    name,
                    self.rating_history[name][-1]
                    if self.rating_history[name]
                    else self.elo_system.ratings[name],
                )
            )  # Use last known rating if missing this round

        # --- Stability Calculations ---
        current_ranking_list = [name for name, _ in self._get_model_ratings_sorted()]
        rank_corr = self._calculate_rank_correlation(current_ranking_list)

        self.stability_stats.append({"rank_corr": rank_corr})
        logger.info(
            f"Stability Metrics: Rank Correlation = {rank_corr if rank_corr is not None else 'N/A'}"
        )

        # Update previous ranking for next round
        self.previous_rankings = current_ranking_list
        # -----------------------------

    def _calculate_rank_correlation(
        self, current_ranking: List[str]
    ) -> Optional[float]:
        """
        Calculates Spearman rank correlation between the current round's ranking
        and the previous round's ranking.
        Requires numpy and scipy installed.
        Returns None if dependencies are missing, it's the first round, or rankings can't be compared.
        """

        if self.previous_rankings is None or len(self.previous_rankings) != len(
            current_ranking
        ):
            return None

        # Create mapping from model name to rank for both lists
        prev_rank_map = {name: i for i, name in enumerate(self.previous_rankings)}
        curr_rank_map = {name: i for i, name in enumerate(current_ranking)}

        # Ensure we compare ranks for the same set of models
        models = list(curr_rank_map.keys())
        prev_ranks = [prev_rank_map.get(model, -1) for model in models]
        curr_ranks = [curr_rank_map.get(model, -1) for model in models]

        # Filter out any potential models not present in both
        valid_indices = [i for i, r in enumerate(prev_ranks) if r != -1]
        if len(valid_indices) < 2:
            return None  # Need at least 2 data points for correlation

        prev_ranks_valid = [prev_ranks[i] for i in valid_indices]
        curr_ranks_valid = [curr_ranks[i] for i in valid_indices]

        try:
            correlation, _ = spearmanr(prev_ranks_valid, curr_ranks_valid)
            if np.isnan(correlation):  # type: ignore
                return (
                    None  # Handle case where correlation is NaN (e.g., zero variance)
                )
            return correlation  # type: ignore
        except Exception as e:
            logger.error(f"Error calculating rank correlation: {e}")
            return None

    async def run_tournament(self) -> List[Tuple[str, float]]:
        """
        Runs the full tournament for the specified number of rounds using ELO.
        """
        logger.info(
            f"Starting ELO tournament with {len(self.model_names)} models for {self.num_rounds} rounds."
        )
        start_time = time.time()

        # Initial ratings log
        logger.info("--- Initial Ratings --- ")
        initial_ratings = self._get_model_ratings_sorted()
        for name, rating in initial_ratings:
            self.rating_history[name].append(rating)
            logger.info(f"  {name}: Rating={rating:.2f}")

        # Store initial state as "previous" for first correlation calculation
        self.previous_rankings = [name for name, _ in initial_ratings]

        for _ in range(self.num_rounds):
            round_results = await self.run_round()
            self._update_ratings(round_results)  # Updates ratings and logs stability
            # Logger info now happens inside _update_ratings

        end_time = time.time()
        logger.info(f"Tournament finished in {end_time - start_time:.2f} seconds.")
        logger.info("--- Final Rankings (ELO) --- ")
        final_rankings = self._get_model_ratings_sorted()
        for i, (name, rating) in enumerate(final_rankings):
            logger.info(f"  {i + 1}. {name}: Rating={rating:.2f}")

        return final_rankings

    def get_final_ratings(self) -> Dict[str, float]:
        """Returns the final ELO ratings for each model."""
        return self.elo_system.get_all_ratings()

    def get_rating_history(self) -> Dict[str, List[float]]:
        """Returns the ELO rating history for each model across rounds."""
        return self.rating_history


# Example Usage
async def main() -> None:
    models = [
        "mistralai/mistral-7b-instruct",
        "google/gemma-2-9b-it",
        "mistralai/mistral-nemo",
        "google/gemini-flash-1.5-8b",
    ]
    player_names_list = [
        "Alice",
        "Bob",
        "Charlie",
        "David",
        "Eve",
        "Frank",
        "Grace",
        "Henry",
        "Ivy",
        "Jack",
        "Kate",
        "Liam",
        "Mia",
        "Noah",
    ]  # Need at least n_players_per_game

    tournament = Tournament(
        model_names=models,
        player_names=[PlayerName(name) for name in player_names_list],
        num_rounds=2,  # Adjust as needed
        games_per_contest=4,
        n_players_per_game=8,
        n_mafia_per_game=2,
        n_concurrent_contests=2,
        n_concurrent_games_per_contest=5,
        elo_k_factor=32,  # Optional: Adjust K-factor here
    )

    final_rankings = await tournament.run_tournament()

    logger.info("Final Rankings:")
    logger.info(final_rankings)

    logger.info("\nFinal ELO Ratings:")
    logger.info(tournament.get_final_ratings())
    logger.info("\nELO Rating History:")
    logger.info(tournament.get_rating_history())
    logger.info("\nStability Stats (Rank Corr per round):")
    logger.info(tournament.stability_stats)


if __name__ == "__main__":
    # Requires OPEN_ROUTER_API_KEY env var
    # Requires numpy & scipy for rank correlation: pip install numpy scipy
    asyncio.run(main())
