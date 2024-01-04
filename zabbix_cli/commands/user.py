"""Commands to view and manage macros."""
from __future__ import annotations

import hashlib
import random
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

import typer
from pydantic import computed_field

from zabbix_cli.app import app
from zabbix_cli.exceptions import ZabbixAPIException
from zabbix_cli.exceptions import ZabbixNotFoundError
from zabbix_cli.models import AggregateResult
from zabbix_cli.models import ColsRowsType
from zabbix_cli.models import Result
from zabbix_cli.models import TableRenderable
from zabbix_cli.output.console import error
from zabbix_cli.output.console import exit_err
from zabbix_cli.output.console import success
from zabbix_cli.output.console import warning
from zabbix_cli.output.prompts import bool_prompt
from zabbix_cli.output.prompts import str_prompt
from zabbix_cli.output.render import render_result
from zabbix_cli.pyzabbix.types import User
from zabbix_cli.pyzabbix.types import UserMedia
from zabbix_cli.utils.args import parse_bool_arg
from zabbix_cli.utils.args import parse_list_arg
from zabbix_cli.utils.args import UsergroupPermission
from zabbix_cli.utils.args import UserRole
from zabbix_cli.utils.commands import ARG_POSITIONAL
from zabbix_cli.utils.utils import get_permission


if TYPE_CHECKING:
    from typing import Any  # noqa: F401

# # `zabbix-cli host user <cmd>`
# user_cmd = StatefulApp(
#     name="user",
#     help="Host user commands.",
# )
# app.add_subcommand(user_cmd)

HELP_PANEL = "User"


def get_random_password() -> str:
    x = hashlib.md5()
    x.update(str(random.randint(1, 1000000)).encode("ascii"))
    return x.hexdigest()


class ShowUsermacroTemplateListResult(TableRenderable):
    macro: str
    value: Optional[str] = None
    templateid: str
    template: str

    def __cols__(self) -> list[str]:
        return ["Macro", "Value", "Template ID", "Template"]


@app.command("create_user", rich_help_panel=HELP_PANEL)
def create_user(
    ctx: typer.Context,
    username: Optional[str] = typer.Argument(
        None, help="Username of the user to create."
    ),
    args: Optional[str] = ARG_POSITIONAL,  # legacy
    first_name: Optional[str] = typer.Option(
        None, help="First name of the user to create."
    ),
    last_name: Optional[str] = typer.Option(
        None, help="Last name of the user to create."
    ),
    password: Optional[str] = typer.Option(
        None,
        help="Password of the user to create. Set to '-' to prompt for password. Generates random password if omitted.",
    ),
    role: Optional[UserRole] = typer.Option(
        None,
        "--role",
        help="Role of the user.",
        case_sensitive=False,
    ),
    autologin: Optional[bool] = typer.Option(
        None, help="Enable auto-login for the user."
    ),
    autologout: Optional[str] = typer.Option(
        None,
        help="User session lifetime in seconds. Set to 0 to never expire. Can be a time unit with suffix (0s, 15m, 1h, 1d, etc.)",
    ),
    groups: Optional[str] = typer.Option(
        None, help="Comma-separated list of group IDs to add the user to."
    ),
) -> None:
    """Create a user.

    Prompts for missing values.
    Leave prompt values empty to not set values.
    """
    # TODO: add new options
    if not username:
        username = str_prompt("Username")

    try:
        app.state.client.get_user(username)
        exit_err(f"User {username!r} already exists.")
    except ZabbixNotFoundError:
        pass

    if args:
        warning("Positional arguments are deprecated. Please use options instead.")
        # Old args format: <username>  <first_name> <last_name> <password> <type> <autologin> <autologout> <usergroups>
        # We already have username, so we are left with 7 args.
        # In V2, we either expected NO positional args or ALL of them.
        # So we just match that behavior here.
        if len(args) != 7:
            exit_err(
                "Invalid number of positional arguments. Please use options instead."
            )
        first_name = args[0]
        last_name = args[1]
        password = args[2]
        role = UserRole(args[3])
        autologin = parse_bool_arg(args[4])
        autologout = args[5]
        groups = args[6]

    if not first_name:
        first_name = str_prompt("First name", default="", empty_ok=True)

    if not last_name:
        last_name = str_prompt("Last name", default="", empty_ok=True)

    if password == "-":
        password = str_prompt("Password", password=True)
    elif not password:
        # Generate random password
        password = get_random_password()
    if not role:
        role = UserRole.from_prompt(default=UserRole.USER.value)

    if autologin is None:
        autologin = bool_prompt("Enable auto-login", default=False)

    if autologout is None:
        # Can also be time unit with suffix (0s, 15m, 1h, 1d, etc.)
        autologout = str_prompt("User session lifetime", default="86400")

    if not groups:
        groups = str_prompt("Groups (comma-separated)", default="", empty_ok=True)
    grouplist = parse_list_arg(groups)
    ugroups = [app.state.client.get_usergroup(ug) for ug in grouplist]

    userid = app.state.client.create_user(
        username,
        password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        autologin=autologin,
        autologout=autologout,
        usergroups=ugroups,
    )
    render_result(
        Result(
            message=f"Created user {username!r} ({userid}).",
            result=User(userid=str(userid), username=username),
        ),
    )


