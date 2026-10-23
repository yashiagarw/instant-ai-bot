"""Read one workbook into plain Python structures: main-sheet fault rows, extra sheets as tables,
and embedded images with their anchor cells. The file is opened read-only and never saved."""

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
from PIL import Image as PILImage

from app.knowledge.importer.config import AliasMap, normalise_header
from app.knowledge.importer.parse import clean


@dataclass
class EmbeddedImage:
    row: int  # 1-based anchor row
    col: int
    data: bytes
    ext: str
    width: int | None
    height: int | None

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.data).hexdigest()


@dataclass
class FaultRow:
    row: int
    source_id: str
    values: dict[str, object]  # canonical field -> cell value


@dataclass
class MainSheet:
    title: str
    header_row: int
    columns: dict[str, int]  # canonical field -> 1-based column
    unmapped_headers: list[str]
    rows: list[FaultRow]
    rows_without_id: list[int]
    images: list[EmbeddedImage]


@dataclass
class SheetTable:
    title: str
    header_row: int | None
    headers: list[str]
    rows: list[dict[str, object]]  # header -> value
    row_numbers: list[int]
    hyperlinks: dict[tuple[int, str], str] = field(default_factory=dict)  # (row, header) -> url
    images: list[EmbeddedImage] = field(default_factory=list)
    all_text: list[tuple[int, int, str]] = field(default_factory=list)  # (row, col, text) for gallery sheets


@dataclass
class Workbook:
    path: Path
    sha256: str
    main: MainSheet
    extras: dict[str, SheetTable]


def _anchor(img) -> tuple[int, int]:
    if isinstance(img.anchor, str):
        col, row = coordinate_from_string(img.anchor)
        return row, column_index_from_string(col)
    frm = img.anchor._from
    return frm.row + 1, frm.col + 1


def _images(ws) -> list[EmbeddedImage]:
    out = []
    for img in ws._images:
        data = img._data()
        row, col = _anchor(img)
        try:
            pil = PILImage.open(io.BytesIO(data))
            ext, size = (pil.format or "png").lower(), pil.size
        except Exception:
            ext, size = (getattr(img, "format", None) or "png").lower(), (None, None)
        out.append(EmbeddedImage(row, col, data, "jpg" if ext == "jpeg" else ext, size[0], size[1]))
    return out


def find_header_row(ws, max_scan: int = 8) -> int | None:
    """1-based row whose cells include 'CATEGORY' and an ID column."""
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1):
        norms = {normalise_header(v) for v in row if v is not None}
        if "CATEGORY" in norms and any(n.startswith("ID") for n in norms):
            return r
    return None


def find_table_header(ws, max_scan: int = 8) -> int | None:
    """Header row of an extra sheet: the first row about as wide as the widest early row."""
    widths = [
        (r, sum(clean(v) != "" for v in row))
        for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1)
    ]
    widest = max((w for _, w in widths), default=0)
    if widest < 2:
        return None
    return next((r for r, w in widths if w >= max(2, 0.8 * widest)), None)


def read_main_sheet(ws, aliases: AliasMap) -> MainSheet:
    header_row = find_header_row(ws)
    if header_row is None:
        raise ValueError(f"{ws.title}: header row with CATEGORY and ID'S not found in the first 8 rows")
    columns, unmapped = {}, []
    for idx, cell in enumerate(ws[header_row], 1):
        if clean(cell.value) == "":
            continue
        name = aliases.field_for(cell.value)
        if name is None:
            unmapped.append(clean(cell.value))
        else:
            columns.setdefault(name, idx)

    rows, without_id = [], []
    for r in range(header_row + 1, ws.max_row + 1):
        values = {name: ws.cell(r, c).value for name, c in columns.items()}
        if all(clean(v) == "" for v in values.values()):
            continue
        sid = clean(values.get("source_id"))
        if not sid:
            without_id.append(r)
            continue
        rows.append(FaultRow(r, sid, values))
    return MainSheet(ws.title, header_row, columns, unmapped, rows, without_id, _images(ws))


def read_table(ws) -> SheetTable:
    header_row = find_table_header(ws)
    all_text = [(c.row, c.column, clean(c.value)) for row in ws.iter_rows() for c in row if clean(c.value)]
    if header_row is None:
        return SheetTable(ws.title, None, [], [], [], images=_images(ws), all_text=all_text)
    headers = [clean(c.value) for c in ws[header_row]]
    rows, numbers, links = [], [], {}
    for r in range(header_row + 1, ws.max_row + 1):
        cells = [ws.cell(r, c + 1) for c in range(len(headers))]
        if all(clean(c.value) == "" for c in cells):
            continue
        record = {h: c.value for h, c in zip(headers, cells, strict=True) if h}
        for h, c in zip(headers, cells, strict=True):
            if h and c.hyperlink is not None and c.hyperlink.target:
                links[(r, h)] = c.hyperlink.target
        rows.append(record)
        numbers.append(r)
    return SheetTable(ws.title, header_row, headers, rows, numbers, links, _images(ws), all_text)


def read_workbook(path: Path, aliases: AliasMap) -> Workbook:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    wb = openpyxl.load_workbook(path, data_only=True)  # cached formula values; never saved
    main = read_main_sheet(wb.worksheets[0], aliases)
    extras = {ws.title.strip(): read_table(ws) for ws in wb.worksheets[1:]}
    return Workbook(path, sha, main, extras)
