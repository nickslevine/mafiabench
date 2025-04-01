from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, DataTable, RichLog
from textual.containers import Container, Vertical, Grid
from textual.binding import Binding
from rich.text import Text
from typing import Dict, List, Tuple, Any, TypeVar, Optional
from collections import deque

from tournament import Tournament, GameStats
# Import ProgressCallback from game, not directly
# from game import ProgressCallback

# Define types for DataTable generics
T = TypeVar("T")


class TournamentStatus(Static):
    """A widget to display tournament round and game status"""

    current_round = reactive(0)
    total_rounds = reactive(0)
    total_games_completed = reactive(0)  # New reactive property

    def on_mount(self) -> None:
        """Called when widget is added to the app"""
        self.update_content()

    def watch_current_round(self, current_round: int) -> None:
        """Called when current_round changes"""
        self.update_content()

    def watch_total_rounds(self, total_rounds: int) -> None:
        """Called when total_rounds changes"""
        self.update_content()

    def watch_total_games_completed(self, total_games: int) -> None:
        """Called when total_games_completed changes"""
        self.update_content()

    def update_content(self) -> None:
        """Update the content of the widget"""
        self.update(
            f"Round {self.current_round} of {self.total_rounds} | Games Completed: {self.total_games_completed}"
        )
        # Remove style settings, now handled by CSS
        # self.styles.background = "#2d2d2d"
        # self.styles.color = "#ffffff"
        # self.styles.padding = (1, 2)
        # self.styles.border = ("heavy", "#666666")


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
    progress_text = reactive("")  # Add progress text property
    kb_update_text = reactive("")  # Add knowledge base update text property

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
        # Keep existing progress text and kb_update_text until explicitly cleared by callback

    def watch_game_id(self, game_id: str) -> None:
        self.update_content()

    def watch_mafia_model(self, mafia_model: str) -> None:
        self.update_content()

    def watch_town_model(self, town_model: str) -> None:
        self.update_content()

    def watch_phase(self, old_phase: str, new_phase: str) -> None:
        """Flash the border and clear progress when the phase changes."""
        self.update_content()
        # Don't flash on initial mount (old_phase might be default)
        if old_phase != new_phase:
            # Clear progress text when phase truly changes
            self.progress_text = ""
            self._flash_border()

    def watch_progress_text(self, progress_text: str) -> None:
        """Update content when progress text changes"""
        self.update_content()

    def watch_kb_update_text(self, kb_update_text: str) -> None:
        """Update content when knowledge base update text changes"""
        self.update_content()

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

        # Add progress text and KB update text if they exist
        status_line = ""
        if self.progress_text:
            status_line += f"[i]{self.progress_text}[/i]"
        if self.kb_update_text:
            if status_line:
                status_line += " | "
            status_line += f"[cyan]{self.kb_update_text}[/cyan]"
        status_display = f" ({status_line})" if status_line else ""

        content = (
            f"[b]{self.game_id}[/b]\n"
            f"[red]Mafia[/red]: {mafia_display}\n"
            f"[green]Town[/green]: {town_display}\n"
            f"Phase: [{phase_color}]{self.phase.capitalize()}[/] (Day {self.day_count}){status_display}\n"
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


# --- Add EventLogWidget Definition ---
class EventLogWidget(RichLog):
    """A widget to display a continuous stream of game events."""

    def on_mount(self) -> None:
        """Set up the log widget."""
        self.border_title = "Event Log"
        self.styles.border = ("heavy", "#666666")


# --- End EventLogWidget Definition ---


class TournamentTUI(App[None]):
    """A Textual app to visualize the tournament"""

    # Add the dark reactive attribute as a class variable
    dark = reactive(False)

    CSS = """
    Screen {
        background: #1e1e1e;
        layout: vertical;
    }

    TournamentStatus {
        height: 3;
        padding: 0 2;
        text-align: center;
        text-style: bold;
        border: thick #666666;
        background: #2d2d2d;
        color: white;
    }

    #grid {
        grid-size: 2;
        grid-gutter: 1;
        margin: 1 1;
        height: 90%;
    }

    /* NEW: Container for the left column widgets */
    #left-column {
        display: block; /* Use block layout for vertical stacking */
        height: 100%;
        width: 100%;
    }

    /* Adjust ELO container */
    #elo-container {
        height: 60%; /* Allocate top 60% */
        width: 100%;
        border: heavy #666666;
        padding: 0 1;
    }

    ELORankingsTable {
        /* Table fills its container */
        width: 100%;
        height: 100%;
    }

    /* NEW: Style the Event Log */
    EventLogWidget {
        height: 40%; /* Allocate bottom 40% */
        width: 100%;
        margin-top: 1; /* Add margin between table and log */
    }

    ActiveGamesContainer {
        overflow-y: auto;
        height: 100%; /* Ensure it fills the grid cell height */
    }

    GameWidget {
        margin: 1 0;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "toggle_dark", "Toggle Dark Mode"),
    ]

    # Map internal game_id (from Game class) to the TUI's game widget ID
    game_widget_map: Dict[str, str] = {}
    # Keep track of game widgets using TUI ID
    active_games: Dict[str, GameWidget] = {}
    # Store previous ratings to calculate changes
    previous_ratings: Dict[str, float] = {}
    # Track total games completed
    total_games_completed_count: int = 0
    # --- Add deque for event log messages ---
    event_log_messages: deque[Text]
    # -------------------------------------

    def __init__(self, tournament: Tournament, event_log_max_lines: int = 100) -> None:
        """Initialize the app with a tournament"""
        super().__init__()
        self.tournament = tournament
        self.previous_ratings = self.tournament.get_final_ratings().copy()
        # --- Initialize the deque ---
        self.event_log_messages = deque(maxlen=event_log_max_lines)
        # ---------------------------

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield Header(show_clock=True)

        tournament_status = TournamentStatus()
        tournament_status.total_rounds = self.tournament.num_rounds
        yield tournament_status

        # Main grid
        with Grid(id="grid"):
            # --- Left Column (Vertical Stack) ---
            with Vertical(id="left-column"):
                # Top: ELO rankings container
                with Container(id="elo-container") as elo_container:
                    elo_container.border_title = "ELO Rankings"
                    yield ELORankingsTable()

                # Bottom: Event Log
                yield EventLogWidget(wrap=True, highlight=True)

            # --- Right Column: Active games ---
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
        # Keep final game count visible
        final_text = (
            f"Tournament Complete! | Total Games: {self.total_games_completed_count}"
        )
        self.query_one(TournamentStatus).update(final_text)

    # --- Progress Callback Handling ---
    def update_game_progress(self, **kwargs: Any) -> None:
        """Callback function passed to Game instances. Receives kwargs."""
        # Schedule the update on the main thread, passing the whole dict
        self.call_later(self._do_update_game_progress, kwargs)

    def _do_update_game_progress(self, progress_data: Dict[str, Any]) -> None:
        """Safely updates the GameWidget from the main thread using received data.
        Also handles widget creation on first full update and removal on game over.
        """
        internal_game_id = progress_data.get("internal_game_id")
        if not internal_game_id:
            self.log.error("Progress update missing internal_game_id")
            return

        # --- Check for Game Over ---
        phase_name = progress_data.get("phase_name")
        if phase_name == "Game Over":
            self.log.info(
                f"Game Over detected for internal_game_id: {internal_game_id}"
            )

            self._increment_total_games()
            tui_game_id = self.game_widget_map.get(internal_game_id)

            if tui_game_id:
                self.log.info(
                    f"Found TUI ID {tui_game_id} for internal ID {internal_game_id}"
                )
                widget_to_remove = self.active_games.get(tui_game_id)

                if widget_to_remove:
                    self.log.info(
                        f"Found widget {tui_game_id} in active_games. Attempting removal."
                    )
                    try:
                        self.log.info(f"Calling remove() for widget {tui_game_id}")
                        widget_to_remove.remove()  # Remove widget from layout
                        self.log.info(
                            f"Successfully called remove() for widget {tui_game_id}"
                        )
                    except Exception as e:
                        self.log.error(
                            f"Error calling remove() for widget {tui_game_id}: {e}"
                        )
                else:
                    self.log.warning(
                        f"Widget {tui_game_id} not found in active_games dictionary."
                    )

                # Clean up tracking dictionaries regardless of widget removal success
                self.log.info(
                    f"Attempting cleanup for {tui_game_id} / {internal_game_id}"
                )
                if tui_game_id in self.active_games:
                    self.log.info(f"Deleting {tui_game_id} from active_games")
                    del self.active_games[tui_game_id]
                if internal_game_id in self.game_widget_map:
                    self.log.info(f"Deleting {internal_game_id} from game_widget_map")
                    del self.game_widget_map[internal_game_id]
                self.log.info(
                    f"Cleanup finished for {tui_game_id} / {internal_game_id}"
                )

            else:
                # Log if internal ID wasn't found in the map at all
                self.log.warning(
                    f"Received 'Game Over' but internal_game_id {internal_game_id} not found in game_widget_map."
                )

            # Return AFTER logging is complete
            return  # Don't process further updates for a completed game
        # --- End Game Over Check ---

        contest_name = progress_data.get("contest_name", "Unknown")
        game_index = progress_data.get("game_index", -1)
        tui_game_id = f"{contest_name}/Game {game_index}"
        progress_text = progress_data.get("text")
        full_data = progress_data.get("full_data")

        # Handle KB update status - now we'll use the text directly
        if progress_data.get("updating_kb"):
            # Use the provided text directly
            progress_text = progress_data.get("text", "")

        widget = self.active_games.get(tui_game_id)

        # If widget doesn't exist AND we have full data, create it
        if widget is None and full_data:
            self.log.info(f"Creating widget {tui_game_id} from progress callback")
            widget = GameWidget()
            try:
                # Mount first
                self.query_one(ActiveGamesContainer).mount(widget)
                # Then add to dicts
                self.active_games[tui_game_id] = widget
                self.game_widget_map[internal_game_id] = tui_game_id
                # Apply the full data immediately
                widget.update_all(
                    tui_game_id,
                    full_data.get("mafia_model", "?"),
                    full_data.get("town_model", "?"),
                    full_data.get("phase", "?"),
                    full_data.get("day_count", -1),
                    full_data.get("mafia_alive", -1),
                    full_data.get("townspeople_alive", -1),
                )
                # Also apply the current progress text if any
                widget.progress_text = (
                    progress_text if progress_text is not None else ""
                )
                widget.kb_update_text = ""  # Always start with empty kb_update_text

            except Exception as e:
                self.log.error(
                    f"Failed to create/update widget {tui_game_id} from callback: {e}"
                )
                # Clean up if creation failed partially
                if tui_game_id in self.active_games:
                    del self.active_games[tui_game_id]
                if internal_game_id in self.game_widget_map:
                    del self.game_widget_map[internal_game_id]
                widget = None  # Ensure widget is None if failed

        # If widget exists (or was just created), update progress text and potentially full data
        if widget:
            # Update full data if provided
            if full_data:
                widget.update_all(
                    tui_game_id,
                    full_data.get("mafia_model", widget.mafia_model),
                    full_data.get("town_model", widget.town_model),
                    full_data.get("phase", widget.phase),
                    full_data.get("day_count", widget.day_count),
                    full_data.get("mafia_alive", widget.mafia_alive),
                    full_data.get("townspeople_alive", widget.townspeople_alive),
                )
            # Always update progress text
            if progress_text is not None:
                widget.progress_text = progress_text
            # Clear kb_update_text if requested
            if progress_data.get("clear_kb_status"):
                widget.kb_update_text = ""
        else:
            # Widget doesn't exist and we didn't have full data to create it
            if phase_name != "Game Over":  # Only log warning if not game over
                self.log.warning(
                    f"Widget {tui_game_id} not found and no full data in callback for {internal_game_id}. Progress: {progress_text}"
                )

    # ----------------------------------

    # --- Game Completion Tracking ---
    def _increment_total_games(self) -> None:
        """Increment the total games counter and update the status widget."""
        self.total_games_completed_count += 1

        def update_status():
            try:
                status_widget = self.query_one(TournamentStatus)
                status_widget.total_games_completed = self.total_games_completed_count
            except Exception as e:
                self.log.error(f"Failed to update TournamentStatus: {e}")

        self.call_later(update_status)

    # --------------------------------

    # --- Add Event Handling Method ---
    def _handle_game_event(self, event_data: Dict[str, Any]) -> None:
        """Receives game events and writes them to the EventLogWidget."""
        # Schedule the update on the main thread
        self.call_later(self._do_handle_game_event, event_data)

    def _do_handle_game_event(self, event_data: Dict[str, Any]) -> None:
        """Safely updates the event log from the main thread, keeping only maxlen lines."""
        try:
            # --- Build the Text object for the new message (as before) ---
            game_str = (
                f"[{event_data.get('contest_name')}/G{event_data.get('game_index')}]"
            )
            event_type = event_data.get("event_type", "UNKNOWN")
            data = event_data.get("data", {})
            message = Text()
            message.append(game_str, style="dim")
            message.append(" ")
            # (Keep the existing logic for formatting based on event_type)
            if event_type == "SPEECH":
                player = data.get("player", "?")
                snippet = data.get("text", "")
                if len(snippet) > 70:
                    snippet = snippet[:67] + "..."
                message.append(player, style="bold")
                message.append(" said: '")
                message.append(snippet, style="italic")
                message.append("'")
            elif event_type == "VOTE_CAST":
                voter = data.get("voter", "?")
                voted_for = data.get("voted_for", "?")
                message.append(f"{voter} voted for ")
                message.append(voted_for, style="bold")
            elif event_type == "VOTE_SUMMARY":
                eliminated = data.get("eliminated", "?")
                message.append("Eliminated by day vote: ", style="red")
                message.append(eliminated, style="bold")
            elif event_type == "MAFIA_KILL":
                eliminated = data.get("eliminated", "?")
                message.append("Eliminated by mafia: ", style="red")
                message.append(eliminated, style="bold")
            else:
                message.append(f"{event_type}: {data}")
            # --- End building Text object ---

            # --- Update deque and redraw log ---
            self.event_log_messages.append(message)

            log_widget = self.query_one(EventLogWidget)
            log_widget.clear()
            for msg in self.event_log_messages:
                log_widget.write(msg)
            # --------------------------------

        except Exception as e:
            self.log.error(
                f"Failed to write event to EventLogWidget: {e} Data: {event_data}"
            )

    # --- End Event Handling Method ---

    def _inject_tournament_hooks(self) -> None:
        """Inject hooks into tournament methods to update the UI"""
        # Store original methods
        original_run_round = self.tournament.run_round
        original_update_ratings = getattr(self.tournament, "_update_ratings")

        # Patch tournament methods
        async def patched_run_round(*args: Any, **kwargs: Any) -> List[GameStats]:
            self.query_one(TournamentStatus).current_round = (
                self.tournament.current_round + 1
            )
            self.previous_ratings = self.tournament.get_final_ratings().copy()
            result = await original_run_round(*args, **kwargs)
            await self._clear_active_games()
            return result

        def patched_update_ratings(*args: Any, **kwargs: Any) -> None:
            original_update_ratings(*args, **kwargs)
            get_sorted_ratings = getattr(self.tournament, "_get_model_ratings_sorted")
            current_rankings = get_sorted_ratings()
            self.query_one(ELORankingsTable).update_rankings(
                current_rankings, self.previous_ratings
            )

        self.tournament.run_round = patched_run_round
        setattr(self.tournament, "_update_ratings", patched_update_ratings)

        # Patch Contest init to pass the callbacks
        from contest import Contest

        original_contest_init = Contest.__init__

        def patched_contest_init(contest_instance: Contest, *args: Any, **kwargs: Any):
            # Pass BOTH callbacks
            kwargs["progress_callback"] = self.update_game_progress
            kwargs["event_callback"] = self._handle_game_event  # Pass new event handler
            original_contest_init(contest_instance, *args, **kwargs)

        Contest.__init__ = patched_contest_init  # type: ignore

    async def _clear_active_games(self) -> None:
        """Clear all active games widgets AND the map."""

        def clear():
            active_container = self.query_one(ActiveGamesContainer)
            # Remove widgets efficiently
            active_container.remove_children()
            # Clear dictionaries
            self.active_games.clear()
            self.game_widget_map.clear()

        self.call_later(clear)

    def action_toggle_dark(self) -> None:
        """Toggle dark mode"""
        self.dark = not self.dark

    async def action_quit(self) -> None:
        """Quit the application"""
        # TODO: Consider restoring original patched methods here if needed
        self.exit()
