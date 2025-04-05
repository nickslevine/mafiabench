#!/usr/bin/env python3
import argparse
import json
from typing import Dict, Any

from mafia import PlayerName
from tournament import Tournament
from tui import TournamentTUI
from elo_ratings import ELOSystem


def load_tournament_state(json_path: str) -> Dict[str, Any]:
    """
    Load tournament state from a JSON file.

    Args:
        json_path (str): Path to the tournament JSON file

    Returns:
        Dict[str, Any]: Tournament state data
    """
    with open(json_path, "r") as f:
        return json.load(f)


def create_tournament_from_state(
    state: Dict[str, Any], additional_rounds: int
) -> Tournament:
    """
    Create a new tournament instance with state loaded from saved data.

    Args:
        state (Dict[str, Any]): Loaded tournament state
        additional_rounds (int): Number of additional rounds to run

    Returns:
        Tournament: Initialized tournament with preserved state
    """
    metadata = state["tournament_metadata"]

    # Create tournament with same configuration
    tournament = Tournament(
        model_names=metadata["model_names"],
        player_names=[
            PlayerName(name)
            for name in [
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
                "Olivia",
                "Peter",
                "Quinn",
                "Rose",
                "Sam",
                "Tyler",
                "Uma",
                "Victor",
                "Wendy",
            ]
        ],
        num_rounds=additional_rounds,  # Set to new number of rounds
        games_per_contest=metadata["games_per_contest"],
        n_players_per_game=metadata["n_players_per_game"],
        n_mafia_per_game=metadata["n_mafia_per_game"],
        temperature=metadata["temperature"],
        limiter_requests_per_second=metadata["limiter_requests_per_second"],
        n_concurrent_contests=metadata["n_concurrent_contests"],
        n_concurrent_games_per_contest=metadata["n_concurrent_games_per_contest"],
        elo_k_factor=metadata["elo_k_factor"],
        elo_initial_rating=metadata["elo_initial_rating"],
    )

    # Restore ELO ratings
    tournament.elo_system = ELOSystem(
        metadata["model_names"],
        metadata["elo_k_factor"],
        metadata["elo_initial_rating"],
    )
    for model, rating in state["final_elo_ratings"].items():
        tournament.elo_system.ratings[model] = rating

    # Restore rating history
    tournament.rating_history = state["elo_rating_history_by_round"]

    # Restore match history
    tournament.match_history = {name: [] for name in metadata["model_names"]}
    for contest in state["contests"]:
        model_a = contest["model_a"]
        model_b = contest["model_b"]
        tournament.match_history[model_a].append(model_b)
        tournament.match_history[model_b].append(model_a)

    # Set current round to last completed round
    tournament.current_round = metadata["num_rounds"]

    # Store completed contests data
    tournament.completed_contests_data = state["contests"]

    return tournament


def main():
    """Main entry point for continuing a tournament from JSON state."""
    parser = argparse.ArgumentParser(
        description="Continue a Mafia Tournament from saved state with TUI"
    )

    parser.add_argument(
        "--json-file", required=True, help="Path to tournament JSON state file"
    )
    parser.add_argument(
        "--additional-rounds",
        type=int,
        required=True,
        help="Number of additional tournament rounds to run",
    )

    args = parser.parse_args()

    # Load state from JSON
    state = load_tournament_state(args.json_file)

    # Create tournament with loaded state
    tournament = create_tournament_from_state(state, args.additional_rounds)

    # Run the TUI with the restored tournament
    app = TournamentTUI(tournament, event_log_max_lines=5)
    app.run()


if __name__ == "__main__":
    main()
