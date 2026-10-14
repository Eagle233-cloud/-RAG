from pathlib import Path

import pytest

from app.documents import parse_file, split_text
from app.errors import UnsupportedFormatError


def test_split_text_has_overlap():
    chunks = split_text("a" * 120, 50, 10)
    assert len(chunks) >= 3
    assert chunks[0][-10:] in chunks[1]


def test_parse_text_file(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("hello local rag", encoding="utf-8")
    parsed = parse_file(path, 100, 10)
    assert parsed.filename == "notes.txt"
    assert parsed.chunks == ["hello local rag"]


def test_unsupported_format(tmp_path: Path):
    path = tmp_path / "image.png"
    path.write_bytes(b"not a document")
    with pytest.raises(UnsupportedFormatError):
        parse_file(path, 100, 10)

