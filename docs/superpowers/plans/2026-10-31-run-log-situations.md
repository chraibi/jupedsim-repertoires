# Run logs, situation export and a Rust reader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write observations only in diagnostic mode, record provenance in
the run metadata, stream log reading, and add
`jps-repertoires extract-situations` with a Rust twin checked against it.

**Architecture:** `RunLog` gains a `diagnostic` flag and writes provenance
keys itself. A new module `situations.py` does the two-pass extraction and
the manifest-last publication; `cli.py` is the console script. The Rust
crate in `rust/extract-situations/` reimplements the same contract and is
compared on shared static fixtures.

**Tech Stack:** Python 3.12 standard library only (`hashlib`, `json`,
`argparse`, `subprocess`, `tempfile`); Rust 2021 with `serde_json`, `sha2`,
`clap` (cargo 1.84 is installed).

**Spec:** `docs/superpowers/specs/2026-10-31-run-log-situations-design.md`

## Global Constraints

- No new Python dependency.
- Repository root: `~/workspace/PedestrianDynamics/jupedsim-repertoires`.
  Tests: `J=~/workspace/PedestrianDynamics/jupedsim; PYTHONPATH=$J/build/stage:$PWD/src $J/.venv/bin/python -P -m pytest -q -p no:cacheprovider tests`
  (107 passed, 1 xfailed before this plan). Lint:
  `$J/.venv/bin/ruff check src tests scripts docs`. Both must pass before
  every commit.
- Commit messages: cbea.ms rules, imperative subject ≤ 50 chars, body
  wrapped at 72. No `Claude-Session:` trailer or AI attribution. Never
  `--no-verify`. Do not push.
- At most two indentation levels inside a function body; guard clauses.
- Every new file starts with `# SPDX-License-Identifier: LGPL-3.0-or-later`
  (Rust: `// SPDX-License-Identifier: LGPL-3.0-or-later`).
- JSON written by Python: `json.dumps(record, sort_keys=True,
  allow_nan=False)`, one record per line, `"\n"` line ends.
- Error categories (shared by Python and Rust, printed to stderr as
  `error[<category>]: <message>`, exit code 1): `exists`, `no-metadata`,
  `not-json`, `duplicate-request`, `duplicate-response`, `orphan-response`,
  `source-changed`, `manifest-missing`, `checksum-mismatch`. Usage errors
  exit with code 2 (argparse and clap default).

## Review Focus

1. A log cut off mid-line (run killed): last line without newline and not
   JSON → `not-json` with that line number, no output.
2. `--overwrite` with an invalid source: the previous export stays
   byte-identical (Task 5 test).
3. Output path without `.jsonl` suffix: usage error, nothing written
   (Task 6 test).
4. A log with zero requests: export with empty situation and label files
   and counts all zero, not an error (Task 5 test).
5. Temporary files are removed on every error path; the output directory
   holds no `*.tmp*` file afterwards (asserted in each Task 5 failure
   test).

---

### Task 1: Diagnostic flag and provenance in `RunLog`

**Files:**
- Create: `src/jupedsim_repertoires/provenance.py`
- Modify: `src/jupedsim_repertoires/log.py` (`RunLog.__init__`, `_write`,
  `observation`)
- Test: `tests/layer/test_repertoires_log.py`,
  `tests/layer/test_provenance.py`

**Interfaces:**
- Produces: `provenance.code_revision(directory: pathlib.Path =
  _PACKAGE_DIR) -> str | None` (`functools.cache`d);
  `provenance.file_sha256(path: pathlib.Path) -> str` (hex digest, read in
  1 MiB chunks); `RunLog(path, metadata, *, diagnostic: bool = False,
  input_checksum: str | None = None)`.
- Metadata record: `{"type": "metadata", **metadata, "diagnostic": ...,
  "code_revision": provenance.code_revision(), "input_checksum": ...}`.
  `metadata` containing any of `type`, `diagnostic`, `code_revision`,
  `input_checksum` raises `ValueError`.

- [ ] **Step 1: Write failing tests**

`tests/layer/test_provenance.py`:
- `test_code_revision_outside_repository_is_none(tmp_path)`:
  `code_revision.__wrapped__(tmp_path) is None`.
- `test_code_revision_clean_and_dirty(tmp_path)`: `git init`, add and commit
  `a.txt` (use `git -c user.name=t -c user.email=t commit`); result equals
  `git rev-parse HEAD` (40 hex chars). Add untracked `b.txt`: unchanged.
  Modify `a.txt`: result ends with `"-dirty"`.
