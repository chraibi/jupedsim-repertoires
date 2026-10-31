# SPDX-License-Identifier: LGPL-3.0-or-later

import pathlib
import subprocess
import sys

import pytest

from jupedsim_repertoires.cli import main

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "situations"


def extract(source: pathlib.Path, output: pathlib.Path, *args: str) -> int:
    return main(["extract-situations", str(source), "--output", str(output), *args])


def test_success_writes_three_files(tmp_path):
    out = tmp_path / "s.jsonl"
    assert extract(FIXTURES / "complete.jsonl", out) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "s.jsonl",
        "s.labels.jsonl",
        "s.manifest.json",
    ]


def test_sample_without_seed_uses_seed_zero(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert extract(FIXTURES / "sampling.jsonl", a, "--sample", "2") == 0
    assert extract(FIXTURES / "sampling.jsonl", b, "--sample", "2", "--seed", "0") == 0
    assert a.read_text() == b.read_text()


def test_extract_error_reports_category(tmp_path, capsys):
    out = tmp_path / "s.jsonl"
    assert extract(FIXTURES / "duplicate_request.jsonl", out) == 1
    assert "error[duplicate-request]" in capsys.readouterr().err


def test_existing_output_needs_overwrite(tmp_path, capsys):
    out = tmp_path / "s.jsonl"
    assert extract(FIXTURES / "complete.jsonl", out) == 0
    assert extract(FIXTURES / "complete.jsonl", out) == 1
    assert "error[exists]" in capsys.readouterr().err
    assert extract(FIXTURES / "complete.jsonl", out, "--overwrite") == 0


@pytest.mark.parametrize(
    "args",
    [
        ["--seed", "1"],
        ["--sample", "0"],
        ["--sample", "-3"],
        ["--sample", "1", "--seed", "-1"],
        ["--sample", "1", "--seed", str(2**64)],
    ],
)
def test_usage_errors_exit_2_and_write_nothing(tmp_path, args):
    with pytest.raises(SystemExit) as info:
        extract(FIXTURES / "complete.jsonl", tmp_path / "s.jsonl", *args)
    assert info.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_output_must_end_in_jsonl(tmp_path):
    with pytest.raises(SystemExit) as info:
        extract(FIXTURES / "complete.jsonl", tmp_path / "s.json")
    assert info.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_seed_upper_bound_accepted(tmp_path):
    out = tmp_path / "s.jsonl"
    args = ["--sample", "1", "--seed", str(2**64 - 1)]
    assert extract(FIXTURES / "complete.jsonl", out, *args) == 0


def test_runs_as_module(tmp_path):
    out = tmp_path / "s.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "jupedsim_repertoires.cli",
            "extract-situations",
            str(FIXTURES / "complete.jsonl"),
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
