#!/usr/bin/env python3
"""Safe Course2Web processor for local and EC2 execution.

Remote invariants:
- Google Drive is read through a local mounted directory or `rclone copyto`.
- S3 is read with get/head operations and written with explicit single-object cp.
- No remote delete, move, purge, or mirroring operation is implemented.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


SHEET_KEY = "0AkWmZX8HtwWHdENUNFcxdG9XdzBTaWhlVkZ0RU1QcXc"
SHEET_GIDS = [
    1218728177,
    1233971849,
    1019442815,
    1559662669,
    1501128082,
    827677169,
    469482974,
    6,
    4,
    3,
    2,
    0,
    1,
]
DEFAULT_ACTIVE_SERIES = [
    "daily_homilies",
    "misc",
    "st_joseph_novena",
    "magnificat_humanitas",
]
GENERATED_FIELDS = ("duration", "length", "link2mp3")
MUTABLE_CACHE_CONTROL = "max-age=300, must-revalidate"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
NY_TZ = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


class PipelineError(RuntimeError):
    pass


@dataclass
class Upload:
    local_path: Path
    key: str
    content_type: str
    cache_control: str
    changed: bool
    remote_exists: bool
    reason: str
    sha256: str
    size: int

    def as_json(self) -> dict[str, Any]:
        return {
            "localPath": str(self.local_path),
            "key": self.key,
            "contentType": self.content_type,
            "cacheControl": self.cache_control,
            "changed": self.changed,
            "remoteExists": self.remote_exists,
            "reason": self.reason,
            "sha256": self.sha256,
            "size": self.size,
        }


def log(message: str) -> None:
    print(message, flush=True)


def run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    assert_safe_command(command)
    log("+ " + " ".join(shell_display(part) for part in command))
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def shell_display(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=,@+-]+", value):
        return value
    return repr(value)


def assert_safe_command(command: Iterable[str]) -> None:
    parts = list(command)
    if not parts:
        raise PipelineError("empty external command")
    lowered = [part.lower() for part in parts]
    forbidden = {
        "--delete",
        "delete",
        "delete-object",
        "delete-objects",
        "rm",
        "mv",
        "move",
        "moveto",
        "purge",
        "cleanup",
        "rmdirs",
        "sync",
    }
    for part in lowered:
        if part in forbidden or part.startswith("--delete-"):
            raise PipelineError(f"forbidden deletion/move command token: {part}")

    executable = Path(parts[0]).name
    if executable == "rclone" and (len(parts) < 2 or parts[1] not in {"copyto", "version"}):
        raise PipelineError("rclone is restricted to copyto/version")
    if executable == "aws":
        allowed = (
            len(parts) >= 3
            and (
                (parts[1] == "s3" and parts[2] == "cp")
                or (parts[1] == "s3api" and parts[2] in {"get-object", "head-object"})
                or (parts[1] == "cloudfront" and parts[2] == "create-invalidation")
                or (parts[1] == "sts" and parts[2] == "get-caller-identity")
            )
        )
        if not allowed:
            raise PipelineError(f"AWS command is not allowlisted: {' '.join(parts[:3])}")


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    value = value.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise PipelineError(f"unsupported date value: {value}")


def updated_on_json(value: str) -> str:
    parsed: dt.datetime | None = None
    for pattern in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(value, pattern).replace(tzinfo=NY_TZ)
            break
        except ValueError:
            pass
    if parsed is None:
        raise PipelineError(f"unsupported updated_on value: {value}")
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+0000")


def rss_date(value: dt.date) -> str:
    local_midnight = dt.datetime.combine(value, dt.time.min, tzinfo=NY_TZ)
    return local_midnight.strftime("%a, %-d %b %Y %H:%M:%S %z")


def add_csv_value(target: dict[str, Any], key: str, value: str) -> None:
    if not key or not value:
        return
    if key not in target:
        target[key] = value
    elif isinstance(target[key], list):
        target[key].append(value)
    else:
        target[key] = [target[key], value]


def parse_sheet_csv(text: str, gid: int) -> dict[str, Any]:
    rows = list(csv.reader(text.splitlines()))
    if len(rows) < 3:
        raise PipelineError(f"sheet gid {gid} has fewer than three header rows")

    series_data: dict[str, Any] = {}
    for key, value in zip(rows[0], rows[1]):
        add_csv_value(series_data, key.strip(), value.strip())
    name = series_data.get("normalized_name")
    if not isinstance(name, str) or not name:
        raise PipelineError(f"sheet gid {gid} has no normalized_name")

    headers = [header.strip() for header in rows[2]]
    classes: list[dict[str, Any]] = []
    for csv_row in rows[3:]:
        row: dict[str, Any] = {}
        for key, value in zip(headers, csv_row):
            add_csv_value(row, key, value.strip())
        if not row:
            continue
        normalize_class(row, name)
        classes.append(row)

    if str(series_data.get("reverse_order", "")).upper() == "TRUE":
        classes.reverse()
    return {"seriesData": series_data, "classes": classes, "gid": gid}


def normalize_class(row: dict[str, Any], series_name: str) -> None:
    class_id = row.get("id")
    if isinstance(class_id, str) and len(class_id) == 1:
        row["id"] = "0" + class_id

    class_date = parse_date(string_value(row.get("date")))
    if class_date:
        row["rssDate"] = rss_date(class_date)
        row["dateId"] = class_date.strftime("%Y%m%d")

    updated = string_value(row.get("updated_on"))
    if updated:
        row["updated_on_date"] = updated_on_json(updated)

    audio = string_value(row.get("audio"))
    if not row.get("id") and class_date:
        row["id"] = row["dateId"]
    elif not row.get("id") and audio and re.match(r"^20\d\d-\d\d-\d\d", audio):
        derived = parse_date(audio[:10])
        if derived:
            row["id"] = derived.strftime("%Y%m%d")
            row["date"] = derived.strftime("%m/%d/%Y")
            row["rssDate"] = rss_date(derived)
            row["dateId"] = derived.strftime("%Y%m%d")

    if not row.get("title") and row.get("liturgical_day"):
        liturgical = row["liturgical_day"]
        row["title"] = " / ".join(liturgical) if isinstance(liturgical, list) else liturgical

    if audio and row.get("id"):
        row["newAudio"] = f"{row['id']}-{series_name}.mp3"
    if audio and not row.get("volume_boost"):
        row["volume_boost"] = "2"

    handouts = list_value(row.get("handout_file"))
    titles = list_value(row.get("handout_title"))
    if handouts:
        row["handout_file"] = handouts
        row["handout_title"] = titles
        row["new_handout_title"] = titles
        row["new_handout_file"] = [
            new_handout_name(row.get("id"), titles[index] if index < len(titles) else "document", source)
            for index, source in enumerate(handouts)
        ]


def new_handout_name(class_id: Any, title: str, source: str) -> str:
    if source.startswith(("http://", "https://")):
        return source
    suffix = Path(urllib.parse.unquote(source)).suffix.lstrip(".")
    safe_title = title.replace(" ", "_")
    return f"{class_id}-{safe_title}.{suffix}" if suffix else f"{class_id}-{safe_title}"


def string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def effective_date(row: dict[str, Any]) -> dt.date | None:
    values = [
        parse_date(string_value(row.get("date"))),
        parse_date(string_value(row.get("updated_on"))),
    ]
    present = [value for value in values if value is not None]
    return max(present) if present else None


def is_eligible(row: dict[str, Any], cutoff: dt.date) -> bool:
    value = effective_date(row)
    return value is not None and value >= cutoff


def stable_key(row: dict[str, Any]) -> str:
    row_id = string_value(row.get("id"))
    audio = string_value(row.get("audio"))
    # The legacy processor sometimes replaced a missing ID with the local
    # orig/... path after deriving newAudio. Match those snapshots by source
    # audio so the row is preserved rather than duplicated.
    if row_id and row_id.startswith("orig/") and audio:
        return f"audio:{audio}"
    for key in ("id", "dateId", "audio"):
        value = string_value(row.get(key))
        if value:
            return f"{key}:{value}"
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
    return f"sha256:{digest}"


def load_cp(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("cp = "):
        text = text[5:]
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise PipelineError(f"cp snapshot is not an array: {path}")
    return parsed


def write_cp(path: Path, value: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, indent=4, ensure_ascii=False)
    atomic_write_text(path, "cp = " + body)


def merge_snapshot(
    current: list[dict[str, Any]], baseline: list[dict[str, Any]], cutoff: dt.date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_series = {
        item.get("seriesData", {}).get("normalized_name"): item
        for item in baseline
        if item.get("seriesData", {}).get("normalized_name")
    }
    merged: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_series: set[str] = set()

    for current_series in current:
        series_data = copy.deepcopy(current_series["seriesData"])
        name = series_data["normalized_name"]
        seen_series.add(name)
        old_series = baseline_series.get(name, {"classes": [], "seriesData": {}})
        old_by_key: dict[str, list[dict[str, Any]]] = {}
        for old_row in old_series.get("classes", []):
            old_by_key.setdefault(stable_key(old_row), []).append(copy.deepcopy(old_row))

        merged_rows: list[dict[str, Any]] = []
        for current_row in current_series.get("classes", []):
            key = stable_key(current_row)
            candidates = old_by_key.get(key, [])
            old_row = candidates.pop(0) if candidates else None
            if is_eligible(current_row, cutoff):
                new_row = copy.deepcopy(current_row)
                if old_row:
                    for field in GENERATED_FIELDS:
                        if old_row.get(field) is not None:
                            new_row[field] = old_row[field]
                merged_rows.append(new_row)
            elif old_row:
                merged_rows.append(old_row)
            else:
                merged_rows.append(copy.deepcopy(current_row))
                warnings.append(
                    {
                        "type": "historical-row-not-in-baseline",
                        "series": name,
                        "key": key,
                    }
                )

        for remaining in old_by_key.values():
            for old_row in remaining:
                merged_rows.append(old_row)
                warnings.append(
                    {
                        "type": "baseline-row-not-in-current-sheet",
                        "series": name,
                        "key": stable_key(old_row),
                    }
                )
        merged.append({"classes": merged_rows, "seriesData": series_data})

    for name, old_series in baseline_series.items():
        if name not in seen_series:
            merged.append(copy.deepcopy(old_series))
            warnings.append({"type": "baseline-series-not-in-current-sheet", "series": name})
    return merged, warnings


def fetch_sheets(args: argparse.Namespace) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for gid in SHEET_GIDS:
        if args.sheet_fixture_dir:
            path = args.sheet_fixture_dir / f"{gid}.csv"
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
        else:
            query = urllib.parse.urlencode(
                {"key": SHEET_KEY, "output": "csv", "single": "true", "gid": str(gid)}
            )
            url = f"https://docs.google.com/spreadsheet/pub?{query}"
            log(f"GET published sheet gid={gid}")
            request = urllib.request.Request(url, headers={"User-Agent": "course2web-ec2/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8-sig")
        result.append(parse_sheet_csv(text, gid))
    if not result:
        raise PipelineError("no sheet data was loaded")
    return result


def series_map(value: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["seriesData"]["normalized_name"]: item for item in value}


def source_relative(series: str, category: str, filename: str) -> Path:
    clean = Path(urllib.parse.unquote(filename))
    if clean.is_absolute() or ".." in clean.parts:
        raise PipelineError(f"unsafe source filename: {filename}")
    return Path(series) / category / clean


def copy_input(args: argparse.Namespace, relative: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if args.input_mode == "local":
        source = args.input_root / relative
        if not source.is_file():
            raise PipelineError(f"input file not found: {source}")
        if destination.exists():
            same = source.stat().st_size == destination.stat().st_size and int(source.stat().st_mtime) == int(
                destination.stat().st_mtime
            )
            if same:
                return
        shutil.copy2(source, destination)
    elif args.input_mode == "rclone":
        remote_path = f"{args.rclone_remote}:{args.rclone_uploads_path.rstrip('/')}/{relative.as_posix()}"
        run_command(["rclone", "copyto", remote_path, str(destination), "--metadata", "--no-traverse"])
    else:
        raise PipelineError(f"unsupported input mode: {args.input_mode}")


def fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns, "sha256": sha256_file(path)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "inputs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def process_rows(
    args: argparse.Namespace,
    merged: list[dict[str, Any]],
    cutoff: dt.date,
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path], list[dict[str, Any]]]:
    generated: list[Path] = []
    events: list[dict[str, Any]] = []
    state_inputs = state.setdefault("inputs", {})

    for series in merged:
        name = series["seriesData"]["normalized_name"]
        if name not in args.active_series:
            continue
        for row in series.get("classes", []):
            if not is_eligible(row, cutoff):
                continue
            row_key = stable_key(row)
            audio = string_value(row.get("audio"))
            if audio:
                try:
                    output, was_generated = process_audio(
                        args, name, series["seriesData"], row, row_key, state_inputs
                    )
                    generated.append(output)
                    if was_generated:
                        events.append({"type": "audio-generated", "series": name, "key": row_key, "path": str(output)})
                    else:
                        events.append({"type": "audio-current", "series": name, "key": row_key})
                except PipelineError as error:
                    events.append({"type": "audio-error", "series": name, "key": row_key, "error": str(error)})

            handouts = list_value(row.get("handout_file"))
            new_handouts = list_value(row.get("new_handout_file"))
            links: list[str] = []
            for index, handout in enumerate(handouts):
                if handout.startswith(("http://", "https://")):
                    links.append(handout)
                    continue
                if index >= len(new_handouts):
                    continue
                relative = source_relative(name, "docs", handout)
                source_copy = args.work_dir / "orig" / relative
                try:
                    copy_input(args, relative, source_copy)
                except PipelineError as error:
                    events.append({"type": "document-error", "series": name, "key": row_key, "error": str(error)})
                    continue
                output = args.work_dir / "out" / name / "docs" / new_handouts[index]
                output.parent.mkdir(parents=True, exist_ok=True)
                if not output.exists() or fingerprint(output) != fingerprint(source_copy):
                    atomic_copy(source_copy, output)
                    events.append({"type": "document-generated", "series": name, "key": row_key, "path": str(output)})
                generated.append(output)
                links.append(f"/{name}/docs/{new_handouts[index]}")
            if links:
                row["handout_links"] = links
    return merged, generated, events


def process_audio(
    args: argparse.Namespace,
    series_name: str,
    series_data: dict[str, Any],
    row: dict[str, Any],
    row_key: str,
    state_inputs: dict[str, Any],
) -> tuple[Path, bool]:
    audio = string_value(row.get("audio"))
    output_name = string_value(row.get("newAudio"))
    if not audio or not output_name:
        raise PipelineError("audio row has no generated filename")

    if audio.startswith(("http://", "https://")):
        if "youtube" not in audio and "youtu.be" not in audio:
            raise PipelineError(f"unsupported remote audio URL: {audio}")
        source_copy = args.work_dir / "orig" / series_name / "audio" / output_name
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        if not source_copy.exists():
            run_command(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "-f",
                    "bestaudio",
                    "--extract-audio",
                    "--audio-format",
                    "mp3",
                    "--audio-quality",
                    "0",
                    "-o",
                    str(source_copy),
                    audio,
                ]
            )
    else:
        relative = source_relative(series_name, "audio", audio)
        source_copy = args.work_dir / "orig" / relative
        copy_input(args, relative, source_copy)

    source_fingerprint = fingerprint(source_copy)
    state_key = f"{series_name}:{row_key}:audio"
    output = args.work_dir / "out" / series_name / "audio" / output_name
    prior = state_inputs.get(state_key)
    if prior and prior.get("source") == source_fingerprint and output.exists():
        set_audio_metadata(row, output, series_name)
        return output, False

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp.mp3", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_copy),
            "-vn",
            "-af",
            f"volume={string_value(row.get('volume_boost')) or '2'}",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "256k",
            "-metadata",
            "artist=David Tedesche",
            "-metadata",
            f"album={series_name}",
            "-metadata",
            f"title={string_value(row.get('title')) or row.get('id')}",
            "-metadata",
            f"track={row.get('id')}",
            str(temporary),
        ]
        run_command(command)
        if temporary.stat().st_size == 0:
            raise PipelineError(f"ffmpeg created an empty output for {audio}")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    set_audio_metadata(row, output, series_name)
    state_inputs[state_key] = {"source": source_fingerprint, "output": fingerprint(output)}
    return output, True


def set_audio_metadata(row: dict[str, Any], output: Path, series_name: str) -> None:
    probe = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output),
        ],
        capture=True,
    )
    seconds = float(probe.stdout.strip())
    row["duration"] = format_duration(seconds)
    row["length"] = str(output.stat().st_size)
    row["link2mp3"] = f"/{series_name}/audio/{output.name}"


def format_duration(seconds: float) -> str:
    hundredths = int(round(seconds * 100))
    hours, remainder = divmod(hundredths, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def podcast_xml(series: dict[str, Any]) -> str:
    itunes = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    atom = "http://www.w3.org/2005/Atom"
    ET.register_namespace("itunes", itunes)
    ET.register_namespace("atom", atom)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    data = series["seriesData"]
    name = data["normalized_name"]
    title = string_value(data.get("title")) or name
    description = string_value(data.get("description")) or title
    add_text(channel, "title", f"CatholicPatrimony.com - {title}")
    add_text(channel, "link", "https://www.catholicpatrimony.com/")
    add_text(channel, "description", description)
    add_text(channel, "language", "en-us")
    add_text(channel, "webMaster", "dtedesche@gmail.com (David Tedesche)")
    add_text(channel, "managingEditor", "dtedesche@gmail.com (David Tedesche)")
    image = ET.SubElement(channel, "image")
    add_text(image, "url", "https://www.catholicpatrimony.com/img/restoring.jpg")
    add_text(image, "title", "Sacred Art")
    add_text(image, "link", "https://www.catholicpatrimony.com")
    add_text(channel, f"{{{itunes}}}explicit", "false")
    add_text(channel, f"{{{itunes}}}author", "Reverend David Tedesche")
    add_text(channel, f"{{{itunes}}}email", "benanderson.us@gmail.com")
    owner = ET.SubElement(channel, f"{{{itunes}}}owner")
    add_text(owner, f"{{{itunes}}}email", "benanderson.us@gmail.com")
    category = ET.SubElement(channel, f"{{{itunes}}}category", {"text": "Religion & Spirituality"})
    ET.SubElement(category, f"{{{itunes}}}category", {"text": "Christianity"})
    add_text(channel, f"{{{itunes}}}summary", description)
    ET.SubElement(
        channel,
        f"{{{atom}}}link",
        {
            "href": f"https://www.catholicpatrimony.com/{name}/podcast.xml",
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    for index, row in enumerate(series.get("classes", []), start=1):
        if index > 50:
            break
        if not row.get("audio") or not all(row.get(field) for field in GENERATED_FIELDS):
            continue
        item = ET.SubElement(channel, "item")
        add_text(item, "title", f"{row.get('id')}-{string_value(row.get('title')) or ''}")
        add_text(item, "link", f"https://www.catholicpatrimony.com/#!/class?course={name}")
        if row.get("detail"):
            add_text(item, "description", string_value(row.get("detail")) or "")
        add_text(item, "pubDate", string_value(row.get("rssDate")) or "")
        ET.SubElement(
            item,
            "enclosure",
            {
                "url": f"https://www.catholicpatrimony.com{row['link2mp3']}",
                "length": str(row["length"]),
                "type": "audio/mpeg",
            },
        )
        add_text(item, f"{{{itunes}}}duration", str(row["duration"]))
        add_text(item, f"{{{itunes}}}author", "Reverend David Tedesche")
        if row.get("detail"):
            add_text(item, f"{{{itunes}}}summary", string_value(row.get("detail")) or "")
        add_text(item, "guid", f"https://www.catholicpatrimony.com{row['link2mp3']}")

    ET.indent(rss, space="  ")
    return "<?xml version='1.0' encoding='utf-8'?>\n" + ET.tostring(rss, encoding="unicode") + "\n"


def legacy_podcast_item(row: dict[str, Any], series_name: str, scheme: str) -> str:
    def escaped(value: Any) -> str:
        return html_escape(string_value(value) or "")

    detail = string_value(row.get("detail"))
    lines = [
        "    <item>",
        f"      <title>{escaped(row.get('id'))}-{escaped(row.get('title'))}</title>",
        f"      <link>{scheme}://www.catholicpatrimony.com/#!/class?course={html_escape(series_name)}</link>",
    ]
    if detail:
        lines.append(f"      <description>{html_escape(detail)}</description>")
    lines.extend(
        [
            f"      <pubDate>{escaped(row.get('rssDate'))}</pubDate>",
            f"      <enclosure url=\"{scheme}://www.catholicpatrimony.com{html_escape(str(row['link2mp3']), quote=True)}\" length=\"{escaped(row['length'])}\" type=\"audio/mpeg\"/>",
            f"      <itunes:duration>{escaped(row['duration'])}</itunes:duration>",
            "      <itunes:author>Reverend David Tedesche</itunes:author>",
            "      <itunes:subtitle/>",
        ]
    )
    if detail:
        lines.append(f"      <itunes:summary>{html_escape(detail)}</itunes:summary>")
    lines.extend(
        [
            f"      <guid>{scheme}://www.catholicpatrimony.com{html_escape(str(row['link2mp3']))}</guid>",
            "    </item>",
        ]
    )
    return "\n".join(lines)


def html_escape(value: str, *, quote: bool = False) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;" if quote else '"')
    )


def merge_podcast_snapshot(baseline_text: str, series: dict[str, Any], cutoff: dt.date) -> str:
    item_pattern = re.compile(r"(?ms)^\s*<item>.*?</item>")
    matches = list(item_pattern.finditer(baseline_text))
    existing_blocks = [match.group(0).strip("\n") for match in matches]
    scheme_match = re.search(r"<guid>(https?)://www\.catholicpatrimony\.com", baseline_text)
    scheme = scheme_match.group(1) if scheme_match else "https"

    def block_key(block: str) -> str | None:
        match = re.search(r"<guid>https?://www\.catholicpatrimony\.com([^<]+)</guid>", block)
        return match.group(1) if match else None

    by_key = {block_key(block): block for block in existing_blocks if block_key(block)}
    ordered_keys = [block_key(block) for block in existing_blocks if block_key(block)]
    additions: list[str] = []
    addition_keys: list[str] = []
    for row in series.get("classes", []):
        if not is_eligible(row, cutoff) or not row.get("audio"):
            continue
        if not all(row.get(field) for field in GENERATED_FIELDS):
            continue
        key = str(row["link2mp3"])
        by_key[key] = legacy_podcast_item(row, series["seriesData"]["normalized_name"], scheme)
        additions.append(key)
        addition_keys.append(key)

    if not additions:
        return baseline_text
    final_keys = addition_keys + [key for key in ordered_keys if key not in set(addition_keys)]
    final_blocks = [by_key[key] for key in final_keys[:50]]
    item_text = "\n".join(final_blocks)

    if matches:
        prefix = baseline_text[: matches[0].start()]
        suffix = baseline_text[matches[-1].end() :]
        if not prefix.endswith("\n"):
            prefix += "\n"
        if suffix and not suffix.startswith("\n"):
            suffix = "\n" + suffix
        return prefix + item_text + suffix
    closing = baseline_text.rfind("</channel>")
    if closing == -1:
        raise PipelineError("baseline podcast has no channel closing tag")
    return baseline_text[:closing] + item_text + "\n  " + baseline_text[closing:]


def add_text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = value
    return element


def write_outputs(args: argparse.Namespace, merged: list[dict[str, Any]], cutoff: dt.date) -> list[Path]:
    outputs: list[Path] = []
    cp_path = args.work_dir / "out" / "cp.json"
    write_cp(cp_path, merged)
    outputs.append(cp_path)
    by_name = series_map(merged)
    for name in args.active_series:
        if name not in by_name:
            continue
        for filename in ("podcast.xml", "podcast-2.xml"):
            path = args.work_dir / "out" / name / filename
            baseline_path = args.baseline_dir / name / filename
            if baseline_path.exists():
                xml = merge_podcast_snapshot(
                    baseline_path.read_text(encoding="utf-8"), by_name[name], cutoff
                )
            else:
                xml = podcast_xml(by_name[name])
            atomic_write_text(path, xml)
            outputs.append(path)
    return outputs


def validate_outputs(args: argparse.Namespace, merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    cp_path = args.work_dir / "out" / "cp.json"
    parsed = load_cp(cp_path)
    if len(parsed) != len(merged):
        problems.append({"type": "cp-series-count-mismatch"})
    for name in args.active_series:
        path = args.work_dir / "out" / name / "podcast.xml"
        if not path.exists():
            problems.append({"type": "missing-podcast", "series": name})
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as error:
            problems.append({"type": "invalid-podcast-xml", "series": name, "error": str(error)})
            continue
        guids = [item.text for item in root.findall("./channel/item/guid")]
        duplicates = sorted({guid for guid in guids if guids.count(guid) > 1})
        if duplicates:
            problems.append({"type": "duplicate-podcast-guid", "series": name, "guids": duplicates})
    return problems


def content_type(path: Path) -> str:
    explicit = {".xml": "application/rss+xml", ".json": "application/javascript", ".mp3": "audio/mpeg"}
    return explicit.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def output_key(args: argparse.Namespace, path: Path) -> str:
    return path.relative_to(args.work_dir / "out").as_posix()


def baseline_path_for(args: argparse.Namespace, key: str) -> Path:
    return args.baseline_dir / key


def aws_head(args: argparse.Namespace, key: str) -> dict[str, Any] | None:
    command = [
        "aws",
        "s3api",
        "head-object",
        "--bucket",
        args.s3_bucket,
        "--key",
        key,
        "--region",
        args.aws_region,
        "--output",
        "json",
    ]
    try:
        result = run_command(command, capture=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as error:
        if "404" in (error.stderr or "") or "Not Found" in (error.stderr or ""):
            return None
        raise


def build_upload_plan(args: argparse.Namespace, output_paths: list[Path]) -> list[Upload]:
    uploads: list[Upload] = []
    for path in sorted(set(output_paths)):
        if not path.is_file():
            continue
        key = output_key(args, path)
        baseline_path = baseline_path_for(args, key)
        mutable = path.name in {"cp.json", "podcast.xml", "podcast-2.xml"}
        remote_exists = baseline_path.exists()
        changed = True
        reason = "new-object"
        if baseline_path.exists():
            changed = path.read_bytes() != baseline_path.read_bytes()
            reason = "content-changed" if changed else "unchanged"
        elif args.check_aws:
            head = aws_head(args, key)
            remote_exists = head is not None
            if head:
                etag = str(head.get("ETag", "")).strip('"')
                if "-" not in etag and etag == md5_file(path):
                    changed = False
                    reason = "remote-md5-match"
                else:
                    reason = "remote-object-differs"
        uploads.append(
            Upload(
                local_path=path,
                key=key,
                content_type=content_type(path),
                cache_control=MUTABLE_CACHE_CONTROL if mutable else IMMUTABLE_CACHE_CONTROL,
                changed=changed,
                remote_exists=remote_exists,
                reason=reason,
                sha256=sha256_file(path),
                size=path.stat().st_size,
            )
        )
    return uploads


def invalidation_paths(uploads: list[Upload]) -> list[str]:
    values: set[str] = set()
    for upload in uploads:
        if not upload.changed:
            continue
        mutable = Path(upload.key).name in {"cp.json", "podcast.xml", "podcast-2.xml"}
        if mutable or upload.remote_exists:
            values.add("/" + upload.key)
    return sorted(values)


def publish(args: argparse.Namespace, plan: dict[str, Any]) -> None:
    if not args.allow_publish:
        raise PipelineError("publish mode requires --allow-publish")
    for item in plan["uploads"]:
        if not item["changed"]:
            continue
        path = Path(item["localPath"])
        if sha256_file(path) != item["sha256"]:
            raise PipelineError(f"file changed after plan creation: {path}")
        run_command(
            [
                "aws",
                "s3",
                "cp",
                str(path),
                f"s3://{args.s3_bucket}/{item['key']}",
                "--region",
                args.aws_region,
                "--only-show-errors",
                "--content-type",
                item["contentType"],
                "--cache-control",
                item["cacheControl"],
                "--metadata",
                f"course2web-sha256={item['sha256']}",
            ]
        )
    paths = plan.get("cloudFrontInvalidationPaths", [])
    if paths:
        if not args.cloudfront_distribution_id:
            raise PipelineError("CloudFront paths changed but no distribution ID is configured")
        run_command(
            [
                "aws",
                "cloudfront",
                "create-invalidation",
                "--distribution-id",
                args.cloudfront_distribution_id,
                "--paths",
                *paths,
            ]
        )


def save_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    cutoff = parse_date(args.process_not_before)
    if cutoff is None:
        raise PipelineError("processing cutoff is required")
    baseline_cp = args.baseline_dir / "cp.json"
    if not baseline_cp.exists():
        raise PipelineError(f"baseline cp.json not found: {baseline_cp}")

    current = fetch_sheets(args)
    baseline = load_cp(baseline_cp)
    merged, warnings = merge_snapshot(current, baseline, cutoff)
    state_path = args.state_dir / "processing-state.json"
    state = load_state(state_path)
    merged, generated, events = process_rows(args, merged, cutoff, state)
    output_paths = generated + write_outputs(args, merged, cutoff)
    validation_problems = validate_outputs(args, merged)
    for event in events:
        if event["type"] in {"audio-error", "document-error"}:
            validation_problems.append(
                {
                    "type": "input-processing-error",
                    "series": event.get("series"),
                    "key": event.get("key"),
                    "error": event.get("error"),
                }
            )
    uploads = build_upload_plan(args, output_paths)
    invalidations = invalidation_paths(uploads)

    eligible = []
    for series in current:
        name = series["seriesData"]["normalized_name"]
        if name not in args.active_series:
            continue
        for row in series.get("classes", []):
            if is_eligible(row, cutoff):
                eligible.append(
                    {
                        "series": name,
                        "key": stable_key(row),
                        "date": string_value(row.get("date")),
                        "updatedOn": string_value(row.get("updated_on")),
                        "audio": string_value(row.get("audio")),
                    }
                )

    plan = {
        "version": 1,
        "mode": args.mode,
        "processNotBefore": args.process_not_before,
        "activeSeries": args.active_series,
        "eligibleRows": eligible,
        "events": events,
        "warnings": warnings,
        "validationProblems": validation_problems,
        "uploads": [upload.as_json() for upload in uploads],
        "cloudFrontDistributionId": args.cloudfront_distribution_id,
        "cloudFrontInvalidationPaths": invalidations,
        "remoteDeletes": [],
    }
    args.state_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.state_dir / "run-plan.json", plan)

    # Persist processing fingerprints only after local output validation succeeds.
    if not validation_problems:
        save_json(state_path, state)
    if args.mode == "publish":
        if validation_problems:
            raise PipelineError("refusing to publish because output validation failed")
        publish(args, plan)
    return plan


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dry-run", "process", "publish"), default="dry-run")
    parser.add_argument("--process-not-before", default="2026-08-04")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--sheet-fixture-dir", type=Path)
    parser.add_argument("--input-mode", choices=("local", "rclone"), default="local")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--rclone-remote", default="course2web-drive")
    parser.add_argument("--rclone-uploads-path", default="catholic/tedesche/uploads")
    parser.add_argument("--active-series", default=",".join(DEFAULT_ACTIVE_SERIES))
    parser.add_argument("--s3-bucket", default="www.catholicpatrimony.com")
    parser.add_argument("--aws-region", default="us-east-1")
    parser.add_argument("--cloudfront-distribution-id", default="")
    parser.add_argument("--check-aws", action="store_true")
    parser.add_argument("--allow-publish", action="store_true")
    args = parser.parse_args(argv)
    args.work_dir = args.work_dir.resolve()
    args.state_dir = args.state_dir.resolve()
    args.baseline_dir = args.baseline_dir.resolve()
    args.active_series = [value.strip() for value in args.active_series.split(",") if value.strip()]
    if args.input_mode == "local" and args.input_root is None:
        parser.error("--input-root is required for local input mode")
    if args.input_root:
        args.input_root = args.input_root.resolve()
    return args


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        plan = run_pipeline(args)
        changed = [item for item in plan["uploads"] if item["changed"]]
        log(f"eligible_rows={len(plan['eligibleRows'])}")
        log(f"proposed_uploads={len(changed)}")
        log(f"validation_problems={len(plan['validationProblems'])}")
        log(f"plan={args.state_dir / 'run-plan.json'}")
        return 0 if not plan["validationProblems"] else 1
    except (PipelineError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