@app.command("remove_user", rich_help_panel=HELP_PANEL)
def remove_user(
    ctx: typer.Context,
    username: Optional[str] = typer.Argument(None, help="Username to remove."),
) -> None:
    """Remove a user."""
    if not username:
        username = str_prompt("Username")
    userid = app.state.client.delete_user(username)
    render_result(
        Result(
            message=f"Deleted user {username!r} ({userid}).",
            result=User(userid=str(userid), username=username),
        ),
    )


@app.command("show_user", rich_help_panel=HELP_PANEL)
def show_user(
    ctx: typer.Context,
    username: Optional[str] = typer.Argument(None, help="Username of user"),
) -> None:
    """Show a user."""
    if not username:
        username = str_prompt("Username")
    user = app.state.client.get_user(username)
    render_result(user)


@app.command("show_users", rich_help_panel=HELP_PANEL)
def show_users(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Limit the number of users shown."
    ),
    username: Optional[str] = typer.Option(
        None, "--username", help="Filter users by username. Wildcards supported."
    ),
    role: Optional[UserRole] = typer.Option(
        None,
        "--role",
        help="Filter users by role.",
        case_sensitive=False,
    ),
) -> None:
    """Show all users."""
    kwargs = {}  # type: dict[str, Any]
    if username or role:
        kwargs["search"] = True
    if username:
        kwargs["username"] = username
    if role:
        kwargs["role"] = role
    users = app.state.client.get_users(**kwargs)
    if limit:
        users = users[: abs(limit)]
    render_result(AggregateResult(result=users))


