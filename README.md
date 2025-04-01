# MafiaBench Tournament Visualization

This project implements a Terminal User Interface (TUI) for visualizing MafiaBench tournaments between different language models.

## Requirements

- Python 3.8+
- `textual` library (can be installed via `pip install textual`)
- An OpenRouter API key (set as environment variable `OPEN_ROUTER_API_KEY`)

## Running the Tournament TUI

You can run the tournament visualization with different models using the following command:

```bash
# Set your API key
export OPEN_ROUTER_API_KEY=your_api_key_here

# Run a tournament with multiple models
python run_tui.py --models mistralai/mistral-7b-instruct google/gemma-2-9b-it mistralai/mistral-nemo --rounds 2
```

### Command Line Options

- `--models`: List of model names to include in the tournament (required, minimum 2)
- `--rounds`: Number of tournament rounds (default: 3)
- `--games-per-contest`: Number of games per contest (default: 4)
- `--players-per-game`: Number of players per game (default: 8)
- `--mafia-per-game`: Number of mafia roles per game (default: 2)
- `--temperature`: Temperature setting for model generation (default: 0.7)
- `--request-limit`: Rate limit for API requests per second (default: 60.0)
- `--concurrent-contests`: Number of contests to run concurrently (default: 20)
- `--concurrent-games`: Number of games to run concurrently per contest (default: 4)

## Interface

The TUI provides a real-time view of the tournament with the following elements:

- **Round Status**: Shows the current round number and total rounds
- **ELO Rankings**: Displays models sorted by their current ELO rating
- **Active Games**: Shows all currently running games with details like:
  - Which model is playing as mafia/townsperson
  - The current phase (intro, day, night)
  - How many players of each role are still alive
  - The day count

## Key Bindings

- `d`: Toggle dark mode
- `q`: Quit the application

## Example

```bash
python run_tui.py --models openai/gpt-4-turbo google/gemini-pro-1.5 anthropic/claude-3-opus --rounds 2 --concurrent-contests 2
```
TODO: 



- check summaries are working
- implement tournament. 
    - check logic. 

    - show more event updates in tui? 
    - fix bugs: completed games disappearing. 
    - serialization. 
