# extract-situations

Rust twin of `jps-repertoires extract-situations`. It exports the decision
requests of a run log as situations plus labels and a manifest, with the
same options, files and error categories as the Python command.

```
cargo build --release
target/release/extract-situations RUN --output OUT.jsonl [--sample N] [--seed S] [--overwrite]
```

Errors print `error[<category>]: <message>` and exit 1; usage errors exit 2.

```
cargo test                       # SplitMix64 and reservoir vectors
PATH=$PWD/target/release:$PATH   # then run pytest from the repository root:
pytest tests/layer/test_situations_rust.py
```

The parity test compares both implementations on `tests/fixtures/situations/`
and is skipped when `extract-situations` is not on `PATH`.