- `test_file_sha256(tmp_path)`: file `b"abc"` →
  `"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"`.

`tests/layer/test_repertoires_log.py`:
- Update `test_first_record_is_metadata`: monkeypatch
  `jupedsim_repertoires.provenance.code_revision` to `lambda: "abc"`;
  expect `{"type": "metadata", "seed": 3, "selector": "fixed",
  "diagnostic": False, "code_revision": "abc", "input_checksum": None}`.
- `test_reserved_metadata_keys_rejected`: parametrize over the four keys,
  `pytest.raises(ValueError)`.
- `test_observations_written_only_in_diagnostic_mode`: `log.observation(...)`
  with `diagnostic=False` writes no observation record; with `True` one.
- The existing record-types test that asserts
  `by_type["observation"][0]["agent_id"] == 1` opens its log with
  `diagnostic=True`.
- `test_nan_is_rejected_at_write_time`: `log.diagnostic(0.0, "k",
  {"x": float("nan")})` raises `ValueError`.

- [ ] **Step 2: Run them; expect failures** (`ModuleNotFoundError`,
  missing keys).
- [ ] **Step 3: Implement** `provenance.py` (`git -C <dir> rev-parse HEAD`
  and `git -C <dir> status --porcelain --untracked-files=no` via
  `subprocess.run(..., capture_output=True, text=True)`; any non-zero exit
  or `FileNotFoundError` → `None`; `_PACKAGE_DIR =
  pathlib.Path(__file__).parent`). In `log.py` import the module (`from
  jupedsim_repertoires import provenance`) and call
  `provenance.code_revision()` at write time so the monkeypatch applies.
- [ ] **Step 4: Run the full suite and ruff; expect pass.**
- [ ] **Step 5: Commit** — `Write observations only in diagnostic mode`
  (body: provenance keys and strict JSON).

### Task 2: `diagnostic` and input checksum through builders and scripts

**Files:**
- Modify: `src/repertoire_examples/scenario.py` (`build_entrance`),
  `demo.py` (`build_demo`), `croma.py` (`build_2c120`), `evaluation.py`
  (`simulate`), `scripts/repertoires_{demo,entrance,2c120}.py`,
  `docs/scorecard.py`, `docs/model.md`
- Test: `tests/examples/test_entrance_scenario.py`,
  `tests/examples/test_entrance_croma.py`

**Interfaces:**
- Consumes: Task 1 `RunLog` keywords, `provenance.file_sha256`.
- Produces: `build_entrance(..., diagnostic: bool = False)`,
  `build_demo(..., diagnostic: bool = False)`,
  `build_2c120(..., diagnostic: bool = False, input_checksum: str | None =
  None)`, `simulate(..., diagnostic=False)` which passes
  `input_checksum=file_sha256(data)`. Each builder passes both on to
  `RunLog`.

- [ ] **Step 1: Write failing tests**
  - `test_entrance_log_has_no_observations_by_default`: run the existing
    small entrance setup for a few steps; no record of type `observation`;
    `metadata["diagnostic"] is False`.
  - `test_entrance_diagnostic_log_has_observations`: same with
    `diagnostic=True`; at least one observation; `metadata["diagnostic"] is
    True`.
  - In `test_entrance_croma.py`: `build_2c120(..., input_checksum="x")` →
    `metadata["input_checksum"] == "x"`.
- [ ] **Step 2: Run; expect `TypeError` on the new keyword.**
- [ ] **Step 3: Implement.** Scripts: `parser.add_argument("--diagnostic",
  action="store_true", help="also log every observation (large logs)")`;
  `repertoires_2c120.py` passes `input_checksum=file_sha256(args.data)`.
  `docs/scorecard.py`: same `--diagnostic` flag passed to `simulate`.
  `docs/model.md`: append `## Run log` — observations are written only in
  diagnostic mode; analyses of what agents saw between decisions (such as
  the no-gap investigation) need `--diagnostic`; metadata records
  `diagnostic`, `code_revision`, `input_checksum`.
- [ ] **Step 4: Full suite and ruff; expect pass.**
- [ ] **Step 5: Commit** — `Add a diagnostic switch to scenarios and
  scripts`.

### Task 3: Streaming reader

