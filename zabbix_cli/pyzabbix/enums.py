from __future__ import annotations

from enum import Enum
from typing import Any
from typing import Generic
from typing import List
from typing import Mapping
from typing import Optional
from typing import Type
from typing import TypeVar

from strenum import StrEnum
from typing_extensions import Self

from zabbix_cli.exceptions import ZabbixCLIError

T = TypeVar("T")


class APIStr(str, Generic[T]):
    """String type that can be used as an Enum choice while also
    carrying an API value associated with the string.
    """

    # Instance variables are set by __new__
    api_value: T  # pyright: ignore[reportUninitializedInstanceVariable]
    value: str  # pyright: ignore[reportUninitializedInstanceVariable]
    metadata: Mapping[str, Any]  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(
        cls,
        s: str,
        api_value: T = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> APIStr[T]:
        if isinstance(s, APIStr):
            return s  # type: ignore # Type checker should be able to infer generic type
        if api_value is None:
            raise ZabbixCLIError("API value must be provided for APIStr.")
        obj = str.__new__(cls, s)
        obj.value = s
        obj.api_value = api_value
        obj.metadata = metadata or {}
        return obj


class APIInt(int):
    """Int type that can be used as an Enum choice while also carrying
    a formatted name and metadata associated with the integer.
    """

    # Instance variables are set by __new__
    value: int
    name: str
    metadata: Mapping[str, Any]  # pyright: ignore[reportUninitializedInstanceVariable]

    def __new__(
        cls,
        i: int,
        name: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> APIInt:
        if isinstance(i, APIInt):
            return i
        obj = int.__new__(cls, i)
        obj.value = i
        obj.name = name
        obj.metadata = metadata or {}
        return obj


MixinType = TypeVar("MixinType", bound="Choice")


class IntChoice(Enum):
    value: APIInt  # pyright: ignore[reportIncompatibleMethodOverride]
    __choice_name__: str = ""  # default (falls back to class name)

    def __new__(cls, value: APIInt) -> Self:
        # Adds type checking for members in enum definition
        obj = object.__new__(cls)
        obj._value_ = APIInt(value)
        return obj

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __str__(self) -> str:
        return str(self.value)

    def casefold(self) -> str:
        return str(self.name).casefold()

    def choice(self) -> str:
        return self.casefold()

    @classmethod
    def __fmt_name__(cls) -> str:
        """Return the name of the enum class in a human-readable format.

        If no default is provided, the class name is split on capital letters and
        lowercased, e.g. `ActiveInterface` becomes `active interface`.
        """
        if cls.__choice_name__:
            return cls.__choice_name__
        return (
            "".join([(" " + i if i.isupper() else i) for i in cls.__name__])
            .lower()
            .strip()
        )

    # NOTE: should we use a custom prompt class instead of repurposing the str prompt?
    @classmethod
    def from_prompt(
        cls: Type[Self],
        prompt: Optional[str] = None,
        default: Self = ...,
    ) -> Self:
        """Prompt the user to select a choice from the enum.

        Args:
            prompt (Optional[str], optional): Alternative prompt.
                Defaults to None, which uses the formatted class name.

        Returns:
            MixinType: Enum member selected by the user.
        """
        from zabbix_cli.output.prompts import str_prompt

        if not prompt:
            # Assume
            prompt = cls.__fmt_name__()
            # Uppercase first letter without mangling the rest of the string
            if prompt and prompt[0].islower():
                prompt = prompt[0].upper() + prompt[1:]
        default = default if default is ... else str(default)
        choice = str_prompt(
            prompt,
            choices=cls.choices(),
            default=default,
        )
        return cls(choice)

    @classmethod
    def choices(cls) -> List[str]:
        """Return list of string values of the enum members."""
        return [str(e) for e in cls]

    @classmethod
    def all_choices(cls) -> List[str]:
        """Choices including API values."""
        return [e.choice() for e in cls] + [str(e.value) for e in cls]

    def as_api_value(self) -> int:
        """Return the equivalent Zabbix API value."""
        return self.value

    @classmethod
    def _missing_(cls, value: object) -> Self:
        """Method that is called when an enum member is not found.

        Attempts to find the member with 2 strategies:
        1. Search for a member with the given value
        2. Search for a member with the given name (case-insensitive)
        """
        for v in cls:
            if v.value == value:
                return v
            elif v.name.casefold() == str(value).casefold():
                return v
        raise ZabbixCLIError(f"Invalid {cls.__fmt_name__()}: {value!r}.")


class APIIntEnum(IntChoice):
    """Enum that returns value of member as str."""

    # FIXME: should inherit from string somehow!
    # Does not inherit from str now, as it would convert enum member value
    # to string, thereby losing the API associated value.
    # If we are to do that, we need to hijack the object creation and inject
    # the member value somehow?

    def __str__(self) -> str:
        return str(self.value)

    def as_status(self, default: str = "Unknown", with_code: bool = False) -> str:
        return self.string_from_value(self.value, default=default, with_code=with_code)

    @classmethod
    def string_from_value(
        cls: Type[Self], value: Any, default: str = "Unknown", with_code: bool = False
    ) -> str:
        """Get a formatted status string given a value."""
        try:
            c = cls(value)
            if c.value.name:
                name = c.value.name
            else:
                name = c.name.replace("_", " ")
                # All lowercase is capitalized
                # E.g. "zabbix agent" -> "Zabbix agent"
                # While names with other casing is left as is
                # IPv4, DNS, SNMP, etc.
                if name.islower():
                    name = name.capitalize()
            code = c.value
        except ValueError:
            name = default
            code = value
        if with_code:
            return f"{name} ({code})"
        return name


class Choice(Enum):
    """Enum subclass that allows for an Enum to have APIStr values, which
    enables it to be instantiated with either the name of the option
    or the Zabbix API value of the option.

    We can instantiate the enum with either the name or the API value:
        * `ActiveInterface("available")`
        * `ActiveInterface(1)`
        * `ActiveInterface("1")`

    We use these enums as choices in the CLI, so that users can pass in
    a human readable name for the choice or its API value.

    Since the API itself is inconsistent with usage of strings and ints,
    we support instantiation with either one.

    Provides the `from_prompt` class method, which prompts the user to select
    one of the enum members. The prompt text is generated from the class name
    by default, but can be overridden by setting the `__choice_name__` class var.

    Also provides a method for returning the API value of an enum member with the
    with the `as_api_value()` method.
    """

    value: APIStr[int]  # pyright: ignore[reportIncompatibleMethodOverride]
    __choice_name__: str = ""  # default (falls back to class name)

    def __new__(cls, value: APIStr[int]) -> Choice:
        # Adds type checking for members in enum definition
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __str__(self) -> str:
        return str(self.value)

    def casefold(self) -> str:
        return str(self.value).casefold()

    @classmethod
    def __fmt_name__(cls) -> str:
        """Return the name of the enum class in a human-readable format.

        If no default is provided, the class name is split on capital letters and
        lowercased, e.g. `ActiveInterface` becomes `active interface`.
        """
        if cls.__choice_name__:
            return cls.__choice_name__
        return (
            "".join([(" " + i if i.isupper() else i) for i in cls.__name__])
            .lower()
            .strip()
        )

    # NOTE: should we use a custom prompt class instead of repurposing the str prompt?
    @classmethod
    def from_prompt(
        cls: Type[MixinType],
        prompt: Optional[str] = None,
        default: MixinType = ...,
    ) -> MixinType:
        """Prompt the user to select a choice from the enum.

        Args:
            prompt (Optional[str], optional): Alternative prompt.
                Defaults to None, which uses the formatted class name.

        Returns:
            MixinType: Enum member selected by the user.
        """
        from zabbix_cli.output.prompts import str_prompt

        if not prompt:
            # Assume
            prompt = cls.__fmt_name__()
            # Uppercase first letter without mangling the rest of the string
            if prompt and prompt[0].islower():
                prompt = prompt[0].upper() + prompt[1:]
        default = default if default is ... else str(default)
        choice = str_prompt(
            prompt,
            choices=cls.choices(),
            default=default,
        )
        return cls(choice)

    @classmethod
    def choices(cls) -> List[str]:
        """Return list of string values of the enum members."""
        return [str(e) for e in cls]

    @classmethod
    def all_choices(cls) -> List[str]:
        """Choices including API values."""
        return [str(e) for e in cls] + [str(e.as_api_value()) for e in cls]

    def as_api_value(self) -> int:
        """Return the equivalent Zabbix API value."""
        return self.value.api_value

    @classmethod
    def _missing_(cls, value: object) -> object:
        """Method that is called when an enum member is not found.

        Attempts to find the member with 2 strategies:
        1. Search for a member with the given string value (ignoring case)
        2. Search for a member with the given API value (converted to string)
        """
        for v in cls:
            if v.value == value:
                return v
            # kinda hacky. Should make sure we are dealing with strings here:
            elif str(v.value).lower() == str(value).lower():
                return v
            elif str(v.as_api_value()) == str(value):
                return v
        raise ZabbixCLIError(f"Invalid {cls.__fmt_name__()}: {value!r}.")


class APIStrEnum(Choice):
    """Enum that returns value of member as str."""

    # FIXME: should inherit from string somehow!
    # Does not inherit from str now, as it would convert enum member value
    # to string, thereby losing the API associated value.
    # If we are to do that, we need to hijack the object creation and inject
    # the member value somehow?

    def __str__(self) -> str:
        return str(self.value)

    def as_status(self, default: str = "Unknown", with_code: bool = False) -> str:
        return self.string_from_value(self.value, default=default, with_code=with_code)

    @classmethod
    def string_from_value(
        cls: Type[Self], value: Any, default: str = "Unknown", with_code: bool = False
    ) -> str:
        """Get a formatted status string given a value."""
        try:
            c = cls(value)
            # All lowercase is capitalized
            if str(c.value.islower()):
                name = c.value.capitalize()
            # Everything else is left as is
            else:
                name = str(c.value)
            code = c.value.api_value
        except ValueError:
            name = default
            code = value
        if with_code:
            return f"{name} ({code})"
        return name


class AckStatus(APIIntEnum):
    NO = APIInt(0, "no")
    YES = APIInt(1, "yes")


class ActiveInterface(APIIntEnum):
    """Active interface availability status."""

    __choice_name__ = "Agent availability status"

    UNKNOWN = APIInt(0, "unknown")
    AVAILABLE = APIInt(1, "available")
    UNAVAILABLE = APIInt(2, "unavailable")


class DataCollectionMode(APIIntEnum):
    """Maintenance data collection mode."""

    ON = APIInt(0, "With DC")
    OFF = APIInt(1, "Without DC")


class EventStatus(APIIntEnum):
    OK = APIInt(0, "OK")
    PROBLEM = APIInt(1, "Problem")


class ExportFormat(StrEnum):
    XML = "xml"
    JSON = "json"
    YAML = "yaml"
    PHP = "php"

    @classmethod
    def _missing_(cls, value: object) -> ExportFormat:
        """Case-insensitive missing lookup.

        Allows for both `ExportFormat("JSON")` and `ExportFormat("json")`, etc.
        """
        if not isinstance(value, str):
            raise TypeError(f"Invalid format: {value!r}. Must be a string.")
        value = value.lower()
        for e in cls:
            if e.value.lower() == value:
                return e
        raise ValueError(f"Invalid format: {value!r}.")

    @classmethod
    def get_importables(cls) -> List[ExportFormat]:
        """Return list of formats that can be imported."""
        return [cls.JSON, cls.YAML, cls.XML]


class GUIAccess(APIIntEnum):
    """GUI Access for a user group."""

    __choice_name__ = "GUI Access"

    DEFAULT = APIInt(0, "default")
    INTERNAL = APIInt(1, "internal")
    LDAP = APIInt(2, "LDAP")
    DISABLE = APIInt(3, "disable")


class HostgroupFlag(APIIntEnum):
    """Hostgroup flags."""

    PLAIN = APIInt(0, "plain")
    DISCOVER = APIInt(4, "discover")


class HostgroupType(APIIntEnum):
    """Hostgroup types."""

    NOT_INTERNAL = APIInt(0, "Not internal")
    INTERNAL = APIInt(1, "Internal")


class InterfaceConnectionMode(APIIntEnum):
    """Interface connection mode.

    Controls the value of `useip` when creating interfaces in the API.
    """

    DNS = APIInt(0, "DNS")
    IP = APIInt(1, "IP")


class InterfaceType(APIIntEnum):
    """Interface type."""

    AGENT = APIInt(1, "Agent", metadata={"port": "10050"})
    SNMP = APIInt(2, "SNMP", metadata={"port": "161"})
    IPMI = APIInt(3, "IPMI", metadata={"port": "623"})
    JMX = APIInt(4, "JMX", metadata={"port": "12345"})

    def get_port(self: InterfaceType) -> str:
        """Returns the default port for the given interface type."""
        try:
            return self.value.metadata["port"]
        except KeyError:
            raise ZabbixCLIError(f"Unknown interface type: {self}")


class InventoryMode(APIIntEnum):
    """Host inventory mode."""

    DISABLED = APIInt(-1, "disabled")
    MANUAL = APIInt(0, "manual")
    AUTOMATIC = APIInt(1, "automatic")


class ItemType(APIIntEnum):
    ZABBIX_AGENT = APIInt(0, "Zabbix agent")
    SNMPV1_AGENT = APIInt(1, "SNMPv1 agent")
    ZABBIX_TRAPPER = APIInt(2, "Zabbix trapper")
    SIMPLE_CHECK = APIInt(3, "Simple check")
    SNMPV2_AGENT = APIInt(4, "SNMPv2 agent")
    ZABBIX_INTERNAL = APIInt(5, "Zabbix internal")
    SNMPV3_AGENT = APIInt(6, "SNMPv3 agent")
    ZABBIX_AGENT_ACTIVE = APIInt(7, "Zabbix agent (active)")
    ZABBIX_AGGREGATE = APIInt(8, "Zabbix aggregate")
    WEB_ITEM = APIInt(9, "Web item")
    EXTERNAL_CHECK = APIInt(10, "External check")
    DATABASE_MONITOR = APIInt(11, "Database monitor")
    IPMI_AGENT = APIInt(12, "IPMI agent")
    SSH_AGENT = APIInt(13, "SSH agent")
    TELNET_AGENT = APIInt(14, "TELNET agent")
    CALCULATED = APIInt(15, "calculated")
    JMX_AGENT = APIInt(16, "JMX agent")
    SNMP_TRAP = APIInt(17, "SNMP trap")
    DEPENDENT_ITEM = APIInt(18, "Dependent item")
    HTTP_AGENT = APIInt(19, "HTTP agent")
    SNMP_AGENT = APIInt(20, "SNMP agent")
    SCRIPT = APIInt(21, "Script")


class MacroType(APIIntEnum):
    TEXT = APIInt(0, "text")
    SECRET = APIInt(1, "secret")
    VAULT_SECRET = APIInt(2, "vault secret")


class MaintenancePeriodType(APIIntEnum):
    """Maintenance period."""

    ONETIME = APIInt(0, "one time")
    DAILY = APIInt(2, "daily")
    WEEKLY = APIInt(3, "weekly")
    MONTHLY = APIInt(4, "monthly")


class MaintenanceStatus(APIIntEnum):
    """Host maintenance status."""

    # API values are inverted here compared to monitoring status...
    ON = APIInt(1, "on")
    OFF = APIInt(0, "off")


class MaintenanceType(APIIntEnum):
    """Maintenance type."""

    WITH_DC = APIInt(0, "With DC")
    WITHOUT_DC = APIInt(1, "Without DC")


class MaintenanceWeekType(APIIntEnum):
    """Maintenance every week type."""

    FIRST_WEEK = APIInt(1, "first week")
    SECOND_WEEK = APIInt(2, "second week")
    THIRD_WEEK = APIInt(3, "third week")
    FOURTH_WEEK = APIInt(4, "fourth week")
    LAST_WEEK = APIInt(5, "last week")


class MonitoredBy(APIIntEnum):  # >=7.0 only
    SERVER = APIInt(0, "server")
    PROXY = APIInt(1, "proxy")
    PROXY_GROUP = APIInt(2, "proxygroup")


class MonitoringStatus(APIIntEnum):
    """Host monitoring status."""

    ON = APIInt(0, "on")  # Yes, 0 is on, 1 is off...
    OFF = APIInt(1, "off")
    UNKNOWN = APIInt(
        3, "unknown"
    )  # Undocumented, but shows up in virtual trigger hosts (get_triggers(select_hosts=True))


class ProxyCompatibility(APIIntEnum):
    """Proxy compatibility status for >=7.0"""

    UNDEFINED = APIInt(0, "undefined")
    CURRENT = APIInt(1, "current")
    OUTDATED = APIInt(2, "outdated")
    UNSUPPORTED = APIInt(3, "unsupported")


class ProxyGroupState(APIIntEnum):
    UNKNOWN = APIInt(0, "unknown")
    OFFLINE = APIInt(1, "offline")
    RECOVERING = APIInt(2, "recovering")
    ONLINE = APIInt(3, "online")
    DEGRADING = APIInt(4, "degrading")


class ProxyMode(APIIntEnum):
    """Proxy mode."""

    ACTIVE = APIInt(0, "active")
    PASSIVE = APIInt(1, "passive")


class ProxyModePre70(APIIntEnum):
    """Proxy mode pre 7.0."""

    ACTIVE = APIInt(5, "active")
    PASSIVE = APIInt(6, "passive")


class SNMPAuthProtocol(APIIntEnum):
    """Authentication protocol for SNMPv3."""

    __choice_name__ = "SNMPv3 auth protocol"

    MD5 = APIInt(0, "MD5")
    SHA1 = APIInt(1, "SHA1")
    # >=6.0 only:
    SHA224 = APIInt(2, "SHA224")
    SHA256 = APIInt(3, "SHA256")
    SHA384 = APIInt(4, "SHA384")
    SHA512 = APIInt(5, "SHA512")


class SNMPPrivProtocol(APIIntEnum):
    """Privacy protocol for SNMPv3."""

    __choice_name__ = "SNMPv3 privacy protocol"

    DES = APIInt(0, "DES")
    AES = APIInt(1, "AES")  # < 6.0 only
    # >=6.0 only:
    AES128 = APIInt(1, "AES128")  # >= 6.0
    AES192 = APIInt(2, "AES192")
    AES256 = APIInt(3, "AES256")
    AES192C = APIInt(4, "AES192C")
    AES256C = APIInt(5, "AES256C")


class SNMPSecurityLevel(APIIntEnum):
    __choice_name__ = "SNMPv3 security level"

    # Match casing from Zabbix API
    noAuthNoPriv = APIInt(0, "noAuthNoPriv")
    authNoPriv = APIInt(1, "authNoPriv")
    authPriv = APIInt(2, "authPriv")


class TriggerPriority(APIIntEnum):
    UNCLASSIFIED = APIInt(0, "unclassified")
    INFORMATION = APIInt(1, "information")
    WARNING = APIInt(2, "warning")
    AVERAGE = APIInt(3, "average")
    HIGH = APIInt(4, "high")
    DISASTER = APIInt(5, "disaster")


class UsergroupPermission(APIIntEnum):
    """Usergroup permission levels."""

    DENY = APIInt(0, "deny")
    RO = APIInt(2, "Read Only")
    RW = APIInt(3, "Read/Write")


class UsergroupStatus(APIIntEnum):
    """Usergroup status."""

    ENABLED = APIInt(0, "enabled")
    DISABLED = APIInt(1, "disabled")


class UserRole(APIIntEnum):
    __choice_name__ = "User role"

    # Match casing from Zabbix API
    USER = APIInt(1, "user")
    ADMIN = APIInt(2, "admin")
    SUPERADMIN = APIInt(3, "superadmin")
    GUEST = APIInt(4, "guest")


class ValueType(APIIntEnum):
    NUMERIC_FLOAT = APIInt(0, "Numeric (float)")
    CHARACTER = APIInt(1, "Character")
    LOG = APIInt(2, "Log")
    NUMERIC_UNSIGNED = APIInt(3, "Numeric (unsigned)")
    TEXT = APIInt(4, "Text")
