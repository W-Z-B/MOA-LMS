"""Checking an uploaded package before it is kept, and reading entries from it afterwards (items 5.12, 5.13).

A package is a zip file: a SCORM 1.2 or 2004 package (imsmanifest.xml at its root) or an H5P file (h5p.json
at its root). It is never unpacked onto the disk. The zip is kept as the content item's file, and each entry
is read from it when the player asks for it, so only names that are in the package can ever be served.

Before a package is accepted:
- it must be a zip file no larger than UPLOAD_LIMIT_PACKAGE_MB, within the course's storage allowance;
- it may hold at most PACKAGE_MAX_ENTRIES entries and PACKAGE_MAX_UNPACKED_MB once unpacked, and no entry
  may be compressed more than MAX_RATIO times over (zip bombs);
- every name must be a plain relative path: no folder above the package ("../"), no drive or leading "/",
  no backslashes, no control characters, no links and no encrypted entries;
- no entry may be a program for a computer rather than a web page (.exe, .bat, .php and the like);
- every entry must unpack to exactly the size and checksum it declares;
- the manifest must be well formed and declare no document type or entities (quizzes.formats).
"""

import json
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass, field

from django.conf import settings

from core.archives import too_compressed  # the zip-bomb rule every uploaded zip meets
from quizzes.formats import FormatError, parse_xml

MB = 1024 * 1024

RESERVED = "__lms__"  # the player's own addresses live under this name; a package may not use it
REFUSED_EXTENSIONS = frozenset(
    {
        ".exe", ".dll", ".com", ".bat", ".cmd", ".msi", ".scr", ".ps1", ".vbs", ".sh", ".php", ".phtml",
        ".asp", ".aspx", ".jsp", ".cgi", ".pl", ".py", ".jar", ".apk", ".dmg", ".app", ".lnk",
    }
)  # fmt: skip
_BAD_NAME = re.compile(r"[\x00-\x1f\x7f\\]|^[A-Za-z]:")


class PackageRefused(ValueError):
    """The upload is not a package the LMS will keep; the message says why, in plain words."""


@dataclass
class Sco:
    """Something the learner launches: a SCORM SCO, or the H5P content as a whole."""

    id: str
    title: str
    href: str  # the entry inside the package, without any query
    parameters: str = ""  # a query string the manifest adds to the launch address

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "href": self.href, "parameters": self.parameters}


@dataclass
class Checked:
    standard: str  # scorm12, scorm2004 or h5p
    title: str
    version_label: str
    scos: list[Sco] = field(default_factory=list)
    entries: int = 0
    unpacked_bytes: int = 0


def clean_name(name: str) -> str | None:
    """The entry name as served, or None when it is not a plain relative path inside the package."""
    if not name or _BAD_NAME.search(name) or name.startswith("/"):
        return None
    parts = name.split("/")
    if parts and parts[-1] == "":
        parts = parts[:-1]  # a folder
    if any(part in ("", ".", "..") for part in parts):
        return None
    return "/".join(parts)


def _is_link(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode) if mode else False


def entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    """Every file in the package by its served name. Raises PackageRefused for anything unsafe."""
    limit_entries = settings.PACKAGE_MAX_ENTRIES
    limit_bytes = settings.PACKAGE_MAX_UNPACKED_MB * MB
    infos = archive.infolist()
    if len(infos) > limit_entries:
        raise PackageRefused(f"The package holds more than {limit_entries} files.")
    found: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        name = clean_name(info.filename)
        if name is None:
            raise PackageRefused(f"The package holds a file with an unsafe name ({info.filename[:80]!r}).")
        if info.flag_bits & 0x1:
            raise PackageRefused("The package is protected by a password; save it without one.")
        if _is_link(info):
            raise PackageRefused(f"The package holds a link ({name[:80]}), which is not accepted.")
        if info.is_dir():
            continue
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise PackageRefused(
                "The package uses a kind of compression the LMS does not read; zip it again."
            )
        if name.split("/")[0] == RESERVED:
            raise PackageRefused(f"The package uses the name {RESERVED}, which the LMS keeps for itself.")
        if posixpath.splitext(name)[1].lower() in REFUSED_EXTENSIONS:
            raise PackageRefused(f"The package holds a program ({name[:80]}), which is not accepted.")
        if name in found or name.lower() in {n.lower() for n in found}:
            raise PackageRefused(f"The package holds two files named {name[:80]}.")
        if too_compressed(info):
            raise PackageRefused("The package unpacks to far more than its size, so it was refused.")
        total += info.file_size
        if total > limit_bytes:
            raise PackageRefused(
                f"The package unpacks to more than {settings.PACKAGE_MAX_UNPACKED_MB} MB, so it was refused."
            )
        found[name] = info
    return found


