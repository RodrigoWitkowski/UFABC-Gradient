import hashlib
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PreservedFile:
    path: Path
    sha256: str
    size_bytes: int


class ImportStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def incoming_path(self, original_filename: str) -> Path:
        suffix = Path(original_filename).suffix.casefold()
        incoming = self.root / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        return incoming / f"{uuid.uuid4()}{suffix}"

    def preserve(self, source_path: Path) -> PreservedFile:
        digest = hashlib.sha256()
        size = 0
        with source_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        sha256 = digest.hexdigest()
        destination = self.root / sha256[:2] / f"{sha256}{source_path.suffix.casefold()}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source_path, destination)
        return PreservedFile(destination, sha256, size)
