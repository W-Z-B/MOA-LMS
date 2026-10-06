"""Reading zip files people upload without being overwhelmed by them (ASVS 12.1.2: zip bombs).

Every place that opens an uploaded zip goes through these checks before it unpacks anything: Word and
PowerPoint files read for AI drafting (assist.services) and for the similarity check (similarity.extract),
question packages (quizzes.formats), SCORM and H5P packages, Common Cartridges and older Moodle backups
(packages.archive, which the importers use), and the Office check at upload (core.uploads, which only lists
names).

- At most `max_entries` entries, and at most `max_bytes` once unpacked, by the sizes the zip declares;
- no entry above 1 MB unpacked may be more than MAX_RATIO times its packed size;
- no encrypted entry, and only the two usual kinds of compression;
- an entry is read through zipfile, which never gives more than the size it declared and checks the
  checksum, and never more than the caller's limit.

XML inside is refused if it declares a document type or entities (quizzes.formats.refuse_unsafe_xml):
Office files, manifests and question files never need them, and an entity can expand without limit.
"""

import zipfile

MB = 1024 * 1024
MAX_RATIO = 100  # an entry above 1 MB unpacked may not be more than 100 times its packed size
COMPRESSIONS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)


class ArchiveRefused(ValueError):
    """The zip is not read; the message says why, in plain words."""


def open_zip(upload) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(upload)
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as error:
        raise ArchiveRefused("The file is not a complete zip file; save or export it again.") from error


def too_compressed(info: zipfile.ZipInfo) -> bool:
    return info.file_size > MB and info.file_size > MAX_RATIO * max(info.compress_size, 1)


def checked(archive: zipfile.ZipFile, *, max_entries: int, max_bytes: int) -> list[zipfile.ZipInfo]:
    """The archive's entries once the limits are met; ArchiveRefused otherwise. Nothing is unpacked."""
    infos = archive.infolist()
    if len(infos) > max_entries:
        raise ArchiveRefused(f"The file holds more than {max_entries} parts.")
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise ArchiveRefused("The file is protected by a password; save it without one.")
        if info.is_dir():
            continue
        if info.compress_type not in COMPRESSIONS:
            raise ArchiveRefused("The file uses a kind of compression the LMS does not read; save it again.")
        if too_compressed(info):
            raise ArchiveRefused("The file unpacks to far more than its size, so it was refused.")
        total += info.file_size
        if total > max_bytes:
            raise ArchiveRefused(f"The file unpacks to more than {max_bytes // MB} MB, so it was refused.")
    return infos


def read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    """An entry's bytes, refused when it is larger than `limit` (zipfile stops at the size it declares)."""
    if info.file_size > limit:
        raise ArchiveRefused(f"{info.filename[:80]} is too large to read.")
    try:
        with archive.open(info) as handle:
            data = handle.read(limit + 1)
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as error:
        raise ArchiveRefused(f"{info.filename[:80]} is damaged in the file.") from error
    if len(data) > limit:  # pragma: no cover - zipfile never returns more than the declared size
        raise ArchiveRefused(f"{info.filename[:80]} is too large to read.")
    return data


def xml_text(data: bytes, what: str) -> str:
    """XML from an archive as text, refusing a document type or entity declaration."""
    from quizzes.formats import FormatError, refuse_unsafe_xml

    text = data.decode("utf-8-sig", "ignore")
    try:
        refuse_unsafe_xml(text)
    except FormatError as error:
        raise ArchiveRefused(
            f"{what} declares a document type or entities, which are not accepted."
        ) from error
    return text
