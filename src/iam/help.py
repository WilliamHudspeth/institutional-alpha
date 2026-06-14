"""Context-aware help system for Institutional Alpha."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

HELP_CONTENT = {
    "valuation": """
Quick Valuation:
  Runs a fast, single-method valuation check on a ticker.
  Useful for initial screening.

  Example: IA> value AAPL
""",
    "dcf": """
FCFE DCF Engine:
  Full multi-stage discounted cash flow model.
  Requires revenue growth, margin, and reinvestment assumptions.

  Example: IA> dcf MSFT
""",
    "reverse-dcf": """
Reverse DCF:
  Solves for the growth rate implied by the current market price.
  High implied growth vs history suggests expectations might be too high.

  Example: IA> reverse-dcf NVDA
""",
    "screener": """
Stock Screener:
  Filters the coverage universe based on factor z-scores (Quality, Value, Momentum).

  Example: IA> screen quality > 1.5
""",
}


def display_help(topic: str | None = None):
    """Display help information for a specific topic or general overview."""
    if not topic:
        _display_general_help()
    elif topic.lower() in HELP_CONTENT:
        console.print(
            Panel(
                HELP_CONTENT[topic.lower()],
                title=f"Help: {topic.capitalize()}",
                border_style="cyan",
            )
        )
    else:
        console.print(f"[red]No help topic found for: {topic}[/red]")
        _display_general_help()


def _display_general_help():
    table = Table(title="Institutional Alpha Command Reference")
    table.add_column("Command", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Example", style="green")

    table.add_row("value <TKR>", "Quick valuation", "value AAPL")
    table.add_row("dcf <TKR>", "Full DCF analysis", "dcf MSFT")
    table.add_row("reverse-dcf <TKR>", "Market implied growth", "reverse-dcf NVDA")
    table.add_row("screen <EXPR>", "Factor screening", "screen quality > 1.0")
    table.add_row("backtest <NAME>", "Run backtest scenario", "backtest momentum")
    table.add_row("help <TOPIC>", "Detailed topic help", "help dcf")
    table.add_row("quit", "Exit application", "quit")

    console.print(table)


if __name__ == "__main__":
    display_help()
