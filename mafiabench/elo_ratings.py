import math
from typing import Dict, List, Tuple
from loguru import logger

DEFAULT_K_FACTOR = 32
DEFAULT_RATING = 1500


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """
    Calculates the expected score of player A against player B.

    Args:
        rating_a (float): The ELO rating of player A.
        rating_b (float): The ELO rating of player B.

    Returns:
        float: The expected score for player A (between 0 and 1).
    """
    # Clamp the rating difference to avoid potential overflow/underflow with large differences
    # A difference of > 800 or < -800 results in expected scores very close to 1 or 0 anyway.
    # Common practice in some implementations, though not strictly part of original ELO.
    # Adjust the clamping range (e.g., 400, 800) if needed.
    diff = max(-800.0, min(800.0, rating_b - rating_a))
    return 1.0 / (1.0 + math.pow(10, diff / 400.0))


def update_rating(
    rating: float, actual_score: float, expected_score: float, k_factor: float
) -> float:
    """
    Updates a player's ELO rating based on the outcome of a game.

    Args:
        rating (float): The current rating of the player.
        actual_score (float): The actual score achieved (1 for win, 0.5 for draw, 0 for loss).
        expected_score (float): The expected score calculated before the game.
        k_factor (float): The K-factor, determining the maximum rating change.

    Returns:
        float: The updated ELO rating.
    """
    return rating + k_factor * (actual_score - expected_score)


class ELOSystem:
    """
    Manages ELO ratings for a set of players (models).
    """

    def __init__(
        self,
        model_names: List[str],
        k_factor: float = DEFAULT_K_FACTOR,
        initial_rating: float = DEFAULT_RATING,
    ):
        """
        Initializes the ELO system.

        Args:
            model_names (List[str]): A list of unique names for the models.
            k_factor (float): The K-factor to use for rating updates. Defaults to 32.
            initial_rating (float): The starting ELO rating for all models. Defaults to 1500.
        """
        if len(set(model_names)) != len(model_names):
            raise ValueError("Model names must be unique.")
        self.ratings: Dict[str, float] = {name: initial_rating for name in model_names}
        self.k_factor = k_factor

    def get_rating(self, model_name: str) -> float:
        """
        Retrieves the current rating for a given model.

        Args:
            model_name (str): The name of the model.

        Returns:
            float: The current ELO rating.

        Raises:
            KeyError: If the model name is not found.
        """
        return self.ratings[model_name]

    def get_all_ratings(self) -> Dict[str, float]:
        """
        Returns a dictionary of all current model ratings.

        Returns:
            Dict[str, float]: A mapping from model name to ELO rating.
        """
        return self.ratings.copy()

    def record_game(self, model_a: str, model_b: str, score_a: float):
        """
        Records the outcome of a single game and updates ratings for both models.

        Args:
            model_a (str): The name of the first model.
            model_b (str): The name of the second model.
            score_a (float): The score achieved by model_a (1 for win, 0.5 for draw, 0 for loss).
                         The score for model_b is implicitly 1 - score_a.

        Raises:
            KeyError: If either model name is not found.
            ValueError: If score_a is not 0, 0.5, or 1.
        """
        if model_a not in self.ratings or model_b not in self.ratings:
            raise KeyError(
                f"Model name not found: {model_a if model_a not in self.ratings else model_b}"
            )
        if score_a not in [0.0, 0.5, 1.0]:
            raise ValueError("score_a must be 0 (loss), 0.5 (draw), or 1 (win).")

        rating_a = self.ratings[model_a]
        rating_b = self.ratings[model_b]
        score_b = 1.0 - score_a

        expected_a = calculate_expected_score(rating_a, rating_b)
        expected_b = 1.0 - expected_a  # More direct calculation

        new_rating_a = update_rating(rating_a, score_a, expected_a, self.k_factor)
        new_rating_b = update_rating(rating_b, score_b, expected_b, self.k_factor)

        self.ratings[model_a] = new_rating_a
        self.ratings[model_b] = new_rating_b

    def record_batch_games(self, game_results: List[Tuple[str, str, float]]):
        """
        Records a batch of game outcomes and updates ratings synchronously.
        All rating changes are calculated using ratings from the start of the round,
        then applied simultaneously.

        Args:
            game_results (List[Tuple[str, str, float]]): A list of tuples, where each tuple
                represents a game: (model_a_name, model_b_name, score_for_model_a).
        """
        # Store initial ratings for all models at start of round
        initial_ratings = self.ratings.copy()

        # Calculate all rating changes first
        rating_changes: Dict[str, float] = {model: 0.0 for model in self.ratings}

        for model_a, model_b, score_a in game_results:
            if model_a not in initial_ratings or model_b not in initial_ratings:
                raise KeyError(
                    f"Model name not found: {model_a if model_a not in initial_ratings else model_b}"
                )
            if score_a not in [0.0, 0.5, 1.0]:
                raise ValueError("score_a must be 0 (loss), 0.5 (draw), or 1 (win).")

            score_b = 1.0 - score_a

            # Calculate expected scores using initial ratings
            expected_a = calculate_expected_score(
                initial_ratings[model_a], initial_ratings[model_b]
            )
            expected_b = 1.0 - expected_a

            # Calculate rating changes for both models
            change_a = self.k_factor * (score_a - expected_a)
            change_b = self.k_factor * (score_b - expected_b)

            # Accumulate changes
            rating_changes[model_a] += change_a
            rating_changes[model_b] += change_b

        # Apply all changes simultaneously
        for model, change in rating_changes.items():
            self.ratings[model] = initial_ratings[model] + change


# --- Example Usage ---
if __name__ == "__main__":
    models = ["ModelAlpha", "ModelBeta", "ModelGamma"]
    elo_system = ELOSystem(models, k_factor=32)

    logger.info("Initial Ratings:", elo_system.get_all_ratings())

    # Simulate some games
    # Alpha beats Beta
    elo_system.record_game("ModelAlpha", "ModelBeta", 1.0)
    logger.info("\nAfter Alpha beats Beta:", elo_system.get_all_ratings())

    # Gamma draws with Alpha
    elo_system.record_game("ModelGamma", "ModelAlpha", 0.5)
    logger.info("\nAfter Gamma draws Alpha:", elo_system.get_all_ratings())

    # Beta beats Gamma
    elo_system.record_game("ModelBeta", "ModelGamma", 1.0)
    logger.info("\nAfter Beta beats Gamma:", elo_system.get_all_ratings())

    # Batch update example
    batch_results = [
        ("ModelAlpha", "ModelBeta", 1.0),
        ("ModelAlpha", "ModelGamma", 1.0),
        ("ModelBeta", "ModelGamma", 0.5),
    ]
    # Reset ratings for batch example
    elo_system = ELOSystem(models, k_factor=32)
    logger.info("\nInitial Ratings (for batch):", elo_system.get_all_ratings())
    elo_system.record_batch_games(batch_results)
    logger.info("After batch update:", elo_system.get_all_ratings())
