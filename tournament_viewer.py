# type: ignore
import streamlit as st
import os
import json
import pandas as pd
from typing import Dict, List, Optional, Any, TypedDict, Union
from datetime import datetime
from plotly.graph_objs._figure import Figure
import plotly.express as px
import plotly.graph_objects as go


class GameData(TypedDict):
    model_mafia: str
    model_townsperson: str
    winner: str
    game_rounds: int
    game_duration: float
    n_players: int
    n_mafia: int


class ContestData(TypedDict):
    contest_name: str
    round_number: int
    model_a: str
    model_b: str
    contest_stats: Dict[str, Any]
    games: List[GameData]


class TournamentMetadata(TypedDict):
    start_time: Optional[str]
    end_time: Optional[str]
    duration_seconds: Optional[float]
    model_names: List[str]
    num_rounds: int
    games_per_contest: int
    n_players_per_game: int
    n_mafia_per_game: int
    temperature: float
    limiter_requests_per_second: float
    n_concurrent_contests: int
    n_concurrent_games_per_contest: int
    elo_k_factor: float
    elo_initial_rating: float
    name: str


class TournamentResults(TypedDict):
    tournament_metadata: TournamentMetadata
    final_elo_ratings: Dict[str, float]
    elo_rating_history_by_round: Dict[str, List[float]]
    contests: List[ContestData]


def load_tournament_data(tournament_dir: str) -> TournamentResults:
    """Load all tournament data from a tournament directory."""
    # Load final results
    final_dir = os.path.join(tournament_dir, "final")
    final_results = None
    for file in os.listdir(final_dir):
        if file.startswith("final_results_"):
            with open(os.path.join(final_dir, file)) as f:
                final_results = json.load(f)
            break

    if not final_results:
        st.error(f"No final results found in {final_dir}")
        st.stop()

    return final_results


def load_game_logs(tournament_dir: str, game_id: str) -> Optional[Dict[str, Any]]:
    """Load detailed game logs for a specific game."""
    logs_dir = os.path.join(tournament_dir, "logs")
    for file in os.listdir(logs_dir):
        if game_id in file and file.endswith("_log.json"):
            with open(os.path.join(logs_dir, file)) as f:
                return json.load(f)
    return None


def display_elo_ratings(final_results: TournamentResults) -> None:
    """Display final ELO ratings in a sortable table."""
    st.header("Final ELO Ratings")

    # Extract final ratings
    ratings = final_results["final_elo_ratings"]
    df_ratings = pd.DataFrame(list(ratings.items()), columns=["Model", "Rating"])

    # Sort by rating descending by default
    df_ratings = df_ratings.sort_values("Rating", ascending=False)

    # Create a centered container with constrained width
    container = st.container()
    with container:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # Display table
            st.dataframe(
                df_ratings,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Model": st.column_config.TextColumn("Model", width=300),
                    "Rating": st.column_config.NumberColumn(
                        "ELO Rating", format="%.1f", width=100
                    ),
                },
            )