@app.command("create_notification_user", rich_help_panel=HELP_PANEL)
def create_notification_user(
    ctx: typer.Context,
    sendto: Optional[str] = typer.Argument(
        None,
        help="E-mail address, SMS number, jabber address, etc.",
        show_default=False,
    ),
    mediatype: Optional[str] = typer.Argument(
        None,
        help="A media type defined in Zabbix. E.g. [green]'Email'[/green]. [yellow]WARNING: Case sensitive![/yellow]",
        show_default=False,
    ),
    remarks: Optional[str] = typer.Option(
        None,
        "--remarks",
        help="Remarks about the notification user to include in username (max 20 chars).",
    ),
    usergroups: Optional[str] = typer.Option(
        None,
        "--usergroups",
        help="Comma-separated list of usergroups to add the user to. Overrides user groups in config file.",
    ),
    username: Optional[str] = typer.Option(
        None,
        "--username",
        help="Override generated username. Ignores --remarks.",
    ),
    # Legacy V2 args
    args: Optional[str] = ARG_POSITIONAL,
) -> None:
    """Create a notification user.

    Notification users can be used to send notifications when a Zabbix
    event happens.

    Sometimes we need to send a notification to a place not owned by any
    user in particular, e.g. an email list or jabber channel but Zabbix has
    not the possibility of defining media for a usergroup.

    This is the reason we use *notification users*. They are users nobody
    owns, but that can be used by other users to send notifications to the
    media defined in the notification user profile.

    Run [green]show_media_types[/green] to get a list of available media types.

    The configuration file option [green]default_notification_users_usergroup[/green]
    must be configured if [green]--usergroups[/green] is not specified.
    """
    if args:
        warning("Positional arguments are deprecated. Please use options instead.")
        # Old args format: <sendto> <mediatype> <remarks>
        # We already have sendto and mediatype, so we are left with 1 arg.
        if len(args) != 1:
            exit_err(
                "Invalid number of positional arguments. Please use options instead."
            )
        remarks = args[0]
    remarks = remarks or ""

    if not sendto:
        sendto = str_prompt("Send to")

    if not mediatype:
        mediatype = str_prompt("Media type")

    # Generate username
    if username and remarks:
        warning("Both --username and --remarks specified. Ignoring --remarks.")

    if username:
        username = username.strip()
    elif remarks.strip() == "":
        username = "notification-user-" + sendto.replace(".", "-")
    else:
        username = (
            "notification-user-"
            + remarks.strip()[:20].replace(" ", "_")
            + "-"
            + sendto.replace(".", "-")
        )

    # Check if user exists (it should not)
    try:
        app.state.client.get_user(username)
        exit_err(f"User {username!r} already exists.")
    except ZabbixNotFoundError:
        pass

    # Check if media type exists (it should)
    try:
        mt = app.state.client.get_mediatype(mediatype)
    except ZabbixNotFoundError:
        exit_err(
            f"Media type {mediatype!r} does not exist. Run [green]show_media_types[/green] command to get a list of available media types."
        )

    with app.status("Fetching usergroup(s)"):
        if usergroups:
            ug_list = parse_list_arg(usergroups)
        else:
            ug_list = app.state.config.app.default_notification_users_usergroups
        if not ug_list:
            exit_err(
                "No usergroups specified. "
                "Please specify usergroups with the --usergroups option "
                "or configure [green]default_notification_users_usergroup[/green] "
                "in the config file."
            )
        ugroups = [app.state.client.get_usergroup(ug) for ug in ug_list]
        if not ugroups:
            exit_err("No usergroups found.")

    user_media = [
        UserMedia(
            mediatypeid=mt.mediatypeid,
            sendto=sendto,
            active=0,  # enabled
            severity=63,  # all
            period="1-7,00:00-24:00",  # 24/7
        )
    ]

    with app.status("Creating user"):
        userid = app.state.client.create_user(
            username=username,
            password=get_random_password(),
            role=UserRole.USER,
            autologin=False,
            autologout="3600",
            usergroups=ugroups,
            media=user_media,
        )

    render_result(
        Result(
            message=f"Created notification user {username!r} ({userid}).",
            result=User(userid=userid, username=username),
        ),
    )


class UgroupUpdateUsersResult(TableRenderable):
    usergroup: str
    usergroupid: str
    users: list[str]

    def __cols_rows__(self) -> ColsRowsType:
        return (
            ["Usergroup", "Usergroup ID", "Users"],
            [[self.usergroup, self.usergroupid, ", ".join(self.users)]],
        )


class UsergroupAddUsers(UgroupUpdateUsersResult):
    __title__ = "Added Users"


class UsergroupRemoveUsers(UgroupUpdateUsersResult):
    __title__ = "Removed Users"


