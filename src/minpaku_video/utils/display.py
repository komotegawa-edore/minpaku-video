from __future__ import annotations

from rich.console import Console

console = Console()


def print_status(label: str, value: str, style: str = "bold") -> None:
    console.print(f"  {label}: [{style}]{value}[/{style}]")


def print_success(message: str) -> None:
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    console.print(f"[red]{message}[/red]")


def print_warning(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")