def display_win_rates(contests: List[ContestData]) -> None:
    """Display win rates overall and by model."""
    st.header("Win Rates")

    # Count total games and wins
    total_games = 0
    mafia_wins = 0
    town_wins = 0

    # Track wins and games for each model in each role
    mafia_stats: Dict[str, Dict[str, int]] = {}  # model -> {wins, games}
    town_stats: Dict[str, Dict[str, int]] = {}  # model -> {wins, games}

    # Iterate through all games and count wins
    for contest in contests:
        for game in contest["games"]:
            total_games += 1
            mafia_model = game["model_mafia"]
            town_model = game["model_townsperson"]
            winner = game.get("winner", "").lower()

            # Initialize stats for models if not seen before
            for model in [mafia_model, town_model]:
                if model not in mafia_stats:
                    mafia_stats[model] = {"wins": 0, "games": 0}
                if model not in town_stats:
                    town_stats[model] = {"wins": 0, "games": 0}

            # Update games played counts
            mafia_stats[mafia_model]["games"] += 1
            town_stats[town_model]["games"] += 1

            # Update win counts
            if winner == "mafia":
                mafia_wins += 1
                mafia_stats[mafia_model]["wins"] += 1
            elif winner in ["townsperson", "town"]:
                town_wins += 1
                town_stats[town_model]["wins"] += 1

    # Display overall win rates
    col1, col2, col3 = st.columns(3)
    with col1:
        mafia_win_rate = mafia_wins / total_games if total_games > 0 else 0
        st.metric("Mafia Win Rate", str(f"{mafia_win_rate:.1%}"))
    with col2:
        town_win_rate = town_wins / total_games if total_games > 0 else 0
        st.metric("Town Win Rate", str(f"{town_win_rate:.1%}"))
    with col3:
        st.metric("Total Games", str(total_games))

    # Calculate win rates by model and role
    st.subheader("Win Rates By Model and Role")
    model_stats = []

    # Get all unique models
    all_models = set(mafia_stats.keys()) | set(town_stats.keys())

    for model in all_models:
        # Calculate Mafia win rate
        mafia_games = mafia_stats[model]["games"]
        mafia_win_rate = (
            mafia_stats[model]["wins"] / mafia_games if mafia_games > 0 else 0
        )

        # Calculate Town win rate
        town_games = town_stats[model]["games"]
        town_win_rate = town_stats[model]["wins"] / town_games if town_games > 0 else 0

        model_stats.append(
            {
                "Model": model,
                "Mafia Win Rate": mafia_win_rate,
                # "Mafia Wins": mafia_stats[model]["wins"],
                # "Mafia Games": mafia_stats[model]["games"],
                "Town Win Rate": town_win_rate,
                # "Town Wins": town_stats[model]["wins"],
                # "Town Games": town_stats[model]["games"],
            }
        )

    df_stats = pd.DataFrame(model_stats)
    # Sort by overall win rate (average of both roles)
    df_stats["Overall Win Rate"] = (
        df_stats["Mafia Win Rate"] + df_stats["Town Win Rate"]
    ) / 2
    df_stats = df_stats.sort_values("Overall Win Rate", ascending=False)
    df_stats = df_stats.drop("Overall Win Rate", axis=1)  # Remove helper column

    # Display win rates table
    container = st.container()
    with container:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.dataframe(
                df_stats,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Model": st.column_config.TextColumn("Model", width=300),
                    "Mafia Win Rate": st.column_config.NumberColumn(
                        "As Mafia", width=100
                    ),
                    "Mafia Wins": st.column_config.NumberColumn("Mafia Wins", width=80),
                    "Mafia Games": st.column_config.NumberColumn(
                        "Mafia Games", width=80
                    ),
                    "Town Win Rate": st.column_config.NumberColumn(
                        "As Town", width=100
                    ),
                    "Town Wins": st.column_config.NumberColumn("Town Wins", width=80),
                    "Town Games": st.column_config.NumberColumn("Town Games", width=80),
                },
            )


def display_game_results(
    contests: List[ContestData], tournament_dir: str
) -> pd.DataFrame:
    """Display detailed game results in a table."""
    st.header("Game Results")

    # Prepare data for the table
    games_data = []
    for contest in contests:
        for game in contest["games"]:
            games_data.append(
                {
                    "Select": False,  # Add Select column
                    "Contest": contest["contest_name"],
                    "Mafia Model": game["model_mafia"],
                    "Town Model": game["model_townsperson"],
                    "Winner": game["winner"],
                    "Rounds": game["game_rounds"],
                }
            )

    df_games = pd.DataFrame(games_data)

    # Display table with selection
    edited_df = st.data_editor(
        df_games,
        hide_index=True,
        disabled={
            "Contest",
            "Mafia Model",
            "Town Model",
            "Winner",
            "Rounds",
        },  # Only allow Select column to be edited
        use_container_width=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(
                "Select",
                help="Select game to view details",
                default=False,
            ),
            "Contest": st.column_config.TextColumn("Contest", width="medium"),
            "Mafia Model": st.column_config.TextColumn("Mafia Model", width="medium"),
            "Town Model": st.column_config.TextColumn("Town Model", width="medium"),
            "Winner": st.column_config.TextColumn("Winner", width="small"),
            "Rounds": st.column_config.NumberColumn("Rounds", width="small"),
        },
        key="game_table",
        num_rows="dynamic",
    )

    # Check if any row is selected and display game log
    if edited_df is not None:
        selected_row = (
            edited_df[edited_df["Select"]].iloc[0]
            if not edited_df[edited_df["Select"]].empty
            else None
        )
        if selected_row is not None:
            st.write("Debug - Selected Game:", selected_row)
            st.divider()
            display_game_log(tournament_dir, selected_row)

    return df_games


