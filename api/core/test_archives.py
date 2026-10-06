"""Uploaded zips are checked before anything is unpacked (core.archives; ASVS 12.1.2): a crafted zip bomb,
too many parts, and XML that declares entities are refused wherever the LMS opens a zip."""

import io
import zipfile
from types import SimpleNamespace

import pytest

from core import archives

CONTENT_TYPES = (
    b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
)


def office(parts: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as made:
        made.writestr("[Content_Types].xml", CONTENT_TYPES)
        for name, data in parts.items():
            made.writestr(name, data)
    return buffer.getvalue()


def bomb() -> bytes:
    """A Word file of about 60 KB whose text part unpacks to 64 MB."""
    body = (
        b"<w:document><w:body><w:p><w:t>" + b"A" * (64 * archives.MB) + b"</w:t></w:p></w:body></w:document>"
    )
    return office({"word/document.xml": body})


def stored(data: bytes):
    return SimpleNamespace(file=SimpleNamespace(open=lambda mode="rb": io.BytesIO(data)))


def test_a_zip_bomb_is_refused_before_it_is_unpacked():
    data = bomb()
    assert len(data) < 200_000
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        pytest.raises(archives.ArchiveRefused, match="far more"),
    ):
        archives.checked(archive, max_entries=10, max_bytes=500 * archives.MB)


def test_ai_drafting_refuses_a_word_bomb_and_reads_a_real_file():
    from assist import services

    with pytest.raises(archives.ArchiveRefused, match="far more"):
        services._office_text(stored(bomb()))
    words = office({"word/document.xml": b"<w:document><w:p><w:t>Soil &amp; water</w:t></w:p></w:document>"})
    assert services._office_text(stored(words)) == "Soil & water"


def test_ai_drafting_refuses_too_many_parts_too_much_and_declared_entities(monkeypatch):
    from assist import services

    many = office({f"ppt/slides/slide{n}.xml": b"<p/>" for n in range(services.OFFICE_MAX_PARTS + 1)})
    with pytest.raises(archives.ArchiveRefused, match="more than"):
        services._office_text(stored(many))
    monkeypatch.setattr(services, "OFFICE_MAX_BYTES", 1000)
    with pytest.raises(archives.ArchiveRefused, match="unpacks to more than"):
        services._office_text(stored(office({"word/document.xml": b"<w:t>" + b"x" * 2000 + b"</w:t>"})))
    monkeypatch.undo()
    laughs = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><w:document>&a;</w:document>'
    with pytest.raises(archives.ArchiveRefused, match="entities"):
        services._office_text(stored(office({"word/document.xml": laughs})))


def test_each_part_is_read_no_further_than_the_limit(monkeypatch):
    from assist import services

    monkeypatch.setattr(services, "OFFICE_PART_BYTES", 40)
    words = office({"word/document.xml": b"<w:t>" + b"word " * 100 + b"</w:t>"})
    assert len(services._office_text(stored(words))) <= 40


def test_question_packages_refuse_a_zip_bomb():
    from quizzes.formats import FormatError, _zip_documents

    with pytest.raises(FormatError, match="far more"):
        _zip_documents(bomb())


def test_packages_cartridges_and_moodle_backups_refuse_a_zip_bomb(settings):
    """SCORM and H5P packages, and the importers' zips (interchange.common.ZipSource), share these checks."""
    from interchange.common import ImportRefused, ZipSource
    from packages.archive import PackageRefused, entries

    with zipfile.ZipFile(io.BytesIO(bomb())) as archive, pytest.raises(PackageRefused, match="far more"):
        entries(archive)
    with pytest.raises(ImportRefused, match="far more"):
        ZipSource(io.BytesIO(bomb()))


def test_reading_an_entry_is_capped_and_damage_is_refused():
    data = office({"word/document.xml": b"x" * 5000})
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("word/document.xml")
        with pytest.raises(archives.ArchiveRefused, match="too large"):
            archives.read(archive, info, limit=100)
        assert archives.read(archive, info, limit=5000) == b"x" * 5000
    with pytest.raises(archives.ArchiveRefused, match="not a complete zip"):
        archives.open_zip(io.BytesIO(b"PK\x03\x04 not really"))


def test_encrypted_and_oddly_compressed_entries_are_refused():
    data = bytearray(office({"word/document.xml": b"<w:t>x</w:t>"}))
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as archive:
        archive.infolist()[1].flag_bits |= 0x1
        with pytest.raises(archives.ArchiveRefused, match="password"):
            archives.checked(archive, max_entries=10, max_bytes=archives.MB)
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as archive:
        archive.infolist()[1].compress_type = zipfile.ZIP_LZMA
        with pytest.raises(archives.ArchiveRefused, match="compression"):
            archives.checked(archive, max_entries=10, max_bytes=archives.MB)