def open_zip(upload) -> zipfile.ZipFile:
    upload.seek(0)
    head = upload.read(4)
    upload.seek(0)
    if head != b"PK\x03\x04":
        raise PackageRefused("Send a SCORM package (.zip) or an H5P file (.h5p).")
    try:
        return zipfile.ZipFile(upload)
    except (zipfile.BadZipFile, OSError, ValueError) as error:
        raise PackageRefused("The package is not a complete zip file; export it again.") from error


def read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int | None = None) -> bytes:
    """An entry's bytes, never more than it declares (zipfile checks the size and checksum as it reads)."""
    if limit is not None and info.file_size > limit:
        raise PackageRefused(f"{info.filename[:80]} is too large to read.")
    try:
        with archive.open(info) as handle:
            return handle.read(info.file_size + 1)[: info.file_size + 1]
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as error:
        raise PackageRefused(f"{info.filename[:80]} is damaged in the package; export it again.") from error


def _verify(archive: zipfile.ZipFile, found: dict[str, zipfile.ZipInfo]) -> None:
    for info in found.values():
        data = read(archive, info)
        if len(data) != info.file_size:
            raise PackageRefused(f"{info.filename[:80]} is damaged in the package; export it again.")


def check(upload) -> Checked:
    """Check an uploaded package and say what it is. Raises PackageRefused with the reason."""
    limit = settings.UPLOAD_LIMIT_PACKAGE_MB
    if upload.size > limit * MB:
        raise PackageRefused(f"The package is larger than {limit} MB.")
    with open_zip(upload) as archive:
        found = entries(archive)
        if "imsmanifest.xml" in found:
            checked = _scorm(archive, found)
        elif "h5p.json" in found:
            checked = _h5p(archive, found)
        else:
            raise PackageRefused(
                "This is not a SCORM package or an H5P file: it has no imsmanifest.xml or h5p.json at its "
                "top."
            )
        _verify(archive, found)
        checked.entries = len(found)
        checked.unpacked_bytes = sum(info.file_size for info in found.values())
    upload.seek(0)
    return checked


# ---------------------------------------------------------------------------------------------------------
# SCORM


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element, name: str):
    return [child for child in element if _local(child.tag) == name]


def _child(element, name: str):
    found = _children(element, name)
    return found[0] if found else None


def _attr(element, name: str) -> str:
    """An attribute by its local name, whatever namespace it is written in (adlcp:scormtype, xml:base)."""
    for key, value in element.attrib.items():
        if _local(key).lower() == name.lower():
            return value
    return ""


def _text_of(element) -> str:
    return "".join(element.itertext()).strip() if element is not None else ""


def _version(root, text: str) -> tuple[str, str]:
    metadata = _child(root, "metadata")
    version = _text_of(_child(metadata, "schemaversion")) if metadata is not None else ""
    if version == "1.2":
        return "scorm12", "SCORM 1.2"
    if "2004" in version or version.startswith("CAM 1.3"):
        return "scorm2004", f"SCORM {version}"
    if "adlcp_v1p3" in text or "adlseq" in text:
        return "scorm2004", "SCORM 2004"
    if "adlcp_rootv1p2" in text:
        return "scorm12", "SCORM 1.2"
    raise PackageRefused("The manifest does not say which SCORM version it is (1.2 or 2004).")


