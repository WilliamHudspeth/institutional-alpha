"""Power User Shell for Institutional Alpha."""

import cmd

from rich.console import Console

from iam.help import display_help

console = Console()


class IAShell(cmd.Cmd):
    intro = "Welcome to the Institutional Alpha Power Shell. Type help or ? to list commands.\n"
    prompt = "IA> "

    def do_value(self, arg):
        """Quick valuation check: value <ticker>"""
        if not arg:
            console.print("[red]Error: Ticker symbol required.[/red]")
            return
        ticker = arg.strip().upper()
        console.print(f"Running quick valuation for [cyan]{ticker}[/cyan]...")
        try:
            from iam.ui.menu import run_quick_recommendation

            run_quick_recommendation(ticker)
        except Exception as e:
            console.print(f"[red]Error executing valuation: {e}[/red]")

    def do_reverse_dcf(self, arg):
        """Market implied growth: reverse-dcf <ticker>"""
        if not arg:
            console.print("[red]Error: Ticker symbol required.[/red]")
            return
        ticker = arg.strip().upper()
        console.print(f"Solving reverse DCF for [cyan]{ticker}[/cyan]...")
        try:
            from iam.ui.menu import run_valuation_pipeline

            run_valuation_pipeline(ticker)
        except Exception as e:
            console.print(f"[red]Error executing reverse DCF: {e}[/red]")

    def do_screen(self, arg):
        """Factor screening: screen quality > 1.5"""
        console.print(f"Filtering coverage universe for: [cyan]{arg}[/cyan]...")
        # TODO: Integration with real engine
        console.print("[yellow]Found 12 matches (MOCKED for demo).[/yellow]")

    def do_backtest(self, arg):
        """Run backtest: backtest momentum"""
        console.print(f"Initializing backtest: [cyan]{arg}[/cyan]...")
        # TODO: Integration with real engine
        console.print(
            "[yellow]Backtest results (MOCKED for demo): Sharpe 1.42, Sortino 1.88[/yellow]"
        )

    def do_help(self, arg):
        """Display help: help [topic]"""
        display_help(arg)

    def do_quit(self, arg):
        """Exit the shell."""
        return True

    def do_exit(self, arg):
        """Exit the shell."""
        return True

    def default(self, line):
        console.print(f"[red]Unknown command: {line.split()[0]}[/red]")
        _display_suggestions(line.split()[0])


def _display_suggestions(cmd):
    # Simple fuzzy match or suggestion logic
    suggestions = ["value", "reverse_dcf", "screen", "backtest", "help", "quit"]
    console.print(f"Suggestions: {', '.join(suggestions)}")


def run_shell():
    try:
        IAShell().cmdloop()
    except KeyboardInterrupt:
        console.print("\nExiting Power Shell...")


if __name__ == "__main__":
    run_shell()
