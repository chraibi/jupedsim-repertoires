# Run logs, situation export and a Rust reader

Date: 2026-10-31. Status: approved after external review, ready for
planning.

## Why

A 2C120 run log is about 600 MB. 91 % of it is `observation` records:
what each agent perceived and remembered at every perception step, with
the whole 8 s progress history repeated in every record. Normal readers
do not need them; detailed diagnostic analyses do. Size itself is not the problem; quick, efficient access to what we
actually use is.

The record type with a future is `request`: the situation a selector was
asked about. The next step of the project is to put the same recorded
situations to other selectors (the rule selector, Jev, Laya) offline and
compare their choices. That needs a clean, reproducible way to get
situations out of a run.

The maintainer is learning Rust. A Rust twin of the extraction command is
the learning project; Python stays the supported implementation.

## Goals

1. Observations are written only in diagnostic mode.
2. A command `jps-repertoires extract-situations` turns a run log into a
   file of situations and a separate file of the original decisions.
3. Production readers stream; the explicit convenience loader
   `load_records()` remains for tests and small diagnostic logs.
4. A Rust crate implements the same extraction and is checked against
   the Python command on shared fixtures.

## Non-goals

- A new log format. The run log stays JSON Lines; without observations a
  2C120 log is about 40 MB.
- Adapters for Jev or Laya (wording, choices, API calls). They are a
  separate piece of work that consumes the situation file.
- Measuring the effect of other choices on queue outcomes. That needs new
  simulations, not extraction.
- Shipping or packaging the Rust crate, or running it in CI.

## Anti-goals

- The original decision must never appear in the input given to another
  selector.
- An export that cannot be traced to its source log, or that silently
  overwrites or drops data.

## 1. Diagnostic mode

- `RunLog(path, metadata, *, diagnostic=False)`. `RunLog.observation()`
  writes only when `diagnostic` is true. All other record types are
  unchanged.
- The run metadata records `"diagnostic": true|false`.
- The scenario builders that create a `RunLog` (`scenario.py`, `demo.py`,
  `croma.py`) take `diagnostic: bool = False` and pass it on. The scripts
  in `scripts/` and `docs/scorecard.py` get `--diagnostic`.
- Document in `docs/model.md` (section on the run log) that analyses of
  what agents saw *between* decisions, such as the earlier no-gap
  investigation, need diagnostic mode.

## 2. Run metadata

Add where available, `null` otherwise:

- `code_revision`: git commit of this repository at run time
  (`git rev-parse HEAD` in the package's repository; `null` outside a
  checkout), with `"-dirty"` appended when tracked files have
  uncommitted changes (untracked files do not count).
- `input_checksum`: SHA-256 of the input data file, for scenarios that
  read one (2C120 trajectory file).

## 3. Streaming reader

- `iter_records(path, types=None)` in `jupedsim_repertoires/log.py`
  yields one decoded record at a time; with `types`, only records whose
  `type` is in that set.
- `ReplaySelector`, `transitions_by_agent()` and the scripts that count
  record types use it. `load_records()` stays for diagnosis and tests.
- This closes the reading part of issue #4.

## 4. `extract-situations`

### Command

```
jps-repertoires extract-situations RUN.jsonl --output SITUATIONS.jsonl
    [--sample N --seed S] [--overwrite]
```

`jps-repertoires` is a console script in `pyproject.toml`
(`[project.scripts]`), with subcommands so later tools can join it. No new
dependency.

### Outputs

For `--output situations.jsonl`:

| File | Content |
|---|---|
| `situations.jsonl` | one situation per line |
| `situations.labels.jsonl` | one label per situation, same keys, same order |
| `situations.manifest.json` | provenance and counts |

All three are written only if none exists, unless `--overwrite` is given.

Publication is not atomic across three files; the manifest is the
completion marker:

1. Validate the source and write situations and labels to temporary
   files in the output directory. An existing export stays untouched
   until this succeeds, so an invalid source log never invalidates it.
2. With `--overwrite`, delete the existing manifest, then rename the
   temporary situations and labels files into place.
