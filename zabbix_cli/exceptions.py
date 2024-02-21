from __future__ import annotations

import functools
from typing import Any
from typing import NoReturn
from typing import Optional
from typing import Protocol
from typing import runtime_checkable
from typing import Type
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pydantic import ValidationError
    from httpx import ConnectError
    from httpx import RequestError


class ZabbixCLIError(Exception):
    """Base exception class for ZabbixCLI exceptions."""


class ConfigError(ZabbixCLIError):
    """Error with configuration file."""


class CommandFileError(ZabbixCLIError):
    """Error running bulk commands from a file."""


class AuthTokenFileError(ZabbixCLIError):
    """Auth token file error."""


class AuthTokenError(ZabbixCLIError):  # NOTE: unused
    """Auth token (not file) error."""


class ZabbixAPIException(ZabbixCLIError):
    # Extracted from pyzabbix, hence *Exception suffix instead of *Error
    """generic zabbix api exception
    code list:
         -32602 - Invalid params (eg already exists)
         -32500 - no permissions
    """

    def __init__(self, *args, code: int | None = None, params: Any = None) -> None:
        self.code = code
        self.params = params
        super().__init__(*args)


class ZabbixNotFoundError(ZabbixAPIException):
    """A Zabbix API resource was not found."""


class Exiter(Protocol):
    """Protocol class for exit function that can be passed to an
    exception handler function.

    See Also
    --------
    [zabbix_cli.exceptions.HandleFunc][]
    """

    def __call__(
        self,
        message: str,
        code: int = ...,
        exception: Optional[Exception] = ...,
        **kwargs: Any,
    ) -> NoReturn:
        ...


@runtime_checkable
class HandleFunc(Protocol):
    """Interface for exception handler functions.

    They take any exception and an Exiter function as the arguments
    and exit with the appropriate message after running any necessary
    cleanup and/or logging.
    """

    def __call__(self, e: Any) -> NoReturn:
        ...


def handle_notraceback(e: Exception) -> NoReturn:
    """Handles an exception with no traceback in console.
    The exception is logged with a traceback in the log file."""
    get_exit_err()(str(e), exception=e, exc_info=True)


def handle_validation_error(e: ValidationError) -> NoReturn:
    """Handles a Pydantic validation error."""
    # TODO: Use some very primitive heuristics to determine whether or not
    # the error is from an API response or somewhere else
    get_exit_err()(str(e), exception=e, exc_info=True)


def _fmt_request_error(e: RequestError, exc_type: str, reason: str) -> str:
    method = e.request.method
    url = e.request.url
    return f"{exc_type}: {method} {url} - {reason}"


def handle_connect_error(e: ConnectError) -> NoReturn:
    """Handles an httpx ConnectError."""
    # Simple heuristic here to determine cause
    if e.args and "connection refused" in str(e.args[0]).casefold():
        reason = "Connection refused"
    else:
        reason = str(e)
    msg = _fmt_request_error(e, "Connection error", reason)
    get_exit_err()(msg, exception=e, exc_info=False)


def handle_zabbix_api_exception(e: ZabbixAPIException) -> NoReturn:
    """Handles a ZabbixAPIException."""
    from zabbix_cli.state import get_state

    state = get_state()

    # If we have a stale auth token, we need to clear it.
    if (
        state.is_config_loaded
        and state.config.app.use_auth_token_file
        and "re-login" in e.args[0]
    ):
        from zabbix_cli.auth import clear_auth_token_file

        # Clear token file and from the config object
        clear_auth_token_file(state.config)
        if state.repl:  # kinda hacky
            state.configure(state.config)
        # NOTE: ideally we automatically re-run the command here, but that's
        # VERY hacky and could lead to unexpected behavior.
        get_exit_err()("Auth token expired. Re-run the command to re-authenticate.")
    else:
        # TODO: extract the reason for the error from the exception here
        # and add it to the message.
        handle_notraceback(e)


def get_exception_handler(type_: Type[Exception]) -> Optional[HandleFunc]:
    """Returns the exception handler for the given exception type."""
    from httpx import ConnectError
    from pydantic import ValidationError

    EXC_HANDLERS = {
        ZabbixAPIException: handle_zabbix_api_exception,  # NOTE: use different strategy for this?
        ZabbixCLIError: handle_notraceback,
        ValidationError: handle_validation_error,
        ConnectError: handle_connect_error,
        ConfigError: handle_notraceback,  # NOTE: can we remove this? subclass of ZabbixCLIError
    }  # type: dict[type[Exception], HandleFunc]
    """Mapping of exception types to exception handling strategies."""

    handler = EXC_HANDLERS.get(type_, None)
    if handler:
        return handler
    if type_.__bases__:
        for base in type_.__bases__:
            handler = get_exception_handler(base)
            if handler:
                return handler
    return None


def handle_exception(e: Exception) -> NoReturn:
    """Handles an exception and exits with the appropriate message."""
    handler = get_exception_handler(type(e))
    if not handler:
        raise e
    handler(e)


@functools.lru_cache(maxsize=1)
def get_exit_err() -> Exiter:
    """Cached lazy-import of `zabbix_cli.output.console.exit_err`.
    Avoids circular imports. Because we can "exit" multiple times in the
    REPL, it's arguably worth caching the import this way.
    """
    from zabbix_cli.output.console import exit_err as _exit_err

    return _exit_err
