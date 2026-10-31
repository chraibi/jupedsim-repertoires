# SPDX-License-Identifier: LGPL-3.0-or-later

"""Parity of the Rust extract-situations binary with the Python extractor."""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from jupedsim_repertoires.situations import (
    ExtractError,
    extract_situations,
    verify_export,
)

RUST = shutil.which("extract-situations")
FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "situations"
SAMPLING = "sampling.jsonl"

pytestmark = pytest.mark.skipif(RUST is None, reason="extract-situations is not on PATH")

CASES = [(path.name, None) for path in sorted(FIXTURES.glob("*.jsonl"))]
CASES += [(SAMPLING, (5, 42)), (SAMPLING, (5, 0))]
IGNORED_MANIFEST = ("extractor", "extractor_version", "outputs")


def read_lines(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def keys(records: list[dict]) -> list[tuple[int, int]]:
    return [(r["unit_index"], r["decision_index"]) for r in records]


def run_python(source, out, sample):
    kwargs = {} if sample is None else {"sample": sample[0], "seed": sample[1]}
    try:
        extract_situations(source, out, **kwargs)
    except ExtractError as err:
        return err.category
    return None


def run_rust(source, out, sample):
    command = [RUST, str(source), "--output", str(out)]
    if sample is not None:
        command += ["--sample", str(sample[0]), "--seed", str(sample[1])]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return None
    assert result.returncode == 1, result.stderr
    match = re.match(r"error\[([a-z-]+)\]: ", result.stderr)
    assert match, result.stderr
    return match.group(1)


def comparable(manifest: dict) -> dict:
    manifest = {k: v for k, v in manifest.items() if k not in IGNORED_MANIFEST}
    manifest["source"] = {k: v for k, v in manifest["source"].items() if k != "path"}
    return manifest


@pytest.mark.parametrize(("name", "sample"), CASES)
def test_rust_matches_python(tmp_path, name, sample):
    source = FIXTURES / name
    py_out = tmp_path / "py" / "x.jsonl"
    rs_out = tmp_path / "rs" / "x.jsonl"
    py_out.parent.mkdir()
    rs_out.parent.mkdir()

    py_category = run_python(source, py_out, sample)
    rs_category = run_rust(source, rs_out, sample)

    assert rs_category == py_category
    if py_category is not None:
        assert not list(rs_out.parent.iterdir())
        return
    py_sit, rs_sit = read_lines(py_out), read_lines(rs_out)
    assert keys(rs_sit) == keys(py_sit)
    assert rs_sit == py_sit
    labels = ".labels.jsonl"
    assert read_lines(rs_out.with_suffix(labels)) == read_lines(py_out.with_suffix(labels))
    manifests = [json.loads(p.with_suffix(".manifest.json").read_text()) for p in (py_out, rs_out)]
    assert comparable(manifests[1]) == comparable(manifests[0])
    assert manifests[1]["extractor"] == "extract-situations"
    assert manifests[1]["source"]["path"] == str(source)
    verify_export(rs_out)
    assert sorted(p.name for p in rs_out.parent.iterdir()) == sorted(
        p.name for p in py_out.parent.iterdir()
    )