@app.command("add_user_to_usergroup", rich_help_panel=HELP_PANEL)
def add_user_to_usergroup(
    ctx: typer.Context,
    usernames: Optional[str] = typer.Argument(
        None, help="Comma-separated list of usernames"
    ),
    usergroups: Optional[str] = typer.Argument(
        None,
        help="Comma-separated list of user groups to add the users to. [yellow]WARNING: Case sensitive![/yellow]]",
    ),
) -> None:
    """Adds user(s) to usergroup(s).

    Ignores users not in user groups. Users and groups must exist."""
    # FIXME: requires support for IDs for parity with V2
    if not usernames:
        usernames = str_prompt("Usernames")
    unames = parse_list_arg(usernames)

    if not usergroups:
        usergroups = str_prompt("User groups")
    groupnames = parse_list_arg(usergroups)

    users = [app.state.client.get_user(u) for u in unames]
    ugroups = [app.state.client.get_usergroup(g) for g in groupnames]

    with app.status("Adding users to user groups"):
        for ugroup in ugroups:
            try:
                app.state.client.add_usergroup_users(ugroup, users)
            except ZabbixAPIException as e:
                error(f"Failed to add users to user group {ugroup.name!r}: {e}")
            else:
                success(f"Added users to user group {ugroup.name!r}.")

    render_result(
        UsergroupRemoveUsers(
            usergroup=ugroup.name,
            usergroupid=ugroup.usrgrpid,
            users=[u.username for u in users],
        ),
    )
    success("Added users to user groups.")


@app.command("remove_user_from_usergroup", rich_help_panel=HELP_PANEL)
def remove_user_from_usergroup(
    ctx: typer.Context,
    usernames: Optional[str] = typer.Argument(
        None, help="Comma-separated list of usernames to remove."
    ),
    usergroups: Optional[str] = typer.Argument(
        None,
        help="Comma-separated list of user groups to remove the users from. [yellow]WARNING: Case sensitive![/yellow]]",
    ),
) -> None:
    """Removes user(s) from usergroup(s).

    Ignores users not in user groups. Users and groups must exist."""
    # FIXME: requires support for IDs for parity with V2
    if not usernames:
        usernames = str_prompt("Usernames")
    unames = parse_list_arg(usernames)

    if not usergroups:
        usergroups = str_prompt("User groups")
    groupnames = parse_list_arg(usergroups)

    users = [app.state.client.get_user(u) for u in unames]
    ugroups = [app.state.client.get_usergroup(g) for g in groupnames]

    with app.status("Removing users from user groups"):
        for ugroup in ugroups:
            try:
                app.state.client.add_usergroup_users(ugroup, users)
            except ZabbixAPIException as e:
                exit_err(f"Failed to remove users from user group {ugroup.name!r}: {e}")

    render_result(
        UsergroupRemoveUsers(
            usergroup=ugroup.name,
            usergroupid=ugroup.usrgrpid,
            users=[u.username for u in users],
        ),
    )
    success("Removed users from user groups.")


class AddUsergroupPermissionsResult(TableRenderable):
    usergroup: str
    usergroupid: str
    hostgroups: list[str]
    templategroups: list[str]
    permission: UsergroupPermission

    @computed_field  # type: ignore # computed field on @property
    @property
    def permission_fmt(self) -> str:
        return get_permission(self.permission.as_api_value())

    def __cols_rows__(self) -> ColsRowsType:
        return (
            [
                "Usergroup",
                "Usergroup ID",
                "Host Groups",
                "Template Groups",
                "Permission",
            ],
            [
                [
                    self.usergroup,
                    self.usergroupid,
                    ", ".join(self.hostgroups),
                    ", ".join(self.templategroups),
                    self.permission_fmt,
                ],
            ],
        )


