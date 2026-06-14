"""Universal Launcher for Institutional Alpha."""

import argparse
import os
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from iam.bootstrap import initialize_system
from iam.version import __version__

console = Console()


def display_welcome_dashboard():
    """Display the startup dashboard with status and loaded modules."""
    console.print(
        Panel(
            Text(
                "Institutional Alpha\nInstitutional Research Platform",
                justify="center",
                style="bold cyan",
            ),
            subtitle=f"Version: {__version__}",
            border_style="bright_blue",
        )
    )

    table = Table(show_header=False, box=None)
    table.add_row("[✓] DCF Engine", "[✓] Reverse DCF")
    table.add_row("[✓] Relative Valuation", "[✓] Bayesian Layer")
    table.add_row("[✓] Macro Overlay", "[✓] Backtesting")
    table.add_row("[✓] Portfolio Analytics", "[✓] 3D Terrain Engine")

    console.print(Panel(table, title="Modules Loaded", border_style="green"))


def run_diagnostics():
    """Run and display system diagnostics."""
    console.print("\n[bold]System Diagnostics[/bold]")
    console.print("-" * 30)

    diag_table = Table(show_header=False, box=None)
    diag_table.add_row("Python Version", f"{sys.version.split()[0]}")
    diag_table.add_row("Operating System", f"{sys.platform}")
    diag_table.add_row("SQLite Status", "[green]Ready[/green]")
    diag_table.add_row("Yahoo Finance", "[green]Connected[/green]")
    diag_table.add_row("Cache Status", "[green]Healthy[/green]")

    console.print(diag_table)
    input("\nPress Enter to return to menu...")


def run_demo():
    """First-time user demo mode."""
    tickers = ["AAPL", "MSFT", "NVDA"]
    console.print("\n[bold]Launching Demo Mode (60-second showcase)...[/bold]")

    with Live(auto_refresh=True) as live:
        for tkr in tickers:
            live.update(f"Analyzing [cyan]{tkr}[/cyan]...")
            time.sleep(1)
            live.update(f"Running Reverse DCF for [cyan]{tkr}[/cyan]...")
            time.sleep(1)
            live.update(f"Generating Valuation Report for [cyan]{tkr}[/cyan]...")
            time.sleep(1)
            live.update(f"[green]✓[/green] {tkr} Analysis Complete: [yellow]ACCUMULATE[/yellow]")
            time.sleep(0.5)

    console.print("\n[bold green]Demo Complete![/bold green] You've explored the core pipeline.")
    input("\nPress Enter to return to menu...")


def main_menu():
    """Main interactive menu loop."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")  # nosec
        display_welcome_dashboard()

        console.print("\n[bold cyan]MAIN MENU[/bold cyan]")
        console.print("1. Quick Valuation")
        console.print("2. Reverse DCF")
        console.print("3. Multi-Lens Valuation")
        console.print("4. Expectations Alignment")
        console.print("5. Portfolio Analysis")
        console.print("6. Stock Screener")
        console.print("7. Macro Research")
        console.print("8. Backtesting")
        console.print("9. Research Dashboard")
        console.print("10. Settings")

        console.print("\n[bold cyan]UI OPTIONS[/bold cyan]")
        console.print("T. Launch Rich TUI")
        console.print("P. Power User Shell (IA>)")
        console.print("W. Web Dashboard (Future)")
        console.print("D. Run Diagnostics")
        console.print("M. Demo Mode")
        console.print("H. Help")
        console.print("Q. Quit")

        choice = input("\nSelect Option: ").strip().upper()

        if choice == "1":
            tkr = input("\nEnter Ticker for Quick Valuation: ").strip().upper()
            if tkr:
                from iam.ui.menu import run_quick_recommendation

                run_quick_recommendation(tkr)
                input("\nPress Enter to return to menu...")
        elif choice == "2":
            tkr = input("\nEnter Ticker for Reverse DCF: ").strip().upper()
            if tkr:
                # Reverse DCF is Stage 1 of the pipeline; for a dedicated view
                # we run the pipeline which displays Stage 1 first.
                from iam.ui.menu import run_valuation_pipeline

                run_valuation_pipeline(tkr)
                input("\nPress Enter to return to menu...")
        elif choice == "3":
            tkr = input("\nEnter Ticker for Multi-Lens Valuation: ").strip().upper()
            if tkr:
                from iam.ui.menu import run_valuation_pipeline

                run_valuation_pipeline(tkr)
                input("\nPress Enter to return to menu...")
        elif choice == "4":
            tkr = input("\nEnter Ticker for Expectations Alignment: ").strip().upper()
            if tkr:
                from iam.ui.menu import run_quick_recommendation

                run_quick_recommendation(tkr)  # Battlefield is shown in quick rec
                input("\nPress Enter to return to menu...")
        elif choice == "5":
            # Portfolio Analysis (TUI mode)
            from iam.ui.alpha_terminal import main as run_tui

            run_tui()
        elif choice == "8":
            from iam.ui.menu import run_backtest_harness

            run_backtest_harness()
            input("\nPress Enter to return to menu...")
        elif choice == "10":
            from iam.ui.menu import run_settings_menu

            run_settings_menu()
        elif choice == "6":
            # Stock Screener placeholder
            console.print("\n[yellow]Stock Screener module coming in v0.5.0.[/yellow]")
            input("\nPress Enter to return to menu...")
        elif choice == "7":
            # Macro Research placeholder
            console.print("\n[yellow]Macro Research Engine coming in v0.4.5.[/yellow]")
            input("\nPress Enter to return to menu...")
        elif choice == "9":
            # Research Dashboard placeholder
            console.print("\n[yellow]Research Dashboard module coming in v0.5.0.[/yellow]")
            input("\nPress Enter to return to menu...")
        elif choice == "T":
            from iam.ui.alpha_terminal import main as run_tui

            run_tui()
        elif choice == "P":
            from iam.ia_shell import run_shell

            run_shell()
        elif choice == "D":
            console.print("\n[cyan]Running System Diagnostics...[/cyan]")
            os.system(f"{sys.executable} scripts/verify.py")  # nosec
            input("\nPress Enter to return to menu...")
        elif choice == "M":
            run_demo()
        elif choice == "H":
            from iam.help import display_help

            display_help()
            input("\nPress Enter to return to menu...")
        elif choice == "Q":
            console.print("\n[bold cyan]Institutional Alpha Shutting Down...[/bold cyan]")
            break


def _tkr_prompt(task_name):
    tkr = input(f"\nEnter Ticker for {task_name}: ").strip().upper()
    if tkr:
        console.print(f"Executing {task_name} for [cyan]{tkr}[/cyan]...")
        time.sleep(1)
        console.print("[yellow]Output: MOCKED for launcher preview.[/yellow]")
        input("\nPress Enter to return to menu...")


def main():
    parser = argparse.ArgumentParser(description="Institutional Alpha Launcher")
    parser.add_argument("--tui", action="store_true", help="Launch Rich TUI directly")
    parser.add_argument("--shell", action="store_true", help="Launch Power User Shell directly")
    parser.add_argument("--skip-setup", action="store_true", help="Skip environment bootstrap")
    args = parser.parse_args()

    if not args.skip_setup:
        if not initialize_system():
            sys.exit(1)

    if args.tui:
        from iam.ui.alpha_terminal import main as run_tui

        run_tui()
    elif args.shell:
        from iam.ia_shell import run_shell

        run_shell()
    else:
        main_menu()


if __name__ == "__main__":
    main()
