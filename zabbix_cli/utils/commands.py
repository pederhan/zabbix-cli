from __future__ import annotations

import click
import typer


def get_parent_ctx(
    ctx: typer.Context | click.core.Context,
) -> typer.Context | click.core.Context:
    """Get the top-level parent context of a context."""
    if ctx.parent is None:
        return ctx
    return get_parent_ctx(ctx.parent)


def get_command_help(command: typer.models.CommandInfo) -> str:
    """Get the help text of a command."""
    if command.help:
        return command.help
    if command.callback and command.callback.__doc__:
        lines = command.callback.__doc__.strip().splitlines()
        if lines:
            return lines[0]
    if command.short_help:
        return command.short_help
    return ""


ARG_POSITIONAL = typer.Argument(
    None,
    help="DEPRECATED: V2-style positional arguments.",
    show_default=False,
)