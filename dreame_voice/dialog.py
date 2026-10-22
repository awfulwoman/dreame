"""Dialog scripts: dialog/<name>/sounds.csv with columns ID,Filename,Text."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Line:
    id: str
    text: str


def dialog_path(root: Path, name: str) -> Path:
    return root / "dialog" / name / "sounds.csv"


def load_dialog(root: Path, name: str) -> list[Line]:
    path = dialog_path(root, name)
    if not path.exists():
        raise FileNotFoundError(f"No dialog script at dialog/{name}/sounds.csv")
    with path.open(newline="") as f:
        return [Line(id=row["ID"].strip(), text=row["Text"].strip()) for row in csv.DictReader(f)]