3. Write the manifest last (temporary file, then rename). It holds the
   SHA-256 and byte size of both output files.

An interruption can leave a mixture of old and new situation and label
files, but never a manifest that matches them. Consumers must reject an
export whose manifest is absent or whose checksums do not match.

### Passes

`run_id` is known only after the whole log has been read, yet every
situation carries it. The extractor therefore reads the log twice:

1. **Validate and select.** Hash the whole file (`run_id`), hash the
   first line (`config_id`), check every rule below, count, and choose
   the keys to export (all, or the reservoir). Record the file's size
   and modification time before starting.
2. **Write.** Stream the log again. Write each selected request as a
   situation to the temporary situations file as it is read; keep the
   decision of each selected response (about 150 bytes each). After the
   pass, write the labels in situation order. Hash the file again during
   this pass.

If the second hash differs from `run_id`, or size or modification time
changed, the source changed during extraction: error, nothing published.

Memory: the key set of all requests and responses (two integers each,
for the checks), the selected keys, and the decisions of selected
responses. No request record is held after it has been written.

### Identifiers

- `run_id`: SHA-256 of the complete source log file. Identical log content
  gives the same ID.
- `config_id`: SHA-256 of the raw bytes of the log's first line (the
  metadata record, `"type": "metadata"` included, trailing newline
  excluded), exactly as written. No re-serialisation, so Rust and Python
  agree without reproducing Python's JSON formatting.
  *(Builder check, settled by Claude.)* It is a fingerprint of the
  metadata bytes, nothing more. It does not establish identical code or
  configuration: `code_revision` can be `null`, different uncommitted
  changes share the same `-dirty` suffix, and the metadata may not hold
  every parameter. The `diagnostic` flag is part of the metadata, so a
  diagnostic run of the same configuration gets a different
  `config_id`.
- Situation key: `(run_id, unit_index, decision_index)`. `unit_id` is
  kept as information.

### Situation record

Everything the selector could know at decision time, taken from the
`request` record, and nothing else:

```json
{"run_id": "...", "config_id": "...",
 "unit_index": 0, "unit_id": 1, "decision_index": 0,
 "snapshot_time": 0.0,
 "members": [1],
 "states": [...], "observations": [...], "events": [...]}
```

`states` carries the current repertoire and `commitment_since`;
`observations` carries each member's perception and memory; `events`
the triggering events. The `type` key is dropped. The response is never
part of it.

### Label record

```json
{"run_id": "...", "unit_index": 0, "decision_index": 0,
 "decision": {"repertoires": ["queueing"], "reasons": []}}
```

If the request has no response (selector failed, run stopped),
`"decision": null` and `"missing": "no response"`. The original decision
is a baseline to compare against, not ground truth.

### Manifest

```json
{"schema_version": 1,
 "extractor": "jps-repertoires extract-situations",
 "extractor_version": "<package version>",
 "source": {"path": "...", "run_id": "...", "config_id": "...",
            "bytes": 0},
 "outputs": {"situations": {"sha256": "...", "bytes": 0},
             "labels": {"sha256": "...", "bytes": 0}},
 "metadata": {...},
 "sampling": null | {"algorithm": "reservoir-r/splitmix64",
                     "size": 200, "seed": 42},
 "counts": {"requests": 0, "responses": 0, "situations": 0,
            "labels": 0, "missing_labels": 0}}
```

`metadata` is a copy of the run's metadata record, so code revision and
input checksum travel with the export.

### Rules

- Default: every request, including decisions to keep the current
  repertoire, in log order.
- A request is one whole decision unit with all its members; it is never
  split.
- Duplicate key in `request` or in `response` records: error, nothing
  written.
- A response without a request: error.
- Missing metadata record or a line that is not JSON: error with the
  line number.
- Logs are strict JSON: `RunLog` writes with `allow_nan=False`, so a NaN
  or infinity fails at write time, and the extractor rejects `NaN` and
  `Infinity` as not JSON. Current logs contain none.
  *(Builder check, settled by Claude.)*
