import json
from typing import Dict, Any
import pandas as pd
import matplotlib.pyplot as plt


# Load the tournament results from the JSON file
def load_tournament_results(filename: str) -> Dict[str, Any]:
    """
    Load tournament results from a JSON file.

    Args:
        filename (str): Path to the JSON file containing tournament results

    Returns:
        Dict[str, Any]: Dictionary containing the tournament results data
    """
    with open(filename, "r") as f:
        data = json.load(f)
    return data


class Analysis:
    def __init__(self, tournament_results: Dict[str, Any]):
        self.data = tournament_results

        # Tournament metadata
        self.metadata = self.data.get("tournament_metadata", {})
        # Final ELO ratings
        self.final_elo_ratings = self.data.get("final_elo_ratings", {})
        # ELO rating history
        self.elo_history = self.data.get("elo_rating_history_by_round", {})
        # Contest data
        self.contests = self.data.get("contests", [])

    @classmethod
    def from_path(cls, file_path: str) -> "Analysis":
        """
        Create an Analysis object from a tournament results JSON file.

        Args:
            file_path (str): Path to the tournament results JSON file

        Returns:
            Analysis: An Analysis object initialized with the tournament data
        """
        tournament_data = load_tournament_results(file_path)
        return cls(tournament_data)

    @property
    def elo(self) -> pd.DataFrame:
        elo_df = pd.DataFrame(
            {
                "Model": list(self.final_elo_ratings.keys()),
                "Final ELO Rating": list(self.final_elo_ratings.values()),
            }
        )

        # Sort the DataFrame by ELO rating in descending order
        elo_df = elo_df.sort_values(by="Final ELO Rating", ascending=False)  # type: ignore

        # Reset the index for cleaner display
        elo_df = elo_df.reset_index(drop=True).round(0)  # type: ignore
        return elo_df

    @property
    def model_stats(self) -> pd.DataFrame:
        stats = {
            model: {"time": 0, "messages": 0, "invalid_votes": 0}
            for model in self.final_elo_ratings.keys()
        }

        # Loop through each contest in the tournament results
        for contest in self.contests:
            # Loop through each game in the contest
            for game in contest.get("games", []):
                # Extract the models playing as mafia and townsperson
                model_mafia = game["model_mafia"]
                model_townsperson = game["model_townsperson"]

                # Update statistics for the mafia model
                stats[model_mafia]["time"] += game.get("mafia_total_time", 0)
                stats[model_mafia]["messages"] += game.get("mafia_total_messages", 0)
                stats[model_mafia]["invalid_votes"] += game.get(
                    "mafia_invalid_votes", 0
                )
                # stats[model_mafia]["timeout_count"] += game.get(
                #     "mafia_timeout_count", 0
                # )

                # Update statistics for the townsperson model
                stats[model_townsperson]["time"] += game.get(
                    "townsperson_total_time", 0
                )
                stats[model_townsperson]["messages"] += game.get(
                    "townsperson_total_messages", 0
                )
                stats[model_townsperson]["invalid_votes"] += game.get(
                    "townsperson_invalid_votes", 0
                )
                # stats[model_townsperson]["timeout_count"] += game.get(
                #     "townsperson_timeout_count", 0
                # )

        stats = pd.DataFrame(stats).transpose()  # type: ignore
        stats["latency"] = stats["time"] / stats["messages"]  # type: ignore
        stats = stats.round(1)  # type: ignore
        return stats

    @property
    def elo_history_df(self) -> pd.DataFrame:
        elos = pd.DataFrame(self.elo_history).iloc[1:]
        rankings = elos.rank(axis=1, ascending=False)
        return rankings

    def plot_elo_history(self):
        rankings = self.elo_history_df
        ax = rankings.plot(marker="o")
        plt.grid()
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        ax.invert_yaxis()
        plt.title("ELO Ranking By Tournament Round")
