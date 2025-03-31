from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, DataTable
from textual.containers import Container, Vertical, Grid
from textual.binding import Binding
from typing import Dict, List, Tuple, Any, TypeVar, Optional

from tournament import Tournament, GameStats

# Define types for DataTable generics
T = TypeVar("T")


class RoundStatus(Static):
    """A widget to display the current round status"""

    current_round = reactive(0)
    total_rounds = reactive(0)

    def on_mount(self) -> None:
        """Called when widget is added to the app"""
        self.update_content()

    def watch_current_round(self, current_round: int) -> None:
        """Called when current_round changes"""
        self.update_content()

    def watch_total_rounds(self, total_rounds: int) -> None:
        """Called when total_rounds changes"""
        self.update_content()

    def update_content(self) -> None:
        """Update the content of the widget"""
        self.update(f"Round {self.current_round} of {self.total_rounds}")
        self.styles.background = "#2d2d2d"
        self.styles.color = "#ffffff"
        self.styles.padding = (1, 2)
        self.styles.border = ("heavy", "#666666")


class ELORankingsTable(DataTable[str]):
    """A widget to display ELO rankings"""

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize with columns set up"""
        super().__init__(*args, **kwargs)
        self.add_column("Rank")
        self.add_column("Model")
        self.add_column("ELO Rating")
        self.add_column("Change")  # Add a column for the change indicator

    def on_mount(self) -> None:
        """Set up the table when the widget is mounted"""
        self.cursor_type = "none"  # Hide cursor
        self.styles.border = ("heavy", "#666666")

    def update_rankings(
        self,
        rankings: List[Tuple[str, float]],
        previous_rankings: Optional[Dict[str, float]] = None,
    ) -> None:
        """Update the table with new rankings and show changes."""
        self.clear()

        for i, (model_name, rating) in enumerate(rankings):
            change_indicator = ""
            rating_style = ""
            if previous_rankings and model_name in previous_rankings:
                prev_rating = previous_rankings[model_name]
                if rating > prev_rating:
                    change_indicator = "[green]▲[/]"
                    rating_style = "[green]"
                elif rating < prev_rating:
                    change_indicator = "[red]▼[/]"
                    rating_style = "[red]"
                else:
                    change_indicator = "-"

            # Truncate model name if it's too long
            display_name = model_name
            if len(model_name) > 25:
                display_name = model_name[:22] + "..."

            # Construct the styled rating string conditionally
            styled_rating = f"{rating:.1f}"
            if rating_style:  # Only add style tags if there was a change
                styled_rating = f"{rating_style}{styled_rating}[/]"

            # Add the row with styled rating and change indicator
            self.add_row(
                str(i + 1),
                display_name,
                styled_rating,  # Use the corrected string
                change_indicator,
            )


class GameWidget(Static):
    """A widget to display an individual game"""

    DEFAULT_BORDER_STYLE = ("heavy", "#666666")
    HIGHLIGHT_BORDER_STYLE = ("heavy", "yellow")

    game_id = reactive("")
    mafia_model = reactive("")
    town_model = reactive("")
    phase = reactive("")
    day_count = reactive(0)
    mafia_alive = reactive(0)
    townspeople_alive = reactive(0)

    def on_mount(self) -> None:
        """Called when widget is added to the app"""
        self.update_content()
        self.styles.padding = (1, 2)
        self.styles.border = self.DEFAULT_BORDER_STYLE

    def update_all(
        self,
        game_id: str,
        mafia_model: str,
        town_model: str,
        phase: str,
        day_count: int,
        mafia_alive: int,
        townspeople_alive: int,
    ) -> None:
        """Update all reactive properties at once"""
        # Update reactive properties, which will trigger watchers including watch_phase
        self.game_id = game_id
        self.mafia_model = mafia_model
        self.town_model = town_model
        self.phase = phase
        self.day_count = day_count
        self.mafia_alive = mafia_alive
        self.townspeople_alive = townspeople_alive

    def watch_game_id(self, game_id: str) -> None:
        self.update_content()

    def watch_mafia_model(self, mafia_model: str) -> None:
        self.update_content()

    def watch_town_model(self, town_model: str) -> None:
        self.update_content()

    def watch_phase(self, old_phase: str, new_phase: str) -> None:
        """Flash the border when the phase changes."""
        self.update_content()
        # Don't flash on initial mount (old_phase might be default)
        if old_phase != new_phase:
            self._flash_border()

    def _flash_border(self) -> None:
        """Highlight the border briefly."""
        self.styles.border = self.HIGHLIGHT_BORDER_STYLE
        self.set_timer(0.5, self._reset_border)

    def _reset_border(self) -> None:
        """Reset the border to the default style."""
        self.styles.border = self.DEFAULT_BORDER_STYLE

    def watch_day_count(self, day_count: int) -> None:
        self.update_content()

    def watch_mafia_alive(self, mafia_alive: int) -> None:
        self.update_content()

    def watch_townspeople_alive(self, townspeople_alive: int) -> None:
        self.update_content()

    def update_content(self) -> None:
        """Update the content of the widget"""
        # Choose color based on phase
        phase_color = "#3498db"  # Default blue
        if self.phase == "night":
            phase_color = "#9b59b6"  # Purple for night
        elif self.phase == "day":
            phase_color = "#f1c40f"  # Yellow for day

        # Truncate model names if needed
        mafia_display = self.mafia_model
        town_display = self.town_model
        if len(mafia_display) > 20:
            mafia_display = mafia_display[:17] + "..."
        if len(town_display) > 20:
            town_display = town_display[:17] + "..."

        content = (
            f"[b]{self.game_id}[/b]\n"
            f"[red]Mafia[/red]: {mafia_display}\n"
            f"[green]Town[/green]: {town_display}\n"
            f"Phase: [{phase_color}]{self.phase.capitalize()}[/] (Day {self.day_count})\n"
            f"Living: [red]{self.mafia_alive}[/red] Mafia, [green]{self.townspeople_alive}[/green] Town"
        )
        self.update(content)


class ActiveGamesContainer(Vertical):
    """Container for all active games"""

    def on_mount(self) -> None:
        """Called when widget is added to the app"""
        self.styles.height = "100%"
        # Set border title directly
        self.styles.border = ("heavy", "#666666")
        self.border_title = "Active Games"


class TournamentTUI(App[None]):
    """A Textual app to visualize the tournament"""

    # Add the dark reactive attribute as a class variable
    dark = reactive(False)

    CSS = """
    Screen {
        background: #1e1e1e;
    }
    
    RoundStatus {
        dock: top;
        height: 3;
        margin: 1 1;
        text-align: center;
        text-style: bold;
    }
    
    #grid {
        grid-size: 2;
        grid-gutter: 1;
        margin: 1 1;
        height: 100%;
    }
    
    ELORankingsTable {
        width: 100%;
        height: 100%;
    }
    
    ActiveGamesContainer {
        overflow-y: auto;
    }
    
    GameWidget {
        margin: 1 0;
        height: auto;
    }
    
    #elo-container {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "toggle_dark", "Toggle Dark Mode"),
    ]

    # Keep track of game widgets
    active_games: Dict[str, GameWidget] = {}
    # Store previous ratings to calculate changes
    previous_ratings: Dict[str, float] = {}

    def __init__(self, tournament: Tournament) -> None:
        """Initialize the app with a tournament"""
        super().__init__()
        self.tournament = tournament
        # Store initial ratings as previous
        self.previous_ratings = self.tournament.get_final_ratings().copy()

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield Header(show_clock=True)

        # Tournament status
        round_status = RoundStatus()
        round_status.total_rounds = self.tournament.num_rounds
        yield round_status

        # Main grid with rankings and games
        with Grid(id="grid"):
            # Left column: ELO rankings
            with Container(id="elo-container") as elo_container:
                # Set the border title on the container directly
                elo_container.border_title = "ELO Rankings"

                # Create the table but don't populate it yet
                yield ELORankingsTable()

            # Right column: Active games
            yield ActiveGamesContainer()

        yield Footer()

    def on_mount(self) -> None:
        """Set up tasks when the app is mounted"""
        # Initialize the ELO rankings table now that it's mounted
        elo_table = self.query_one(ELORankingsTable)
        # Use the stored initial ratings for the first display
        initial_rankings = sorted(
            self.previous_ratings.items(), key=lambda item: item[1], reverse=True
        )
        elo_table.update_rankings(
            initial_rankings, None
        )  # No previous ratings for initial display

        # Run the tournament in the background
        self.run_worker(self._run_tournament())

    async def _run_tournament(self) -> None:
        """Run the tournament and update the UI as it progresses"""
        # Inject hooks into tournament to update the UI
        self._inject_tournament_hooks()

        # Run the tournament
        await self.tournament.run_tournament()

        # Tournament is complete - show final results
        self.query_one(RoundStatus).update("Tournament Complete!")

    def _inject_tournament_hooks(self) -> None:
        """Inject hooks into tournament methods to update the UI"""
        # Store original methods
        original_run_round = self.tournament.run_round
        original_update_ratings = getattr(self.tournament, "_update_ratings")

        # Patch tournament methods
        async def patched_run_round(*args: Any, **kwargs: Any) -> List[GameStats]:
            """Patched run_round to update UI before and after running the round"""
            # Update round number
            self.query_one(RoundStatus).current_round = (
                self.tournament.current_round + 1
            )

            # Store current ratings *before* the round runs to compare later
            self.previous_ratings = self.tournament.get_final_ratings().copy()

            # Run the original method
            result = await original_run_round(*args, **kwargs)

            # Clear active games (round finished)
            await self._clear_active_games()

            return result

        def patched_update_ratings(*args: Any, **kwargs: Any) -> None:
            """Patched _update_ratings to update ELO rankings in UI"""
            # Run the original method to update tournament internal ratings
            original_update_ratings(*args, **kwargs)

            # Now get the new sorted ratings
            get_sorted_ratings = getattr(self.tournament, "_get_model_ratings_sorted")
            current_rankings = get_sorted_ratings()

            # Update the UI table, passing the previous ratings for comparison
            self.query_one(ELORankingsTable).update_rankings(
                current_rankings, self.previous_ratings
            )

        # Apply patches - we need to use setattr for protected methods
        self.tournament.run_round = patched_run_round
        setattr(self.tournament, "_update_ratings", patched_update_ratings)

        # Also patch Contest.run to track games
        from contest import Contest

        original_contest_run = Contest.run

        # Create a wrapper that preserves type compatibility
        async def contest_run_wrapper(
            self_contest: Any, *args: Any, **kwargs: Any
        ) -> Any:
            """Wrapper that preserves the original method's signature but adds our hooks"""
            # Save original Game methods
            from game import Game

            original_game_run = Game.run
            original_run_phase = Game.run_phase

            # Create game method wrappers that preserve signatures
            async def game_run_hook(self_game: Any, *args: Any, **kwargs: Any) -> Any:
                """Hook into Game.run while preserving its signature"""
                game_id = f"{self_contest.name}/Game {self_game.game_id}"

                # Update UI with game start
                await self._update_game_widget(
                    game_id,
                    self_game.model_mafia,
                    self_game.model_townsperson,
                    str(self_game.phase),
                    self_game.day_count,
                    self_game.n_mafia_alive,
                    self_game.n_townsperson_alive,
                )

                # Run original game
                result = await original_game_run(self_game, *args, **kwargs)

                # Update UI with game end
                await self._remove_game_widget(game_id)

                return result

            async def phase_run_hook(self_game: Any, *args: Any, **kwargs: Any) -> Any:
                """Hook into Game.run_phase while preserving its signature"""
                game_id = f"{self_contest.name}/Game {self_game.game_id}"

                # Update UI with phase change
                await self._update_game_widget(
                    game_id,
                    self_game.model_mafia,
                    self_game.model_townsperson,
                    str(self_game.phase),
                    self_game.day_count,
                    self_game.n_mafia_alive,
                    self_game.n_townsperson_alive,
                )

                # Run original phase logic
                return await original_run_phase(self_game, *args, **kwargs)

            # Apply our hooks (with monkey patching)
            Game.run = game_run_hook  # type: ignore
            Game.run_phase = phase_run_hook  # type: ignore

            try:
                # Run the original contest method
                return await original_contest_run(self_contest, *args, **kwargs)
            finally:
                # Restore original methods
                Game.run = original_game_run
                Game.run_phase = original_run_phase

        # Apply the wrapper to Contest.run
        Contest.run = contest_run_wrapper  # type: ignore

    async def _update_game_widget(
        self,
        game_id: str,
        mafia_model: str,
        town_model: str,
        phase: str,
        day_count: int,
        mafia_alive: int,
        townspeople_alive: int,
    ) -> None:
        """Create or update a game widget"""
        # Get games container
        games_container = self.query_one(ActiveGamesContainer)

        # Create a new widget if it doesn't exist
        if game_id not in self.active_games:
            game_widget = GameWidget()
            games_container.mount(game_widget)
            self.active_games[game_id] = game_widget

        # Update the widget
        self.active_games[game_id].update_all(
            game_id,
            mafia_model,
            town_model,
            phase,
            day_count,
            mafia_alive,
            townspeople_alive,
        )

    async def _remove_game_widget(self, game_id: str) -> None:
        """Remove a game widget"""
        if game_id in self.active_games:
            self.active_games[game_id].remove()
            del self.active_games[game_id]

    async def _clear_active_games(self) -> None:
        """Clear all active games widgets"""
        for game_id in list(self.active_games.keys()):
            await self._remove_game_widget(game_id)

    def action_toggle_dark(self) -> None:
        """Toggle dark mode"""
        self.dark = not self.dark

    async def action_quit(self) -> None:
        """Quit the application"""
        self.exit()
