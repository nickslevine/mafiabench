from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, DataTable, RichLog
from textual.containers import Container, Vertical, Grid
from textual.binding import Binding
from rich.text import Text
from typing import Dict, List, Tuple, Any, TypeVar, Optional, Literal
from collections import deque

from tournament import Tournament, GameStats
# Import ProgressCallback from game, not directly
# from game import ProgressCallback

# Define types for DataTable generics
T = TypeVar("T")

# Define a type for our border styles
BorderStyle = Tuple[Literal["heavy"], str]


class TournamentStatus(Static):
    """A widget to display tournament round and game status"""

    current_round = reactive(0)
    total_rounds = reactive(0)
    total_games_completed = reactive(0)  # Total games completed across all rounds
    round_games_completed = reactive(0)  # Games completed in current round
    round_total_games = reactive(0)  # Total games expected in current round

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

    def watch_round_games_completed(self, games: int) -> None:
        """Called when round_games_completed changes"""
        self.update_content()

    def watch_round_total_games(self, total: int) -> None:
        """Called when round_total_games changes"""
        self.update_content()

    def update_content(self) -> None:
        """Update the content of the widget"""
        # Calculate progress percentage for the progress bar
        progress_percent = (
            (self.round_games_completed / self.round_total_games * 100)
            if self.round_total_games > 0
            else 0
        )

        # Create a progress bar using block characters with proper markup
        filled_blocks = int(progress_percent / 5)  # 20 blocks total = 5% per block
        empty_blocks = 20 - filled_blocks

        # Create the progress bar segments with proper escaping
        filled_segment = f"[blue]{'█' * filled_blocks}[/]" if filled_blocks > 0 else ""
        empty_segment = f"[dim]{'█' * empty_blocks}[/]" if empty_blocks > 0 else ""

        self.update(
            f"Round {self.current_round} of {self.total_rounds} | Games in Round: {self.round_games_completed}/{self.round_total_games}\n"
            f"Progress: {filled_segment}{empty_segment} {progress_percent:.1f}%"
        )


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
            if len(model_name) > 50:
                display_name = model_name[:47] + "..."

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

    DEFAULT_BORDER_STYLE: BorderStyle = ("heavy", "#666666")
    HIGHLIGHT_BORDER_STYLE: BorderStyle = ("heavy", "yellow")
    MAFIA_WIN_BORDER_STYLE: BorderStyle = ("heavy", "red")
    TOWN_WIN_BORDER_STYLE: BorderStyle = ("heavy", "green")

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

    def set_border_style(self, style: BorderStyle) -> None:
        """Set the border style directly"""
        self.styles.border = style
        self.refresh()

    def _flash_border(self) -> None:
        """Highlight the border briefly."""
        self.set_border_style(self.HIGHLIGHT_BORDER_STYLE)
        self.set_timer(0.5, self._reset_border)

    def _reset_border(self) -> None:
        """Reset the border to the default style."""
        self.set_border_style(self.DEFAULT_BORDER_STYLE)

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
        if len(mafia_display) > 50:
            mafia_display = mafia_display[:47] + "..."
        if len(town_display) > 50:
            town_display = town_display[:47] + "..."

        # Format the status line without duplicating the progress text
        status_line = ""
        if self.kb_update_text:
            status_line = f"[cyan]{self.kb_update_text}[/cyan]"

        content = (
            f"[b]{self.game_id}[/b]\n"
            f"[red]Mafia[/red]: {mafia_display}\n"
            f"[green]Town[/green]: {town_display}\n"
            f"Phase: [{phase_color}]{self.phase.capitalize()}[/] (Day {self.day_count}) | [i]{self.progress_text}[/i]\n"
            f"Living: [red]{self.mafia_alive}[/red] Mafia, [green]{self.townspeople_alive}[/green] Town"
        )

        # Add KB update text on a new line if it exists
        if status_line:
            content += f"\n{status_line}"

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
        height: 4;  /* Increased to accommodate two lines */
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
    # Track round-specific games
    round_games_completed_count: int = 0
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
        # Calculate total games expected per round
        games_per_contest = self.tournament.games_per_contest
        num_pairings = (
            len(self.tournament.model_names) // 2
        )  # Each round pairs all models
        total_games_per_round = games_per_contest * num_pairings
        tournament_status.round_total_games = total_games_per_round
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
        """Safely updates the GameWidget from the main thread using received data."""

        # self.log.info(f"Received progress data: {progress_data}")
        internal_game_id = progress_data.get("internal_game_id")
        if not internal_game_id:
            self.log.error("Progress update missing internal_game_id")
            return

        # Get contest name from either progress data or full data
        contest_name = progress_data.get("contest_name")
        if not contest_name:
            raise Exception(f"Progress update missing contest_name: {progress_data}")

        # Create unique internal ID for game over check
        unique_internal_id = f"{contest_name}_game_{internal_game_id}"
        # self.log.info(f"Using unique internal ID: {unique_internal_id}")

        # Handle game over state if present
        if progress_data.get("phase_name") == "Game Over":
            self._handle_game_over(unique_internal_id, progress_data)
            return

        # Get or create widget for the game
        widget = self._get_or_create_game_widget(progress_data)
        if not widget:
            return

        # Update the widget with latest data
        self._update_widget_state(widget, progress_data)

    def _handle_game_over(
        self, unique_internal_id: str, progress_data: Dict[str, Any]
    ) -> None:
        """Handle game completion by updating its status."""
        self.log.info(
            f"Game Over detected for unique_internal_id: {unique_internal_id}"
        )
        self._increment_total_games()

        tui_game_id = self.game_widget_map.get(unique_internal_id)
        if not tui_game_id:
            raise Exception(
                f"Received 'Game Over' but unique_internal_id {unique_internal_id} not found in game_widget_map."
            )

        widget = self.active_games.get(tui_game_id)
        if widget:
            self.log.info(
                f"Updating widget {tui_game_id} with game over data {progress_data}"
            )
            # Update the widget to show game over status and determine winner
            mafia_alive = progress_data["full_data"]["mafia_alive"]
            town_alive = progress_data["full_data"]["townspeople_alive"]

            widget.mafia_alive = mafia_alive
            widget.townspeople_alive = town_alive

            if mafia_alive >= town_alive:
                winner_text = "🐍 Mafia Win!"
                widget.set_border_style(GameWidget.MAFIA_WIN_BORDER_STYLE)
            else:
                winner_text = "🏠 Town Win!"
                widget.set_border_style(GameWidget.TOWN_WIN_BORDER_STYLE)

            widget.phase = "Game Over"
            widget.progress_text = winner_text  # Actually set the progress_text
        else:
            raise Exception(
                f"Widget {tui_game_id} not found in active_games dictionary."
            )

    def _get_or_create_game_widget(
        self, progress_data: Dict[str, Any]
    ) -> Optional[GameWidget]:
        """Get existing game widget or create a new one if needed."""
        contest_name = progress_data.get("contest_name", "Unknown")
        game_index = progress_data.get("game_index", -1)
        tui_game_id = f"{contest_name}/Game {game_index}"
        internal_game_id = progress_data.get("internal_game_id")
        if not internal_game_id:  # Early return if no valid ID
            self.log.error("Missing internal_game_id in progress data")
            return None

        # Create unique internal ID with consistent format
        unique_internal_id = f"{contest_name}_game_{internal_game_id}"
        # self.log.info(f"Using unique internal ID: {unique_internal_id}")

        full_data = progress_data.get("full_data")
        widget = self.active_games.get(tui_game_id)

        # Create new widget if needed
        if widget is None and full_data:
            self.log.info(f"Creating widget {tui_game_id} from progress callback")
            widget = GameWidget()
            try:
                # Mount first
                self.query_one(ActiveGamesContainer).mount(widget)
                # Then add to dicts using the unique internal ID
                self.active_games[tui_game_id] = widget
                self.game_widget_map[unique_internal_id] = tui_game_id
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
                widget.progress_text = progress_data.get("text", "")
                widget.kb_update_text = ""  # Always start with empty kb_update_text

            except Exception as e:
                self.log.error(
                    f"Failed to create/update widget {tui_game_id} from callback: {e}"
                )
                # Clean up if creation failed partially
                if tui_game_id in self.active_games:
                    del self.active_games[tui_game_id]
                if unique_internal_id in self.game_widget_map:
                    del self.game_widget_map[unique_internal_id]
                return None

        elif not widget and progress_data.get("phase_name") != "Game Over":
            # Only log warning if not game over
            self.log.warning(
                f"Widget {tui_game_id} not found and no full data in callback for {unique_internal_id}. Progress: {progress_data.get('text')}"
            )

        return widget

    def _update_widget_state(
        self, widget: GameWidget, progress_data: Dict[str, Any]
    ) -> None:
        """Update an existing widget with new game state."""
        full_data = progress_data.get("full_data")
        progress_text = progress_data.get("text")
        phase_name = progress_data.get("phase_name")

        # Don't update progress text if we're in game over state
        if phase_name == "Game Over":
            return

        # Handle KB update status - show notes updating in progress text only
        if progress_data.get("updating_kb"):
            # Keep the notes update in progress_text
            widget.kb_update_text = ""
        elif progress_data.get("clear_kb_status"):
            widget.kb_update_text = ""

        # Update full data if provided
        if full_data:
            widget.update_all(
                progress_data.get("contest_name", "Unknown")
                + f"/Game {progress_data.get('game_index', -1)}",
                full_data.get("mafia_model", widget.mafia_model),
                full_data.get("town_model", widget.town_model),
                full_data.get("phase", widget.phase),
                full_data.get("day_count", widget.day_count),
                full_data.get("mafia_alive", widget.mafia_alive),
                full_data.get("townspeople_alive", widget.townspeople_alive),
            )

        # Update progress text if not in game over state
        if progress_text is not None:
            # Add emojis based on the event type
            if "speaking" in progress_text.lower():
                progress_text = f"💬 {progress_text}"
            elif "vote" in progress_text.lower():
                progress_text = f"⚖️ {progress_text}"
            elif "eliminated" in progress_text:
                progress_text = f"🔫 {progress_text}"
            elif "notes" in progress_text.lower():
                progress_text = f"📝 {progress_text}"
            widget.progress_text = progress_text

    # --- Game Completion Tracking ---
    def _increment_total_games(self) -> None:
        """Increment both total and round-specific game counters and update the status widget."""
        self.total_games_completed_count += 1
        self.round_games_completed_count += 1

        def update_status():
            try:
                status_widget = self.query_one(TournamentStatus)
                status_widget.total_games_completed = self.total_games_completed_count
                status_widget.round_games_completed = self.round_games_completed_count
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
                message.append("💬 ", style="bold")
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
                message.append("🔫  Eliminated by day vote: ", style="red")
                message.append(eliminated, style="bold")
            elif event_type == "MAFIA_KILL":
                eliminated = data.get("eliminated", "?")
                message.append("🔫 Eliminated by mafia: ", style="red")
                message.append(eliminated, style="bold")
            elif event_type == "UPDATING_NOTES":
                message.append("📝 Updating notes...")
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
            # Reset round-specific game counter at the start of each round
            self.round_games_completed_count = 0
            self.query_one(TournamentStatus).round_games_completed = 0

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
