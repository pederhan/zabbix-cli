from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import NoReturn
from typing import Optional

import typer
from rich.console import Console

from zabbix_cli.logs import logger
from zabbix_cli.output.formatting.path import path_link
from zabbix_cli.output.style import RICH_THEME
from zabbix_cli.output.style import Icon
from zabbix_cli.state import get_state

# stdout console used to print results
console = Console(theme=RICH_THEME)

# stderr console used to print prompts, messages, etc.
err_console = Console(
    stderr=True,
    highlight=False,
    soft_wrap=True,
    theme=RICH_THEME,
)


RESERVED_EXTRA_KEYS = (
    "name",
    "level",
    "pathname",
    "lineno",
    "msg",
    "args",
    "exc_info",
    "func",
    "sinfo",
)


def get_extra_dict(**kwargs: Any) -> Dict[str, Any]:
    """Format the extra dict for logging. Renames some keys to avoid
    collisions with the default keys.

    See: https://docs.python.org/3.11/library/logging.html#logging.LogRecord
    """
    for k, v in list(kwargs.items()):  # must be list to change while iterating
        if k in RESERVED_EXTRA_KEYS:
            kwargs[f"{k}_"] = v  # add trailing underscore to avoid collision
            del kwargs[k]
    return kwargs


def debug_kv(key: str, value: Any) -> None:
    """Print and log a key value pair."""
    msg = f"[bold]{key:<20}:[/bold] {value}"
    logger.debug(msg, extra=get_extra_dict(key=key, value=value))
    err_console.print(msg)


def debug(message: str, icon: str = "", *args: Any, **kwargs: Any) -> None:
    """Log with INFO level and print an informational message."""
    logger.debug(message, extra=get_extra_dict(**kwargs))
    err_console.print(message)


def info(message: str, icon: str = Icon.INFO, *args: Any, **kwargs: Any) -> None:
    """Log with INFO level and print an informational message."""
    logger.info(message, extra=get_extra_dict(**kwargs))
    err_console.print(f"[success]{icon}[/] {message}")


def success(message: str, icon: str = Icon.OK, **kwargs: Any) -> None:
    """Log with INFO level and print a success message."""
    logger.info(message, extra=get_extra_dict(**kwargs))
    err_console.print(f"[success]{icon}[/] {message}")


def warning(message: str, icon: str = Icon.WARNING, **kwargs: Any) -> None:
    """Log with WARNING level and optionally print a warning message."""
    logger.warning(message, extra=get_extra_dict(**kwargs))
    err_console.print(f"[warning]{icon} {message}[/]")


def error(
    message: str,
    icon: str = Icon.ERROR,
    exc_info: bool = False,
    log: bool = True,
    **kwargs: Any,
) -> None:
    """Log with ERROR level and print an error message."""
    if log:  # we can disable logging when the logger isn't set up yet
        logger.error(message, extra=get_extra_dict(**kwargs), exc_info=exc_info)
    err_console.print(f"[error]{icon} ERROR: {message}")


def print_help(ctx: typer.Context) -> None:
    console.print(ctx.command.get_help(ctx))
    raise SystemExit(1)


def exit_ok(message: Optional[str] = None, code: int = 0, **kwargs: Any) -> NoReturn:
    """Logs a message with INFO level and exits with the given code (default: 0)

    Parameters
    ----------
    message : str
        Message to print.
    code : int, optional
        Exit code, by default 0
    **kwargs
        Additional keyword arguments to pass to the extra dict.
    """
    if message:
        info(message, **kwargs)
    raise SystemExit(code)


def exit_err(
    message: str, code: int = 1, exception: Optional[Exception] = None, **kwargs: Any
) -> NoReturn:
    """Logs a message with ERROR level and exits with the given
    code (default: 1).

    Parameters
    ----------
    message : str
        Message to print.
    code : int, optional
        Exit code, by default 1
    **kwargs
        Additional keyword arguments to pass to the extra dict.
    """
    state = get_state()
    if not state.is_config_loaded:
        # HACK: prevents unconfigured logger from printing to stderr
        kwargs["log"] = False

    # Render JSON-formatted error message if output format is JSON
    if state.is_config_loaded and state.config.app.output_format == "json":
        from zabbix_cli.models import Result
        from zabbix_cli.models import ReturnCode
        from zabbix_cli.output.render import render_json

        errors: List[str] = []
        if exception:
            errors.extend(str(a) for a in exception.args)
            if exception.__cause__:
                errors.extend(str(a) for a in exception.__cause__.args)
        render_json(
            Result(message=message, return_code=ReturnCode.ERROR, errors=errors)
        )
    else:
        error(message, **kwargs)
    raise SystemExit(code)


def print_toml(toml_str: str) -> None:
    """Prints TOML to stdout using the default console."""
    console.print(
        toml_str,
        markup=False,  # TOML tables could be interpreted as rich markup
        no_wrap=True,  # prevents mangling whitespace
    )


def print_path(path: Path) -> None:
    """Prints a path to stdout using the default console."""
    console.print(
        path_link(path),
        highlight=False,
        soft_wrap=True,
    )