**Files:**
- Modify: `src/jupedsim_repertoires/log.py`, `selectors.py`
  (`ReplaySelector.__init__`), `scripts/repertoires_2c120.py`
  (`print_summary`)
- Test: `tests/layer/test_repertoires_log.py`

**Interfaces:**
- Produces: `iter_records(path: pathlib.Path, types: Collection[str] |
  None = None) -> Iterator[dict]` — one decoded record per non-blank line,
  filtered by `record["type"] in types` when given. `load_records` stays
  unchanged. `transitions_by_agent` uses
  `iter_records(path, {"transition"})`; `ReplaySelector` uses
  `iter_records(path, {"response"})`; `print_summary` counts in one pass
  over `iter_records(log)`.

- [ ] **Step 1: Failing test** `test_iter_records_filters_by_type`: log
  with one request, one response, one transition →
  `[r["type"] for r in iter_records(path, {"response", "transition"})] ==
  ["response", "transition"]`; `list(iter_records(path)) ==
  load_records(path)`; `iter_records(...)` returns an iterator
  (`iter(x) is x`).
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement and migrate the three readers.**
- [ ] **Step 4: Full suite and ruff; expect pass.**
- [ ] **Step 5: Commit** — `Stream run logs instead of loading them`
  (body: closes the reading part of #4).

### Task 4: SplitMix64 and reservoir sampling

**Files:**
- Create: `src/jupedsim_repertoires/sampling.py`
- Test: `tests/layer/test_sampling.py`

**Interfaces:**
- Produces: `class SplitMix64(seed: int)` with `next_u64() -> int` and
  `uniform(m: int) -> int` (rejection, spec §Sampling);
  `reservoir(keys: Iterable[K], size: int, seed: int) -> list[K]` —
  Algorithm R as in the spec, result in original order. `size < 1` or
  `seed` outside `[0, 2**64)` → `ValueError`.

- [ ] **Step 1: Failing tests** (values computed from the spec's
  definition):
  - `test_splitmix64_vectors`: seed 0 → `0xE220A8397B1DCDAF,
    0x6E789E6AA1B965F4, 0x06C45D188009454F`; seed 42 →
    `0xBDD732262FEB6E95, 0x28EFE333B266F103, 0x47526757130F9F52`.
  - `test_uniform_sequence`: `SplitMix64(42)`, five `uniform(10)` →
    `[3, 1, 8, 4, 0]`.
  - `test_uniform_full_range`: `uniform(2**64)` equals the next raw
    `next_u64()` of a twin generator (limit = 2⁶⁴, no rejection).
  - `test_reservoir_pinned`: `keys = [(i % 3, i // 3) for i in range(20)]`;
    `reservoir(keys, 5, 42) == [(0, 1), (1, 2), (0, 3), (2, 3), (0, 6)]`;
    `reservoir(keys, 5, 0) == [(2, 0), (0, 1), (1, 3), (1, 4), (0, 6)]`;
    `reservoir(keys, 1, 7) == [(2, 0)]`; `reservoir(keys, 50, 1) == keys`.
  - `test_reservoir_rejects_bad_arguments`: size 0, seed −1, seed 2**64.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement** with `& 0xFFFF_FFFF_FFFF_FFFF` after each add
  and multiply.
- [ ] **Step 4: Run; expect pass.**
- [ ] **Step 5: Commit** — `Add reproducible reservoir sampling`.

### Task 5: Situation extraction

**Files:**
- Create: `src/jupedsim_repertoires/situations.py`,
  `tests/fixtures/situations/generate.py`, the fixtures it writes,
  `tests/fixtures/situations/expected.json`
- Test: `tests/layer/test_situations.py`

**Interfaces:**
- Consumes: Task 4 `reservoir`.
- Produces:
  - `class ExtractError(Exception)` with attribute `category: str`
    (Global Constraints list).
  - `output_paths(output: pathlib.Path) -> tuple[Path, Path, Path]` —
    `x.jsonl` → `(x.jsonl, x.labels.jsonl, x.manifest.json)`; other
    suffix → `ValueError`.
  - `extract_situations(source: Path, output: Path, *, sample: int | None
    = None, seed: int = 0, overwrite: bool = False) -> dict` — returns the
    manifest.
  - `verify_export(output: Path) -> dict` — reads the manifest, checks both
    files' SHA-256 and size; raises `manifest-missing` or
    `checksum-mismatch`; returns the manifest.
  - Internal seams used by tests: `_scan(source) -> _Scan` (pass 1),
    `_publish_manifest(path, manifest) -> None` (last step).

Fixtures (static files, written once by `generate.py` with plain
`json.dumps(sort_keys=True)`, committed; `generate.py` is the record of how
they were made). Metadata line in all:
`{"scenario": "fixture", "type": "metadata"}`. Request records carry
`decision_index, events, members, observations, snapshot_time, states,
type, unit_id, unit_index` with small literal values; responses
`decision_index, reasons, repertoires, snapshot_time, type, unit_id,
unit_index`.
- `complete.jsonl`: requests (0,0), (1,0), (0,1), each followed by its
  response; plus one observation and one transition record.
- `missing_response.jsonl`: as complete, without the response of (0,1).
- `duplicate_request.jsonl`, `duplicate_response.jsonl`,
  `orphan_response.jsonl` (response (5,0) with no request).
- `not_json.jsonl`: complete, last line truncated, no final newline.
- `nan.jsonl`: one request whose `snapshot_time` is the literal `NaN`.
- `no_metadata.jsonl`: complete without its first line; `empty.jsonl`.
- `no_requests.jsonl`: metadata and one transition only.
- `sampling.jsonl`: 20 requests, request i has key
  `(unit_index, decision_index) = (i % 3, i // 3)`, each followed by its
  response.
- `expected.json`: `{"sampling.jsonl": {"5,42": [[0,1],[1,2],[0,3],[2,3],[0,6]],
  "5,0": [[2,0],[0,1],[1,3],[1,4],[0,6]], "50,42": "all"}}`.

- [ ] **Step 1: Write `generate.py`, run it, commit nothing yet.**
- [ ] **Step 2: Failing tests** in `tests/layer/test_situations.py`:
  - `test_complete_export`: keys in situations file `[(0,0),(1,0),(0,1)]`;
    no `type` key; `run_id == sha256(file bytes)`, `config_id ==
    sha256(first line without "\n")`; labels same key order, `decision ==
    {"repertoires": [...], "reasons": [...]}`; manifest `schema_version
    == 1`, `extractor == "jps-repertoires extract-situations"`,
    `sampling is None`, `counts == {"requests": 3, "responses": 3,
    "situations": 3, "labels": 3, "missing_labels": 0}`;
    `verify_export(out)` passes.
  - `test_missing_response_label`: label of (0,1) is `{"decision": None,
    "missing": "no response", ...}`; `missing_labels == 1`.
  - `test_errors` parametrized: fixture → category
    (`duplicate_request`→`duplicate-request`, …, `not_json`→`not-json`
    with `"line 9"` (the truncated last line) in the message, `nan`→`not-json`,
    `no_metadata`/`empty`→`no-metadata`); no output file and no `*.tmp*`
    file in the directory afterwards.
  - `test_no_requests_exports_empty_files`: counts all zero; both data
    files empty.
  - `test_sampling_matches_expected`: per `expected.json`; manifest
    `sampling == {"algorithm": "reservoir-r/splitmix64", "size": 5,
    "seed": 42}`.
  - `test_sampling_still_checks_whole_log`: `duplicate_request.jsonl` with
    `sample=1` → `duplicate-request`.
  - `test_existing_output_without_overwrite`: second run → `exists`.
  - `test_source_changed_between_passes`: monkeypatch `situations._scan`
    to call the original then append `b"\n"` to the source → 
    `source-changed`; nothing published, no temp files.
  - `test_interrupted_publication`: monkeypatch `_publish_manifest` to
    raise `OSError` → data files present, manifest absent;
    `verify_export` raises `manifest-missing`.
  - `test_checksum_mismatch`: after a good export append a byte to the
    labels file → `verify_export` raises `checksum-mismatch`.
  - `test_overwrite_with_invalid_source_keeps_export`: good export of
    `complete.jsonl` to `out`; then `extract_situations(not_json, out,
    overwrite=True)` raises; all three files byte-identical to before.
- [ ] **Step 3: Run; expect ImportError.**
- [ ] **Step 4: Implement** per spec §Passes and §Outputs. Pass 1 reads
  binary lines: hash all bytes; line 1 → `config_id`; parse each line
  with `json.loads(line, parse_constant=_reject)`; collect request and
  response key sets; keys of requests in log order go to `reservoir` or
  are all selected. Record `(st_size, st_mtime_ns)` before pass 1. Pass 2
  writes situations to a `tempfile.NamedTemporaryFile(dir=output.parent,
  delete=False)` and collects selected decisions; then labels. Order of
  publication: existence check at start (before pass 1), temp files
  complete, source re-check, then delete old manifest (if `overwrite`),
  rename data files, `_publish_manifest` (temp + rename).
  `extractor_version`: `importlib.metadata.version("jupedsim-repertoires")`,
  `"unknown"` on `PackageNotFoundError`. Manifest written with
  `json.dumps(indent=2, sort_keys=True) + "\n"`.
- [ ] **Step 5: Full suite and ruff; expect pass.**
- [ ] **Step 6: Commit** — `Extract decision situations from run logs`
  (fixtures included).

### Task 6: `jps-repertoires` command

**Files:**
- Create: `src/jupedsim_repertoires/cli.py`
- Modify: `pyproject.toml` (`[project.scripts] jps-repertoires =
  "jupedsim_repertoires.cli:main"`), `README.md`, `docs/model.md`
- Test: `tests/layer/test_cli.py`

**Interfaces:**
- Consumes: Task 5 `extract_situations`, `ExtractError`, `output_paths`.
- Produces: `main(argv: list[str] | None = None) -> int`; subcommand
  `extract-situations RUN --output OUT [--sample N] [--seed S]
  [--overwrite]`. `ExtractError` → stderr `error[<category>]: <msg>`,
  return 1. Usage errors (`--seed` without `--sample`, N < 1, seed out of
  range, output not `.jsonl`) → `parser.error` (exit 2). `--sample` help
  states: "uniform over decision requests, not over people or time".
  Runnable as `python -m jupedsim_repertoires.cli`.

- [ ] **Step 1: Failing tests:** success returns 0 and writes three files;
  `duplicate_request.jsonl` returns 1 with `error[duplicate-request]` on
  stderr (`capsys`); each usage error raises `SystemExit(2)` and writes
  nothing.
- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement**; README gets a short "Extracting situations"
  section; `docs/model.md` `## Run log` gets the sampling note.
- [ ] **Step 4: Full suite and ruff; expect pass.**
- [ ] **Step 5: Commit** — `Add the jps-repertoires command`.

### Task 7: Rust twin

**Files:**
- Create: `rust/extract-situations/Cargo.toml`, `src/main.rs`,
  `src/splitmix.rs`, `src/extract.rs`, `rust/extract-situations/README.md`
- Modify: `.gitignore` (`rust/extract-situations/target/`)
- Test: unit tests in `splitmix.rs`; `tests/layer/test_situations_rust.py`

**Interfaces:**
- Consumes: the spec contract, Task 5 fixtures and `expected.json`.
- Produces: binary `extract-situations RUN --output OUT [--sample N]
  [--seed S] [--overwrite]`, same files, same error categories and exit
  codes. Dependencies: `serde_json` (default `Map` sorts keys), `sha2`,
  `clap` with `derive`. `uniform(m: u64)` computes `limit` as `u128`:
  `(1u128 << 64) - ((1u128 << 64) % m as u128)`; the generator uses
  `wrapping_add` / `wrapping_mul` on `u64`.

- [ ] **Step 1: Rust unit tests** for the SplitMix64 vectors,
  `uniform` sequence `[3, 1, 8, 4, 0]` (seed 42, m 10) and the pinned
  reservoir from Task 4. `cargo test` fails (no implementation).
- [ ] **Step 2: Python parity test** `test_situations_rust.py`, skipped
  when `shutil.which("extract-situations")` is None. For every fixture
  and for `sampling.jsonl` with `(5, 42)` and `(5, 0)`: run both into
  separate directories; same exit code; on error the same category; on
  success equal selected keys in order, situation and label records equal
  as parsed JSON, manifests equal after removing `extractor`,
  `extractor_version`, `source.path`, `outputs`; `verify_export` passes
  on the Rust output.
- [ ] **Step 3: Implement** `main.rs` (clap), `extract.rs` (two passes,
  publication order as Task 5; `extractor` is `"extract-situations"`).
- [ ] **Step 4:** `cargo test` passes; `cargo build --release` in the crate, then
  the full Python suite with `PATH=$PWD/rust/extract-situations/target/release:$PATH`
  runs the parity test (not skipped) and passes; ruff passes.
- [ ] **Step 5: Commit** — `Add a Rust twin of extract-situations`.
