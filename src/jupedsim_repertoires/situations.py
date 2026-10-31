# SPDX-License-Identifier: LGPL-3.0-or-later

"""Export the decision requests of a run log as situations with labels."""

import dataclasses
import hashlib
import importlib.metadata
import json
import os
import pathlib
import tempfile
from typing import Any, TextIO

from jupedsim_repertoires import provenance
from jupedsim_repertoires.sampling import reservoir

_EXTRACTOR = "jps-repertoires extract-situations"
_ALGORITHM = "reservoir-r/splitmix64"

Key = tuple[int, int]


class ExtractError(Exception):
    """A run log or export violates the situation export rules.

    Attributes:
        category: One of ``exists``, ``no-metadata``, ``not-json``,
            ``duplicate-request``, ``duplicate-response``,
            ``orphan-response``, ``source-changed``, ``manifest-missing``
            and ``checksum-mismatch``.
    """

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclasses.dataclass
class _Scan:
    """Result of pass 1 over a run log."""

    size: int
    mtime_ns: int
    run_id: str = ""
    config_id: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    requests: dict[Key, None] = dataclasses.field(default_factory=dict)
    responses: dict[Key, int] = dataclasses.field(default_factory=dict)


def output_paths(output: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Return the situations, labels and manifest paths for ``output``.

    Raises:
        ValueError: If ``output`` does not end in ``.jsonl``.
    """
    if output.suffix != ".jsonl":
        raise ValueError(f"output must end in .jsonl, got {output}")
    return (
        output,
        output.with_suffix(".labels.jsonl"),
        output.with_suffix(".manifest.json"),
    )


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def _parse(number: int, line: bytes) -> dict:
    try:
        record = json.loads(line, parse_constant=_reject_constant)
    except ValueError as err:
        raise ExtractError("not-json", f"line {number}: {err}") from err
    if not isinstance(record, dict):
        raise ExtractError("not-json", f"line {number}: record is not an object")
    return record


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _key(number: int, record: dict) -> Key:
    unit, decision = record.get("unit_index"), record.get("decision_index")
    if not _is_int(unit) or not _is_int(decision):
        raise ExtractError(
            "not-json", f"line {number}: unit_index and decision_index must be integers"
        )
    return unit, decision


def _scan_line(scan: _Scan, number: int, line: bytes) -> None:
    record = _parse(number, line)
    if number == 1:
        if record.get("type") != "metadata":
            raise ExtractError("no-metadata", "line 1 is not a metadata record")
        scan.metadata = record
        scan.config_id = hashlib.sha256(line.removesuffix(b"\n")).hexdigest()
        return
    kind = record.get("type")
    if kind == "request":
        _add_request(scan, number, record)
    elif kind == "response":
        _add_response(scan, number, record)


def _add_request(scan: _Scan, number: int, record: dict) -> None:
    key = _key(number, record)
    if key in scan.requests:
        raise ExtractError("duplicate-request", f"line {number}: duplicate request {key}")
    scan.requests[key] = None


def _add_response(scan: _Scan, number: int, record: dict) -> None:
    key = _key(number, record)
    _decision(number, record)
    if key in scan.responses:
        raise ExtractError("duplicate-response", f"line {number}: duplicate response {key}")
    scan.responses[key] = number


def _check_orphans(scan: _Scan) -> None:
    for key, number in scan.responses.items():
        if key not in scan.requests:
            raise ExtractError("orphan-response", f"line {number}: response {key} has no request")


def _scan(source: pathlib.Path) -> _Scan:
    """Pass 1: hash, validate and collect the keys of a run log."""
    stat = source.stat()
    scan = _Scan(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    digest = hashlib.sha256()
    with open(source, "rb") as file:
        for number, line in enumerate(file, 1):
            digest.update(line)
            _scan_line(scan, number, line)
    scan.run_id = digest.hexdigest()
    if not scan.metadata:
        raise ExtractError("no-metadata", "the log has no metadata record")
    _check_orphans(scan)
    return scan


def _select(scan: _Scan, sample: int | None, seed: int) -> list[Key]:
    if sample is None:
        return list(scan.requests)
    return reservoir(scan.requests, sample, seed)


def _check_unchanged(source: pathlib.Path, scan: _Scan) -> None:
    stat = source.stat()
    if (stat.st_size, stat.st_mtime_ns) != (scan.size, scan.mtime_ns):
        raise ExtractError("source-changed", f"{source} changed during extraction")


def _decision(number: int, record: dict) -> dict:
    if not isinstance(record.get("repertoires"), list):
        raise ExtractError("not-json", f"line {number}: response lacks a repertoires list")
    return {"repertoires": record["repertoires"], "reasons": record.get("reasons", [])}


def _dump(record: dict) -> str:
    return json.dumps(record, sort_keys=True, allow_nan=False) + "\n"


def _pass_two_line(
    number: int,
    line: bytes,
    scan: _Scan,
    selected: set[Key],
    handle: TextIO,
    decisions: dict[Key, dict],
) -> None:
    if number == 1:
        return
    record = _parse(number, line)
    kind = record.get("type")
    if kind not in ("request", "response"):
        return
    key = _key(number, record)
    if key not in selected:
        return
    if kind == "response":
        decisions[key] = _decision(number, record)
        return
    situation = {k: v for k, v in record.items() if k != "type"}
    situation.update(run_id=scan.run_id, config_id=scan.config_id)
    handle.write(_dump(situation))


def _pass_two(
    source: pathlib.Path,
    scan: _Scan,
    selected: set[Key],
    handle: TextIO,
) -> dict[Key, dict]:
    """Pass 2: write selected situations, return selected decisions."""
    _check_unchanged(source, scan)
    digest = hashlib.sha256()
    decisions: dict[Key, dict] = {}
    with open(source, "rb") as file:
        for number, line in enumerate(file, 1):
            digest.update(line)
            _pass_two_line(number, line, scan, selected, handle, decisions)
    if digest.hexdigest() != scan.run_id:
        raise ExtractError("source-changed", f"{source} changed during extraction")
    return decisions


def _label(scan: _Scan, key: Key, decisions: dict[Key, dict]) -> dict:
    label: dict[str, Any] = {
        "run_id": scan.run_id,
        "unit_index": key[0],
        "decision_index": key[1],
        "decision": decisions.get(key),
    }
    if key not in decisions:
        label["missing"] = "no response"
    return label


def _temp_file(directory: pathlib.Path, temps: list[pathlib.Path]) -> TextIO:
    handle = tempfile.NamedTemporaryFile(
        "w", dir=directory, suffix=".tmp", delete=False, encoding="utf-8", newline="\n"
    )
    temps.append(pathlib.Path(handle.name))
    return handle


def _write_outputs(
    source: pathlib.Path,
    directory: pathlib.Path,
    scan: _Scan,
    selected: list[Key],
    temps: list[pathlib.Path],
) -> tuple[pathlib.Path, pathlib.Path, int]:
    with _temp_file(directory, temps) as sit_handle:
        decisions = _pass_two(source, scan, set(selected), sit_handle)
    _check_unchanged(source, scan)
    with _temp_file(directory, temps) as lab_handle:
        for key in selected:
            lab_handle.write(_dump(_label(scan, key, decisions)))
    missing = sum(1 for key in selected if key not in decisions)
    return temps[-2], temps[-1], missing


def _same_file(a: pathlib.Path, b: pathlib.Path) -> bool:
    if a.resolve() == b.resolve():
        return True
    return b.exists() and a.exists() and os.path.samefile(a, b)


def _check_not_source(source: pathlib.Path, paths: tuple[pathlib.Path, ...]) -> None:
    for path in paths:
        if _same_file(source, path):
            raise ValueError(f"output {path} is the source run log; refusing to overwrite it")


def _check_sampling(sample: int | None, seed: int) -> None:
    if sample is not None and sample < 1:
        raise ValueError(f"sample must be at least 1, got {sample}")
    if not 0 <= seed < 2**64:
        raise ValueError(f"seed must satisfy 0 <= seed < 2**64, got {seed}")


def _check_absent(paths: tuple[pathlib.Path, ...]) -> None:
    for path in paths:
        if path.exists():
            raise ExtractError("exists", f"{path} exists; pass overwrite to replace it")


def _extractor_version() -> str:
    try:
        return importlib.metadata.version("jupedsim-repertoires")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _file_entry(path: pathlib.Path) -> dict[str, Any]:
    return {"sha256": provenance.file_sha256(path), "bytes": path.stat().st_size}


def _manifest(
    source: pathlib.Path,
    scan: _Scan,
    sample: int | None,
    seed: int,
    files: tuple[pathlib.Path, pathlib.Path],
    selected: int,
    missing: int,
) -> dict[str, Any]:
    sampling = None
    if sample is not None:
        sampling = {"algorithm": _ALGORITHM, "size": sample, "seed": seed}
    return {
        "schema_version": 1,
        "extractor": _EXTRACTOR,
        "extractor_version": _extractor_version(),
        "source": {
            "path": str(source),
            "run_id": scan.run_id,
            "config_id": scan.config_id,
            "bytes": scan.size,
        },
        "outputs": {
            "situations": _file_entry(files[0]),
            "labels": _file_entry(files[1]),
        },
        "metadata": scan.metadata,
        "sampling": sampling,
        "counts": {
            "requests": len(scan.requests),
            "responses": len(scan.responses),
            "situations": selected,
            "labels": selected,
            "missing_labels": missing,
        },
    }


def _publish_manifest(path: pathlib.Path, manifest: dict[str, Any]) -> None:
    """Write the manifest through a temporary file and rename it."""
    text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    handle = tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8", newline="\n"
    )
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _publish(
    paths: tuple[pathlib.Path, pathlib.Path, pathlib.Path],
    temps: tuple[pathlib.Path, pathlib.Path],
    manifest: dict[str, Any],
    overwrite: bool,
) -> None:
    if overwrite:
        paths[2].unlink(missing_ok=True)
    else:
        _check_absent(paths)
    os.replace(temps[0], paths[0])
    os.replace(temps[1], paths[1])
    _publish_manifest(paths[2], manifest)


def extract_situations(
    source: pathlib.Path,
    output: pathlib.Path,
    *,
    sample: int | None = None,
    seed: int = 0,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export the requests of a run log as situations and labels.

    Args:
        source: Run log written by ``RunLog``.
        output: Situations file, ending in ``.jsonl``; the labels and
            manifest files are written next to it.
        sample: Number of requests to sample uniformly; all when ``None``.
        seed: SplitMix64 seed of the sample, 0 <= seed < 2**64.
        overwrite: Replace an existing export.

    Returns:
        The manifest, which is also written as the last file.

    Raises:
        ExtractError: If the log breaks a rule or an output exists.
        ValueError: If ``output``, ``sample`` or ``seed`` is invalid, or
            an output path is the source run log.
    """
    _check_sampling(sample, seed)
    paths = output_paths(output)
    _check_not_source(source, paths)
    if not overwrite:
        _check_absent(paths)
    scan = _scan(source)
    selected = _select(scan, sample, seed)
    temps: list[pathlib.Path] = []
    try:
        sit_tmp, lab_tmp, missing = _write_outputs(source, output.parent, scan, selected, temps)
        files = (sit_tmp, lab_tmp)
        manifest = _manifest(source, scan, sample, seed, files, len(selected), missing)
        _publish(paths, files, manifest, overwrite)
        return manifest
    finally:
        for temp in temps:
            temp.unlink(missing_ok=True)


def _check_entry(name: str, path: pathlib.Path, entry: dict[str, Any]) -> None:
    if not path.is_file():
        raise ExtractError("checksum-mismatch", f"{name} file {path} is missing")
    if path.stat().st_size != entry["bytes"] or provenance.file_sha256(path) != entry["sha256"]:
        raise ExtractError("checksum-mismatch", f"{name} file {path} does not match the manifest")


def _check_manifest_shape(manifest: dict[str, Any]) -> None:
    for name in ("situations", "labels"):
        entry = manifest["outputs"][name]
        if "sha256" not in entry or "bytes" not in entry:
            raise ValueError(f"outputs.{name} lacks sha256 or bytes")


def _read_manifest(path: pathlib.Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        _check_manifest_shape(manifest)
    except (ValueError, KeyError, TypeError) as err:
        raise ExtractError("manifest-missing", f"{path} is not a valid manifest: {err}") from err
    return manifest


def verify_export(output: pathlib.Path) -> dict[str, Any]:
    """Check that an export is complete and matches its manifest.

    Returns:
        The manifest.

    Raises:
        ExtractError: ``manifest-missing`` if the manifest is absent,
            ``checksum-mismatch`` if a file differs from it.
    """
    sit_path, lab_path, manifest_path = output_paths(output)
    if not manifest_path.is_file():
        raise ExtractError("manifest-missing", f"{manifest_path} is missing; the export is incomplete")
    manifest = _read_manifest(manifest_path)
    _check_entry("situations", sit_path, manifest["outputs"]["situations"])
    _check_entry("labels", lab_path, manifest["outputs"]["labels"])
    return manifest