def _scorm(archive, found) -> Checked:
    raw = read(archive, found["imsmanifest.xml"], limit=5 * MB)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PackageRefused("The manifest is not saved as UTF-8 text.") from error
    try:
        root = parse_xml(text)
    except FormatError as error:
        raise PackageRefused(f"The manifest cannot be read: {error}") from error
    if _local(root.tag) != "manifest":
        raise PackageRefused("imsmanifest.xml is not a content package manifest.")
    standard, label = _version(root, text)
    resources_el = _child(root, "resources")
    base = (
        posixpath.join(_attr(root, "base"), _attr(resources_el, "base")) if resources_el is not None else ""
    )
    resources = {}
    for resource in _children(resources_el, "resource") if resources_el is not None else []:
        href = _attr(resource, "href")
        if href:
            resources[_attr(resource, "identifier")] = (
                resource,
                posixpath.join(base, _attr(resource, "base"), href),
            )
    organizations = _child(root, "organizations")
    organization = None
    if organizations is not None:
        orgs = _children(organizations, "organization")
        default = _attr(organizations, "default")
        organization = next((o for o in orgs if _attr(o, "identifier") == default), orgs[0] if orgs else None)
    title = _text_of(_child(organization, "title")) if organization is not None else ""
    scos: list[Sco] = []
    for item in organization.iter() if organization is not None else []:
        if _local(item.tag) != "item" or not _attr(item, "identifierref"):
            continue
        if _attr(item, "isvisible").lower() == "false":
            continue
        resource = resources.get(_attr(item, "identifierref"))
        if resource is None:
            continue
        href, _, query = resource[1].partition("?")
        parameters = _attr(item, "parameters").lstrip("?&")
        if query:
            parameters = f"{query}&{parameters}" if parameters else query
        name = clean_name(posixpath.normpath(href))
        if name is None or name not in found:
            raise PackageRefused(
                f"The manifest starts the course at {href[:80]}, which is not in the package."
            )
        sco_title = _text_of(_child(item, "title")) or title or "Course"
        scos.append(
            Sco(_attr(item, "identifier")[:100] or f"sco{len(scos) + 1}", sco_title[:200], name, parameters)
        )
    if not scos:
        raise PackageRefused("The manifest names nothing to open: no item points to a page in the package.")
    if len(scos) > 200:
        raise PackageRefused("The package has more than 200 parts to open.")
    return Checked(standard, (title or scos[0].title)[:200], label, scos)


# ---------------------------------------------------------------------------------------------------------
# H5P


def _h5p(archive, found) -> Checked:
    try:
        meta = json.loads(read(archive, found["h5p.json"], limit=MB).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageRefused("h5p.json cannot be read.") from error
    if not isinstance(meta, dict) or not isinstance(meta.get("mainLibrary"), str):
        raise PackageRefused("h5p.json does not name the H5P content type it uses.")
    if "content/content.json" not in found:
        raise PackageRefused("The H5P file has no content (content/content.json is missing).")
    dependencies = meta.get("preloadedDependencies") or []
    if not isinstance(dependencies, list):
        raise PackageRefused("h5p.json lists its libraries wrongly.")
    main_version = ""
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise PackageRefused("h5p.json lists its libraries wrongly.")
        machine = str(dependency.get("machineName", ""))
        folder = f"{machine}-{dependency.get('majorVersion')}.{dependency.get('minorVersion')}"
        if f"{folder}/library.json" not in found:
            raise PackageRefused(
                f"The H5P file does not include the library {folder}. Export it again from the H5P editor "
                "with its libraries included."
            )
        if machine == meta["mainLibrary"]:
            main_version = f" {dependency.get('majorVersion')}.{dependency.get('minorVersion')}"
    title = str(meta.get("title") or "H5P content")[:200]
    return Checked("h5p", title, f"H5P {meta['mainLibrary']}{main_version}"[:80], [Sco("h5p", title, "")])