@app.command("add_usergroup_permissions", rich_help_panel=HELP_PANEL)
def add_usergroup_permissions(
    ctx: typer.Context,
    usergroup: Optional[str] = typer.Argument(
        None, help="User group to give permissions to."
    ),
    hostgroups: Optional[str] = typer.Option(
        None,
        "--hgroups",
        "--hostgroups",
        help="Comma-separated list of host group names. [yellow]WARNING: Case sensitive![/yellow]]",
    ),
    templategroups: Optional[str] = typer.Option(
        None,
        "--tgroups",
        "--templategroups",
        help="Comma-separated list of template group names. [yellow]WARNING: Case sensitive![/yellow]]",
    ),
    permission: Optional[UsergroupPermission] = typer.Option(
        None,
        "--permission",
        help="Permission to give to the user group.",
        case_sensitive=False,
    ),
    # Legacy V2 args
    args: Optional[List[str]] = ARG_POSITIONAL,
) -> None:
    """Gives a user group permissions to host groups and template groups.

    Run [green]show_hostgroups[/] to get a list of host groups, and
    [green]show_templategroups --no-templates[/] to get a list of template groups.
    """
    # Legacy positional args: <usergroup> <hostgroups> <permission>
    # We already have usergroup as positional arg, so we are left with 2 args.
    if args:
        warning("Positional arguments are deprecated. Please use options instead.")
        if len(args) != 2:
            exit_err(
                "Invalid number of positional arguments. Please use options instead."
            )
        hostgroups = hostgroups or args[0]
        permission = permission or UsergroupPermission(args[1])

    if not usergroup:
        usergroup = str_prompt("User group")
    ugroup = app.state.client.get_usergroup(usergroup)

    # Only prompt if no group options
    if not hostgroups and not templategroups:
        hostgroups = str_prompt("Host groups", empty_ok=True, default="")
    hgroupnames = parse_list_arg(hostgroups)
    hgroups = [app.state.client.get_hostgroup(h) for h in hgroupnames]

    # Ditto
    if not templategroups and not hostgroups:
        templategroups = str_prompt("Template groups", empty_ok=True, default="")
    tgroupnames = parse_list_arg(templategroups)
    tgroups = [app.state.client.get_templategroup(t) for t in tgroupnames]

    if not hgroupnames and not tgroupnames:
        exit_err("At least one host group or template group must be specified.")

    if not permission:
        permission = UsergroupPermission.from_prompt()

    if hgroups:
        with app.status("Adding host group permissions"):
            try:
                app.state.client.update_usergroup_rights(
                    ugroup, hgroups, permission, hostgroup=True
                )
            except ZabbixAPIException as e:
                exit_err(f"Failed to add host group permissions: {e}")
            else:
                success("Added host group permissions.")

    if tgroups:
        with app.status("Adding template group permissions"):
            try:
                app.state.client.update_usergroup_rights(
                    ugroup, tgroups, permission, hostgroup=False
                )
            except ZabbixAPIException as e:
                exit_err(f"Failed to add template group permissions: {e}")
            else:
                success("Added template group permissions.")

    render_result(
        AddUsergroupPermissionsResult(
            usergroup=ugroup.name,
            usergroupid=ugroup.usrgrpid,
            hostgroups=hgroupnames,
            templategroups=tgroupnames,
            permission=permission,
        ),
    )


@app.command("create_usergroup", rich_help_panel=HELP_PANEL)
def create_usergroup(ctx: typer.Context) -> None:
    pass


@app.command("show_usergroup", rich_help_panel=HELP_PANEL)
def show_usergroup(ctx: typer.Context) -> None:
    pass


@app.command("show_usergroups", rich_help_panel=HELP_PANEL)
def show_usergroups(ctx: typer.Context) -> None:
    pass


@app.command("show_usergroup_permissions", rich_help_panel=HELP_PANEL)
def show_usergroup_permissions(ctx: typer.Context) -> None:
    pass


@app.command("update_usergroup_permissions", rich_help_panel=HELP_PANEL)
def update_usergroup_permissions(ctx: typer.Context) -> None:
    pass
