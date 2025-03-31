#!/usr/bin/env python3
import argparse

from mafia import PlayerName
from tournament import Tournament
from tui import TournamentTUI


def main():
    """Main entry point for the tournament TUI."""
    parser = argparse.ArgumentParser(description="Run a Mafia Tournament with TUI")

    # Tournament options
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Model names to include in the tournament",
    )
    parser.add_argument(
        "--rounds", type=int, default=3, help="Number of tournament rounds"
    )
    parser.add_argument(
        "--games-per-contest", type=int, default=4, help="Number of games per contest"
    )
    parser.add_argument(
        "--players-per-game", type=int, default=8, help="Number of players per game"
    )
    parser.add_argument(
        "--mafia-per-game", type=int, default=2, help="Number of mafia roles per game"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperature setting for model generation",
    )
    parser.add_argument(
        "--request-limit",
        type=float,
        default=60.0,
        help="Rate limit for requests (per second)",
    )
    parser.add_argument(
        "--concurrent-contests",
        type=int,
        default=20,
        help="Number of contests to run concurrently",
    )
    parser.add_argument(
        "--concurrent-games",
        type=int,
        default=4,
        help="Number of games to run concurrently per contest",
    )

    args = parser.parse_args()

    # Basic validation
    if len(args.models) < 2:
        parser.error("At least 2 models must be specified")

    # Generate player names
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

    # Create the tournament
    tournament = Tournament(
        model_names=args.models,
        player_names=[PlayerName(name) for name in player_names_list],
        num_rounds=args.rounds,
        games_per_contest=args.games_per_contest,
        n_players_per_game=args.players_per_game,
        n_mafia_per_game=args.mafia_per_game,
        temperature=args.temperature,
        limiter_requests_per_second=args.request_limit,
        n_concurrent_contests=args.concurrent_contests,
        n_concurrent_games_per_contest=args.concurrent_games,
    )

    # Run the TUI - directly creating and running the app
    app = TournamentTUI(tournament)
    app.run()


if __name__ == "__main__":
    main()