def display_game_log(tournament_dir: str, selected_game: pd.Series) -> None:
    """Display the detailed log for a selected game."""
    st.header(f"Game Log: {selected_game['Contest']}")

    # Load game log
    game_log = load_game_logs(tournament_dir, selected_game["Contest"])
    if not game_log:
        st.error("Game log not found")
        return

    # Track player information
    player_info: Dict[str, Dict[str, str]] = {}

    # Display events in a structured way
    events = game_log

    # Group events by day and phase
    current_day = 0
    current_phase = None

    for event in events:
        event_type = event["event_type"]
        day = event.get("day_count", 0)
        phase = event.get("phase")

        # Track player information from define_player events
        if event_type == "define_player":
            player_info[event["player"]] = {
                "role": event["role"],
                "model": event["model"],
            }

        # Start new day/phase section if needed
        if day != current_day or phase != current_phase:
            st.subheader(f"Day {day} - {phase}")
            current_day = day
            current_phase = phase

        # Display event based on type
        if event_type.lower() in [
            "intro_statement",
            "day_statement",
            "night_statement",
        ]:
            player = event["player"]
            player_details = player_info.get(player, {})
            model_name = player_details.get("model", "Unknown Model")
            role = player_details.get("role", "Unknown Role")

            # Format model name to be more concise
            model_display = (
                model_name.split("/")[-1] if "/" in model_name else model_name
            )

            with st.container():
                st.markdown(
                    f"""
                    <div style="border:1px solid #ccc; border-radius:5px; padding:10px; margin:5px 0; background-color:white;">
                        <div style="margin-bottom:5px;">
                            <span style="color:#1f1f1f; font-size:0.9em;">🗣️ <strong>{player}</strong></span>
                            <span style="color:#666; font-size:0.8em;"> • {role} • {model_display}</span>
                        </div>
                        <div style="background-color:#f0f2f6; border-radius:3px; padding:10px; color:#1f1f1f;">
                            {event["statement"]}
                        </div>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        elif event_type.lower() == "day_vote_summary":
            # Build vote lines HTML
            vote_lines = []
            for voter, vote in event["votes"].items():
                voter_details = player_info.get(voter, {})
                voter_role = voter_details.get("role", "Unknown Role")
                voted_details = player_info.get(vote, {})
                voted_role = voted_details.get("role", "Unknown Role")
                vote_lines.append(
                    f"• <strong>{voter}</strong> ({voter_role}) voted for <strong>{vote}</strong> ({voted_role})"
                )

            eliminated_player = event["eliminated_player"]
            eliminated_details = player_info.get(eliminated_player, {})
            eliminated_role = eliminated_details.get("role", "Unknown Role")

            with st.container():
                st.markdown(
                    f"""
                    <div style="border:1px solid #ccc; border-radius:5px; padding:10px; margin:5px 0; background-color:white;">
                        <div style="margin-bottom:5px;">
                            <span style="color:#1f1f1f; font-size:0.9em;">📊 <strong>Vote Summary</strong></span>
                        </div>
                        <div style="background-color:#f0f2f6; border-radius:3px; padding:10px; color:#1f1f1f;">
                            {"<br>".join(vote_lines)}
                        </div>
                        <div style="margin-top:10px;">
                            <span style="color:#d73027; font-weight:bold;">🚫 Eliminated: {eliminated_player} ({eliminated_role})</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        elif event_type.lower() == "mafia_kill":
            st.markdown(
                f"""
                <div style="border:1px solid #d73027; border-radius:5px; padding:10px; margin:10px 0; background-color:white;">
                    <span style="color:#d73027; font-weight:bold;">🔪 Mafia eliminated: {event["eliminated_player"]}</span>
                </div>
            """,
                unsafe_allow_html=True,
            )


def main() -> None:
    st.set_page_config(page_title="Mafia Tournament Viewer", layout="wide")
    st.title("Mafia Tournament Viewer")

    # Tournament selection
    tournament_base = "tournament_results"
    if not os.path.exists(tournament_base):
        st.error("No tournament results found")
        st.stop()

    tournaments = [
        d
        for d in os.listdir(tournament_base)
        if os.path.isdir(os.path.join(tournament_base, d))
    ]

    if not tournaments:
        st.error("No tournaments found")
        st.stop()

    selected_tournament = st.selectbox(
        "Select Tournament",
        tournaments,
        format_func=lambda x: x.split("_")[0],  # Show only tournament name
    )

    tournament_dir = os.path.join(tournament_base, selected_tournament)
    final_results = load_tournament_data(tournament_dir)

    # Display tournament metadata
    metadata = final_results["tournament_metadata"]
    st.subheader("Tournament Info")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Number of Rounds", metadata["num_rounds"])
    with col2:
        st.metric("Games per Contest", metadata["games_per_contest"])
    with col3:
        st.metric("Players per Game", metadata["n_players_per_game"])

    # Display various sections
    display_elo_ratings(final_results)
    display_win_rates(final_results["contests"])
    df_games = display_game_results(final_results["contests"], tournament_dir)

    # Display game log if a game is selected

    selected_rows = st.session_state.get("game_table", {}).get("selected_rows", [])

    if selected_rows:
        selected_game = df_games.iloc[selected_rows[0]]

        st.divider()
        display_game_log(tournament_dir, selected_game)


if __name__ == "__main__":
    main()
