from __future__ import annotations

import os
from pathlib import Path


def fsync_file_descriptor(file_descriptor: int) -> None:
    os.fsync(file_descriptor)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

