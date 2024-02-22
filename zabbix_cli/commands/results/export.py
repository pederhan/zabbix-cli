from __future__ import annotations

from pathlib import Path
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

from pydantic import field_serializer

from zabbix_cli.commands.export import ExportType
from zabbix_cli.models import TableRenderable
from zabbix_cli.output.formatting.path import path_link
from zabbix_cli.pyzabbix.enums import ExportFormat

if TYPE_CHECKING:
    from zabbix_cli.models import ColsRowsType
    from zabbix_cli.models import RowsType  # noqa: F401


class ExportResult(TableRenderable):
    """Result type for `export_configuration` command."""

    exported: List[Path] = []
    """List of paths to exported files."""
    types: List[ExportType] = []
    names: List[str] = []
    format: ExportFormat


class ImportResult(TableRenderable):
    """Result type for `import_configuration` command."""

    success: bool = True
    dryrun: bool = False
    imported: List[Path] = []
    failed: List[Path] = []
    duration: Optional[float] = None
    """Duration it took to import files in seconds. Is None if import failed."""

    @field_serializer("imported", "failed", when_used="json")
    def _serialize_files(self, files: List[Path]) -> List[str]:
        """Serializes files as list of normalized, absolute paths with symlinks resolved."""
        return [str(f.resolve()) for f in files]

    def __cols_rows__(self) -> ColsRowsType:
        cols = ["Imported", "Failed"]  # type: List[str]
        rows = [
            [
                "\n".join(path_link(f) for f in self.imported),
                "\n".join(path_link(f) for f in self.failed),
            ]
        ]  # type: RowsType
        return cols, rows