- The duplicate and orphan checks cover all requests and responses in the
  log, also under `--sample`. They keep a set of keys (two integers per
  record, about 6.6 k requests for 2C120). This set grows with the log;
  only the sampling reservoir is bounded by N.
  *(Builder check, settled by Claude.)*
- `counts.requests` and `counts.responses`: all in the log;
  `counts.situations`, `counts.labels`, `counts.missing_labels`: in the
  output.

### Sampling

- `--sample N --seed S`: uniform sampling of N requests without
  replacement, output in original log order. If the log has at most N
  requests, all are kept. `N` is an integer ≥ 1; `S` an integer with
  0 ≤ S < 2⁶⁴. Anything else is a usage error. `--seed` without
  `--sample` is a usage error; `--sample` without `--seed` uses S = 0.
- Algorithm R reservoir sampling over request keys in pass 1, so the
  reservoir is bounded by N. The random numbers come from SplitMix64,
  implemented in the package (a few lines), not from Python's `random`,
  so that the Rust twin selects exactly the same requests.
- SplitMix64, all arithmetic modulo 2⁶⁴ (wrapping), state initialised
  to S:

  ```
  next_u64():
      state = state + 0x9E3779B97F4A7C15
      z = state
      z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
      z = (z ^ (z >> 27)) * 0x94D049BB133111EB
      return z ^ (z >> 31)
  ```

  Test vectors, first three outputs:
  S = 0: `0xE220A8397B1DCDAF`, `0x6E789E6AA1B965F4`,
  `0x06C45D188009454F`;
  S = 42: `0xBDD732262FEB6E95`, `0x28EFE333B266F103`,
  `0x47526757130F9F52`.
- Uniform integer in [0, m) by rejection, so the sample is exactly
  uniform: `limit = 2⁶⁴ − (2⁶⁴ mod m)`; draw `u = next_u64()` until
  `u < limit`; return `u mod m`. `limit` can equal 2⁶⁴, which does not
  fit in `u64`: Rust computes it in `u128` (the generator itself stays
  wrapping `u64`).
- For the i-th request (0-based): if i < N, put it in slot i; otherwise
  `j = uniform(i + 1)`, and if `j < N`, replace slot `j`.
- A shared fixture pins the selected keys for one log, N and S, so both
  implementations are checked against the same expected selection.
- Document in the command help and in `docs/model.md`: the sample is
  uniform over decision *requests*. Agents who are asked more often
  (more reconsiderations) contribute more situations; it is not an equal
  sample of people or of time.

## 5. Rust twin

- Crate at `rust/extract-situations/` (binary `extract-situations`), its
  own `Cargo.toml`, dependencies `serde`, `serde_json`, `sha2`, `clap`.
  Not part of the Python package, not built by `uv sync`.
- Same command-line contract as the Python command (without the
  `jps-repertoires` prefix).
- Agreement with Python is checked on shared fixtures in
  `tests/fixtures/situations/` (small logs: complete run, missing
  response, duplicate key, response without request, sampling with
  N smaller and larger than the request count):
  - identical selected keys, in the same order;
  - identical situation, label and manifest records when compared as
    parsed JSON (not byte for byte), except `extractor`,
    `extractor_version`, `source.path` and `outputs` (the output
    checksums depend on each implementation's JSON formatting); `run_id`
    and `config_id` must match;
  - each implementation's manifest checksums match its own output files;
  - the same error case fails in both, with the same error category.
- Failure-path tests (Python): source file changed between passes,
  publication interrupted after the data files but before the manifest,
  manifest checksum not matching its files, and `--overwrite` with an
  invalid source leaving the previous export intact.
- A Python test runs the Rust binary on the fixtures when it is on
  `PATH` and is skipped otherwise.

## Order

1. Diagnostic mode and run metadata.
2. Streaming reader.
3. `extract-situations` with fixtures and tests.
4. Rust twin against the same fixtures.

## Left to the builder

Internal function names and module layout inside `jupedsim_repertoires`
and the CLI module, error message wording, the error categories' names,
and how `code_revision` is found.
