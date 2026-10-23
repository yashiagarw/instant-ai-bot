"""Paths and schema files the importer reads (data/schema/*.yaml)."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIR = REPO_ROOT / "data" / "schema"
REVIEW_DIR = REPO_ROOT / "data" / "review"
MEDIA_DIR = REPO_ROOT / "data" / "media"

# Bump when parsing rules change, so the dataset checksum changes too.
IMPORTER_VERSION = "1.0.1"


def normalise_header(text: object) -> str:
    """Upper-case, drop currency marks, collapse spaces and spacing around punctuation."""
    s = str(text or "").upper().replace("₹", " ").replace("\n", " ")
    s = re.sub(r"\bRS\.?\b", " ", s)
    s = re.sub(r"\s*([()/\-:,?])\s*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class FileEntry:
    file_no: int
    path: Path
    main_sheet: str
    header_row: int
    split_by: str  # category_column | id_prefix
    categories: dict[str, str]  # ID prefix -> category code


@dataclass
class AliasMap:
    exact: dict[str, str]
    prefixes: dict[str, str]
    visibility: dict[str, str]

    def field_for(self, header: object) -> str | None:
        norm = normalise_header(header)
        if norm in self.exact:
            return self.exact[norm]
        for prefix, name in self.prefixes.items():
            if norm.startswith(prefix):
                return name
        return None


@dataclass
class ImportConfig:
    files: dict[int, FileEntry]
    aliases: AliasMap
    taxonomy: dict
    rules: dict
    schema_files: list[Path] = field(default_factory=list)
    review_dir: Path = REVIEW_DIR
    media_dir: Path = MEDIA_DIR

    def entry_for_path(self, path: Path) -> FileEntry:
        resolved = path.resolve()
        for entry in self.files.values():
            if entry.path.resolve() == resolved:
                return entry
        raise SystemExit(f"{path} is not listed in data/schema/manifest.yaml")

    def schema_checksum(self) -> str:
        h = hashlib.sha256(IMPORTER_VERSION.encode())
        for p in self.schema_files:
            h.update(p.read_bytes())
        return h.hexdigest()


def load_alias_map(path: Path) -> AliasMap:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    exact, visibility = {}, {}
    for col in spec["template_columns"] + spec["ev_extra_columns"]:
        visibility[col["field"]] = col["visibility"]
        for alias in col["aliases"]:
            exact[normalise_header(alias)] = col["field"]
    prefixes = {normalise_header(p): f for f, p in (spec.get("prefix_aliases") or {}).items()}
    return AliasMap(exact, prefixes, visibility)


def load_config(schema_dir: Path = SCHEMA_DIR, repo_root: Path = REPO_ROOT) -> ImportConfig:
    manifest_path = schema_dir / "manifest.yaml"
    files = {}
    for f in yaml.safe_load(manifest_path.read_text(encoding="utf-8"))["files"]:
        files[f["file_no"]] = FileEntry(
            file_no=f["file_no"],
            path=repo_root / f["path"],
            main_sheet=f["main_sheet"],
            header_row=f["header_row"],
            split_by=f["split_by"],
            categories=f["categories"],
        )
    schema_files = [manifest_path] + [
        schema_dir / n for n in ("column_aliases.yaml", "taxonomy.yaml", "import_rules.yaml")
    ]
    return ImportConfig(
        files=files,
        aliases=load_alias_map(schema_dir / "column_aliases.yaml"),
        taxonomy=yaml.safe_load((schema_dir / "taxonomy.yaml").read_text(encoding="utf-8")),
        rules=yaml.safe_load((schema_dir / "import_rules.yaml").read_text(encoding="utf-8")),
        schema_files=schema_files,
    )
