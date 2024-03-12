from __future__ import annotations

from functools import lru_cache
from typing import Any
from typing import List
from typing import Optional

import click
import typer
from pydantic import BaseModel
from pydantic import model_validator
from typer.core import TyperArgument
from typer.core import TyperCommand

from .markup import markup_as_plain_text
from .markup import markup_to_markdown


def get(param: Any, attr: str) -> Any:
    """getattr that defaults to None"""
    return getattr(param, attr, None)


class ParamSummary(BaseModel):
    """Serializable representation of a click.Parameter."""

    allow_from_autoenv: Optional[bool] = None
    confirmation_prompt: Optional[bool] = None
    choices: Optional[List[str]] = None
    count: Optional[bool] = None
    default: Optional[Any] = None
    envvar: Optional[str]
    expose_value: bool
    flag_value: Optional[Any] = None
    help: str
    hidden: Optional[bool] = None
    human_readable_name: str
    is_argument: bool
    is_eager: bool = False
    is_bool_flag: Optional[bool] = None
    is_flag: Optional[bool] = None
    is_option: Optional[bool]
    max: Optional[int] = None
    min: Optional[int] = None
    metavar: Optional[str]
    multiple: bool
    name: Optional[str]
    nargs: int
    opts: List[str]
    prompt: Optional[str] = None
    prompt_required: Optional[bool] = None
    required: bool
    secondary_opts: List[str] = []
    show_choices: Optional[bool] = None
    show_default: Optional[bool] = None
    show_envvar: Optional[bool] = None
    type: str

    @classmethod
    def from_param(cls, param: click.Parameter) -> ParamSummary:
        """Construct a new ParamSummary from a click.Parameter."""
        try:
            help_ = param.help or ""  # type: ignore
        except AttributeError:
            help_ = ""

        is_argument = isinstance(param, (click.Argument, TyperArgument))
        return cls(
            allow_from_autoenv=get(param, "allow_from_autoenv"),
            confirmation_prompt=get(param, "confirmation_prompt"),
            count=get(param, "count"),
            choices=get(param.type, "choices"),
            default=param.default,
            envvar=param.envvar,  # TODO: support list of envvars
            expose_value=param.expose_value,
            flag_value=get(param, "flag_value"),
            help=help_,
            hidden=get(param, "hidden"),
            human_readable_name=param.human_readable_name,
            is_argument=is_argument,
            is_bool_flag=get(param, "is_bool_flag"),
            is_eager=param.is_eager,
            is_flag=get(param, "is_flag"),
            is_option=get(param, "is_option"),
            max=get(param.type, "max"),
            min=get(param.type, "min"),
            metavar=param.metavar,
            multiple=param.multiple,
            name=param.name,
            nargs=param.nargs,
            opts=param.opts,
            prompt=get(param, "prompt"),
            prompt_required=get(param, "prompt_required"),
            required=param.required,
            secondary_opts=param.secondary_opts,
            show_choices=get(param, "show_choices"),
            show_default=get(param, "show_default"),
            show_envvar=get(param, "show_envvar"),
            type=param.type.name,
        )

    @property
    def help_plain(self) -> str:
        return markup_as_plain_text(self.help)

    @property
    def help_md(self) -> str:
        return markup_to_markdown(self.help)

    @model_validator(mode="before")
    def _fmt_metavar(cls, data: dict[str, Any]) -> dict[str, Any]:
        metavar = data.get("metavar") or data.get("human_readable_name", "")
        assert isinstance(metavar, str)
        metavar = metavar.upper()
        if data.get("multiple"):
            new_metavar = f"<{metavar},[{metavar}...]>"
        else:
            new_metavar = f"<{metavar}>"
        data["metavar"] = new_metavar
        return data


# TODO: split up CommandSummary into CommandSummary and CommandSearchResult
# so that the latter can have the score field
class CommandSummary(BaseModel):
    """Convenience class for accessing information about a command."""

    category: Optional[str] = None  # not part of TyperCommand
    deprecated: bool
    epilog: Optional[str]
    help: str
    hidden: bool
    name: str
    options_metavar: str
    params: List[ParamSummary] = []
    score: int = 0  # match score (not part of TyperCommand)
    short_help: Optional[str]

    @classmethod
    def from_command(
        cls, command: TyperCommand, name: str | None = None, category: str | None = None
    ) -> CommandSummary:
        """Construct a new CommandSummary from a TyperCommand."""
        return cls(
            category=category,
            deprecated=command.deprecated,
            epilog=command.epilog or "",
            help=command.help or "",
            hidden=command.hidden,
            name=name or command.name or "",
            options_metavar=command.options_metavar or "",
            params=[ParamSummary.from_param(p) for p in command.params],
            short_help=command.short_help or "",
        )

    @property
    def help_plain(self) -> str:
        return markup_as_plain_text(self.help)

    @property
    def help_md(self) -> str:
        return markup_to_markdown(self.help)

    @property
    def usage(self) -> str:
        parts = [self.name]

        # Assume arg list is sorted by required/optional
        # `<POSITIONAL_ARG1> <POSITIONAL_ARG2> [OPTIONAL_ARG1] [OPTIONAL_ARG2]`
        for arg in self.arguments:
            metavar = arg.metavar or arg.human_readable_name
            parts.append(metavar)

        # Command with both required and optional options:
        # `--option1 <opt1> --option2 <opt2> [OPTIONS]`
        has_optional = False
        for option in self.options:
            if option.required:
                metavar = option.metavar or option.human_readable_name
                if option.opts:
                    s = f"{max(option.opts)} {metavar}"
                else:
                    # this shouldn't happen, but just in case. A required
                    # option without any opts is not very useful.
                    # NOTE: could raise exception here instead
                    s = metavar
                parts.append(s)
            else:
                has_optional = True
        if has_optional:
            parts.append("[OPTIONS]")

        return " ".join(parts)

    @property
    def options(self) -> List[ParamSummary]:
        return [p for p in self.params if not p.is_argument]

    @property
    def arguments(self) -> List[ParamSummary]:
        return [p for p in self.params if p.is_argument]


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


@lru_cache(maxsize=None)
def get_app_commands(app: typer.Typer) -> list[CommandSummary]:
    """Get a list of commands from a typer app."""
    return _get_app_commands(app)


def _get_app_commands(
    app: typer.Typer,
    cmds: list[CommandSummary] | None = None,
) -> list[CommandSummary]:
    if cmds is None:
        cmds = []

    cmd = typer.main.get_command(app)
    groups: dict[str, TyperCommand] = {}
    try:
        groups = cmd.commands  # type: ignore
    except AttributeError:
        pass

    # If we have subcommands, we need to go deeper.
    for command in groups.values():
        if command.deprecated:  # skip deprecated commands
            continue

        cmds.append(
            CommandSummary.from_command(
                command, name=command.name, category=command.rich_help_panel
            )
        )

    return sorted(cmds, key=lambda x: x.name)


def get_app_callback_options(app: typer.Typer) -> list[typer.models.OptionInfo]:
    """Get the options of the main callback of a Typer app."""
    options = []  # type: list[typer.models.OptionInfo]

    if not app.registered_callback:
        return options

    callback = app.registered_callback.callback

    if not callback:
        return options
    if not hasattr(callback, "__defaults__") or not callback.__defaults__:
        return options

    for option in callback.__defaults__:
        options.append(option)
    return options
