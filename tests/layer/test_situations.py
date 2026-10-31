# SPDX-License-Identifier: LGPL-3.0-or-later

import hashlib
import json
import pathlib
import shutil

import pytest

from jupedsim_repertoires import situations
from jupedsim_repertoires.situations import (
    ExtractError,
    extract_situations,
    output_paths,
    verify_export,
)

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "situations"


def read_lines(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def keys(records: list[dict]) -> list[tuple[int, int]]:
    return [(r["unit_index"], r["decision_index"]) for r in records]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tmp_files(directory: pathlib.Path) -> list[pathlib.Path]:
    return list(directory.glob("*.tmp*"))


@pytest.fixture
def out(tmp_path) -> pathlib.Path:
    return tmp_path / "out" / "situations.jsonl"


@pytest.fixture(autouse=True)
def make_out_dir(out):
    out.parent.mkdir()


def test_output_paths():
    paths = output_paths(pathlib.Path("d/x.jsonl"))
    assert paths == (
        pathlib.Path("d/x.jsonl"),
        pathlib.Path("d/x.labels.jsonl"),
        pathlib.Path("d/x.manifest.json"),
    )
    with pytest.raises(ValueError):
        output_paths(pathlib.Path("d/x.json"))


def test_complete_export(out):
    source = FIXTURES / "complete.jsonl"
    data = source.read_bytes()
    manifest = extract_situations(source, out)
    sits_path, labels_path, manifest_path = output_paths(out)
    sits = read_lines(sits_path)
    labels = read_lines(labels_path)
    assert keys(sits) == [(0, 0), (1, 0), (0, 1)]
    assert keys(labels) == keys(sits)
    assert all("type" not in s for s in sits)
    run_id = sha256(data)
    config_id = sha256(data.split(b"\n")[0])
    assert {s["run_id"] for s in sits} == {run_id}
    assert {s["config_id"] for s in sits} == {config_id}
    assert labels[0]["decision"] == {
        "repertoires": ["queueing"],
        "reasons": ["fixture"],
    }
    assert labels[0]["run_id"] == run_id
    assert manifest == json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["extractor"] == "jps-repertoires extract-situations"
    assert manifest["sampling"] is None
    assert manifest["counts"] == {
        "requests": 3,
        "responses": 3,
        "situations": 3,
        "labels": 3,
        "missing_labels": 0,
    }
    assert manifest["source"] == {
        "path": str(source),
        "run_id": run_id,
        "config_id": config_id,
        "bytes": len(data),
    }
    assert manifest["metadata"] == {"scenario": "fixture", "type": "metadata"}
    assert verify_export(out) == manifest


def test_missing_response_label(out):
    manifest = extract_situations(FIXTURES / "missing_response.jsonl", out)
    labels = read_lines(output_paths(out)[1])
    assert labels[2]["decision"] is None
    assert labels[2]["missing"] == "no response"
    assert keys(labels)[2] == (0, 1)
    assert manifest["counts"]["missing_labels"] == 1
    assert manifest["counts"]["responses"] == 2


@pytest.mark.parametrize(
    "name, category",
    [
        ("duplicate_request", "duplicate-request"),
        ("duplicate_response", "duplicate-response"),
        ("orphan_response", "orphan-response"),
        ("not_json", "not-json"),
        ("nan", "not-json"),
        ("no_metadata", "no-metadata"),
        ("empty", "no-metadata"),
    ],
)
def test_errors(out, name, category):
    with pytest.raises(ExtractError) as info:
        extract_situations(FIXTURES / f"{name}.jsonl", out)
    assert info.value.category == category
    if name == "not_json":
        assert "line 9" in str(info.value)
    assert list(out.parent.iterdir()) == []


def test_blank_line_is_not_json(tmp_path, out):
    source = tmp_path / "blank.jsonl"
    lines = (FIXTURES / "complete.jsonl").read_text().splitlines()
    source.write_text("\n".join(lines[:3] + [""] + lines[3:]) + "\n")
    with pytest.raises(ExtractError, match="line 4") as info:
        extract_situations(source, out)
    assert info.value.category == "not-json"


def test_no_requests_exports_empty_files(out):
    manifest = extract_situations(FIXTURES / "no_requests.jsonl", out)
    sits_path, labels_path, _ = output_paths(out)
    assert sits_path.read_bytes() == b""
    assert labels_path.read_bytes() == b""
    assert set(manifest["counts"].values()) == {0}
    verify_export(out)


def test_sampling_matches_expected(out):
    expected = json.loads((FIXTURES / "expected.json").read_text())
    for case, selection in expected["sampling.jsonl"].items():
        size, seed = (int(x) for x in case.split(","))
        manifest = extract_situations(
            FIXTURES / "sampling.jsonl", out, sample=size, seed=seed, overwrite=True
        )
        got = keys(read_lines(output_paths(out)[0]))
        if selection == "all":
            assert len(got) == 20
        else:
            assert got == [tuple(k) for k in selection]
        assert manifest["sampling"] == {
            "algorithm": "reservoir-r/splitmix64",
            "size": size,
            "seed": seed,
        }
        assert manifest["counts"]["requests"] == 20
        assert manifest["counts"]["situations"] == len(got)
        assert keys(read_lines(output_paths(out)[1])) == got


def test_sampling_still_checks_whole_log(out):
    with pytest.raises(ExtractError) as info:
        extract_situations(FIXTURES / "duplicate_request.jsonl", out, sample=1)
    assert info.value.category == "duplicate-request"


def test_existing_output_without_overwrite(out):
    extract_situations(FIXTURES / "complete.jsonl", out)
    with pytest.raises(ExtractError) as info:
        extract_situations(FIXTURES / "complete.jsonl", out)
    assert info.value.category == "exists"
    extract_situations(FIXTURES / "complete.jsonl", out, overwrite=True)


def test_source_changed_between_passes(tmp_path, out, monkeypatch):
    source = tmp_path / "run.jsonl"
    shutil.copy(FIXTURES / "complete.jsonl", source)
    original = situations._scan

    def scan_then_append(path):
        result = original(path)
        with open(path, "ab") as file:
            file.write(b"\n")
        return result

    monkeypatch.setattr(situations, "_scan", scan_then_append)
    with pytest.raises(ExtractError) as info:
        extract_situations(source, out)
    assert info.value.category == "source-changed"
    assert list(out.parent.iterdir()) == []


def test_interrupted_publication(out, monkeypatch):
    def fail(path, manifest):
        raise OSError("disk full")

    monkeypatch.setattr(situations, "_publish_manifest", fail)
    with pytest.raises(OSError):
        extract_situations(FIXTURES / "complete.jsonl", out)
    sits_path, labels_path, manifest_path = output_paths(out)
    assert sits_path.exists() and labels_path.exists()
    assert not manifest_path.exists()
    assert tmp_files(out.parent) == []
    with pytest.raises(ExtractError) as info:
        verify_export(out)
    assert info.value.category == "manifest-missing"


def test_checksum_mismatch(out):
    extract_situations(FIXTURES / "complete.jsonl", out)
    with open(output_paths(out)[1], "ab") as file:
        file.write(b" ")
    with pytest.raises(ExtractError) as info:
        verify_export(out)
    assert info.value.category == "checksum-mismatch"


def test_overwrite_with_invalid_source_keeps_export(out):
    extract_situations(FIXTURES / "complete.jsonl", out)
    paths = output_paths(out)
    before = [p.read_bytes() for p in paths]
    with pytest.raises(ExtractError):
        extract_situations(FIXTURES / "not_json.jsonl", out, overwrite=True)
    assert [p.read_bytes() for p in paths] == before
    assert tmp_files(out.parent) == []
