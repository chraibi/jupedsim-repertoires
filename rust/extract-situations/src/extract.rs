// SPDX-License-Identifier: LGPL-3.0-or-later

//! Two-pass extraction of situations and labels from a run log.
//!
//! Pass 1 hashes and validates the whole log and collects the request
//! keys. Pass 2 re-reads the log and writes the selected situations.

use std::collections::{HashMap, HashSet};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::splitmix::reservoir;

const ALGORITHM: &str = "reservoir-r/splitmix64";

/// `(unit_index, decision_index)` of a decision request.
type Key = (i64, i64);

/// A JSON object, with keys in sorted order.
type Record = Map<String, Value>;

/// A failure with one of the documented error categories.
#[derive(Debug)]
pub struct ExtractError {
    /// One of `exists`, `no-metadata`, `not-json`, `duplicate-request`,
    /// `duplicate-response`, `orphan-response`, `source-changed` or `io`.
    pub category: &'static str,
    pub message: String,
}

impl ExtractError {
    fn new(category: &'static str, message: impl Into<String>) -> Self {
        ExtractError {
            category,
            message: message.into(),
        }
    }
}

impl fmt::Display for ExtractError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "error[{}]: {}", self.category, self.message)
    }
}

impl From<io::Error> for ExtractError {
    fn from(err: io::Error) -> Self {
        ExtractError::new("io", err.to_string())
    }
}

type Result<T> = std::result::Result<T, ExtractError>;

/// Settings of one extraction.
pub struct Options {
    /// Number of requests to sample; all requests when `None`.
    pub sample: Option<u64>,
    /// Seed of the sample.
    pub seed: u64,
    /// Replace an existing export.
    pub overwrite: bool,
}

/// The three files of an export.
struct Paths {
    situations: PathBuf,
    labels: PathBuf,
    manifest: PathBuf,
}

/// Return the situations, labels and manifest paths for `output`.
///
/// Fails with a message if `output` does not end in `.jsonl`.
fn paths_for(output: &Path) -> std::result::Result<Paths, String> {
    if output.extension().and_then(|e| e.to_str()) != Some("jsonl") {
        return Err(format!("output must end in .jsonl, got {}", output.display()));
    }
    Ok(Paths {
        situations: output.to_path_buf(),
        labels: output.with_extension("labels.jsonl"),
        manifest: output.with_extension("manifest.json"),
    })
}

/// Check that `output` is a valid situations path (ends in `.jsonl`).
pub fn output_paths(output: &Path) -> std::result::Result<(), String> {
    paths_for(output).map(|_| ())
}

/// Temporary files that are removed when the value is dropped.
///
/// Files that were renamed already are gone, so removing them fails silently.
struct Temps {
    directory: PathBuf,
    base: String,
    paths: Vec<PathBuf>,
}

impl Temps {
    fn new(output: &Path) -> Self {
        let directory = match output.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => parent.to_path_buf(),
            _ => PathBuf::from("."),
        };
        let base = output
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default();
        Temps {
            directory,
            base,
            paths: Vec::new(),
        }
    }

    /// Create a new empty temporary file next to the output.
    fn create(&mut self) -> Result<(PathBuf, File)> {
        let name = format!("{}.tmp{}-{}", self.base, std::process::id(), self.paths.len());
        let path = self.directory.join(name);
        let file = OpenOptions::new().write(true).create_new(true).open(&path)?;
        self.paths.push(path.clone());
        Ok((path, file))
    }
}

impl Drop for Temps {
    fn drop(&mut self) {
        for path in &self.paths {
            let _ = fs::remove_file(path);
        }
    }
}

/// Result of pass 1 over a run log.
struct Scan {
    size: u64,
    modified: SystemTime,
    run_id: String,
    config_id: String,
    metadata: Option<Record>,
    requests: Vec<Key>,
    request_set: HashSet<Key>,
    /// Responses in log order with their line numbers.
    responses: Vec<(Key, usize)>,
    response_set: HashSet<Key>,
}

fn hex(digest: Sha256) -> String {
    format!("{:x}", digest.finalize())
}

/// Call `visit(line_number, line)` for every line (1-based, with its
/// newline) and return the SHA-256 of the whole file.
fn read_lines(path: &Path, mut visit: impl FnMut(usize, &[u8]) -> Result<()>) -> Result<String> {
    let mut reader = BufReader::new(File::open(path)?);
    let mut digest = Sha256::new();
    let mut line = Vec::new();
    let mut number = 0;
    loop {
        line.clear();
        if reader.read_until(b'\n', &mut line)? == 0 {
            return Ok(hex(digest));
        }
        number += 1;
        digest.update(&line);
        visit(number, &line)?;
    }
}

fn parse(number: usize, line: &[u8]) -> Result<Record> {
    match serde_json::from_slice::<Value>(line) {
        Ok(Value::Object(record)) => Ok(record),
        Ok(_) => Err(ExtractError::new(
            "not-json",
            format!("line {number}: record is not an object"),
        )),
        Err(err) => Err(ExtractError::new("not-json", format!("line {number}: {err}"))),
    }
}

fn key_of(number: usize, record: &Record) -> Result<Key> {
    let index = |name: &str| record.get(name).and_then(Value::as_i64);
    match (index("unit_index"), index("decision_index")) {
        (Some(unit), Some(decision)) => Ok((unit, decision)),
        _ => Err(ExtractError::new(
            "not-json",
            format!("line {number}: unit_index and decision_index must be integers"),
        )),
    }
}

/// The decision of a response: its repertoires and reasons.
fn decision_of(number: usize, record: &Record) -> Result<Value> {
    let repertoires = match record.get("repertoires") {
        Some(list @ Value::Array(_)) => list.clone(),
        _ => {
            return Err(ExtractError::new(
                "not-json",
                format!("line {number}: response lacks a repertoires list"),
            ))
        }
    };
    let reasons = record.get("reasons").cloned().unwrap_or_else(|| json!([]));
    Ok(json!({ "repertoires": repertoires, "reasons": reasons }))
}

impl Scan {
    fn new(size: u64, modified: SystemTime) -> Self {
        Scan {
            size,
            modified,
            run_id: String::new(),
            config_id: String::new(),
            metadata: None,
            requests: Vec::new(),
            request_set: HashSet::new(),
            responses: Vec::new(),
            response_set: HashSet::new(),
        }
    }

    fn add_line(&mut self, number: usize, line: &[u8]) -> Result<()> {
        let record = parse(number, line)?;
        if number == 1 {
            return self.add_metadata(record, line);
        }
        match record.get("type").and_then(Value::as_str) {
            Some("request") => self.add_request(number, &record),
            Some("response") => self.add_response(number, &record),
            _ => Ok(()),
        }
    }

    fn add_metadata(&mut self, record: Record, line: &[u8]) -> Result<()> {
        if record.get("type").and_then(Value::as_str) != Some("metadata") {
            return Err(ExtractError::new("no-metadata", "line 1 is not a metadata record"));
        }
        let first = line.strip_suffix(b"\n").unwrap_or(line);
        self.config_id = hex(Sha256::new().chain_update(first));
        self.metadata = Some(record);
        Ok(())
    }

    fn add_request(&mut self, number: usize, record: &Record) -> Result<()> {
        let key = key_of(number, record)?;
        if !self.request_set.insert(key) {
            return Err(ExtractError::new(
                "duplicate-request",
                format!("line {number}: duplicate request {key:?}"),
            ));
        }
        self.requests.push(key);
        Ok(())
    }

    fn add_response(&mut self, number: usize, record: &Record) -> Result<()> {
        let key = key_of(number, record)?;
        decision_of(number, record)?;
        if !self.response_set.insert(key) {
            return Err(ExtractError::new(
                "duplicate-response",
                format!("line {number}: duplicate response {key:?}"),
            ));
        }
        self.responses.push((key, number));
        Ok(())
    }

    fn check_orphans(&self) -> Result<()> {
        for (key, number) in &self.responses {
            if !self.request_set.contains(key) {
                return Err(ExtractError::new(
                    "orphan-response",
                    format!("line {number}: response {key:?} has no request"),
                ));
            }
        }
        Ok(())
    }
}

/// Pass 1: hash, validate and collect the keys of a run log.
fn scan(source: &Path) -> Result<Scan> {
    let stat = fs::metadata(source)?;
    let mut scan = Scan::new(stat.len(), stat.modified()?);
    scan.run_id = read_lines(source, |number, line| scan.add_line(number, line))?;
    if scan.metadata.is_none() {
        return Err(ExtractError::new("no-metadata", "the log has no metadata record"));
    }
    scan.check_orphans()?;
    Ok(scan)
}

fn select(scan: &Scan, options: &Options) -> Vec<Key> {
    match options.sample {
        None => scan.requests.clone(),
        Some(size) => reservoir(&scan.requests, size as usize, options.seed),
    }
}

fn check_unchanged(source: &Path, scan: &Scan) -> Result<()> {
    let stat = fs::metadata(source)?;
    if stat.len() != scan.size || stat.modified()? != scan.modified {
        return Err(changed(source));
    }
    Ok(())
}

fn changed(source: &Path) -> ExtractError {
    ExtractError::new(
        "source-changed",
        format!("{} changed during extraction", source.display()),
    )
}

/// One JSON line; keys are sorted because `Map` is a `BTreeMap`.
fn dump(record: &Value) -> String {
    format!("{record}\n")
}

/// The situation for a request: everything but its type, plus the ids.
fn situation_of(mut request: Record, scan: &Scan) -> Value {
    request.remove("type");
    request.insert("run_id".into(), json!(scan.run_id));
    request.insert("config_id".into(), json!(scan.config_id));
    Value::Object(request)
}

/// Pass 2: write the selected situations, return the selected decisions.
fn pass_two(
    source: &Path,
    scan: &Scan,
    selected: &HashSet<Key>,
    out: &mut impl Write,
) -> Result<HashMap<Key, Value>> {
    check_unchanged(source, scan)?;
    let mut decisions = HashMap::new();
    let run_id = read_lines(source, |number, line| {
        if number == 1 {
            return Ok(());
        }
        let record = parse(number, line)?;
        let kind = record.get("type").and_then(Value::as_str);
        if kind != Some("request") && kind != Some("response") {
            return Ok(());
        }
        let key = key_of(number, &record)?;
        if !selected.contains(&key) {
            return Ok(());
        }
        if kind == Some("response") {
            decisions.insert(key, decision_of(number, &record)?);
            return Ok(());
        }
        out.write_all(dump(&situation_of(record, scan)).as_bytes())?;
        Ok(())
    })?;
    if run_id != scan.run_id {
        return Err(changed(source));
    }
    Ok(decisions)
}

fn label_of(scan: &Scan, key: Key, decisions: &HashMap<Key, Value>) -> Value {
    let mut label = json!({
        "run_id": scan.run_id,
        "unit_index": key.0,
        "decision_index": key.1,
        "decision": decisions.get(&key),
    });
    if !decisions.contains_key(&key) {
        label["missing"] = json!("no response");
    }
    label
}

/// Write situations and labels to temporary files; return their paths and
/// the number of labels without a response.
fn write_outputs(
    source: &Path,
    scan: &Scan,
    selected: &[Key],
    temps: &mut Temps,
) -> Result<(PathBuf, PathBuf, usize)> {
    let (sit_path, sit_file) = temps.create()?;
    let mut sit_out = BufWriter::new(sit_file);
    let set: HashSet<Key> = selected.iter().copied().collect();
    let decisions = pass_two(source, scan, &set, &mut sit_out)?;
    sit_out.flush()?;
    check_unchanged(source, scan)?;
    let (lab_path, lab_file) = temps.create()?;
    let mut lab_out = BufWriter::new(lab_file);
    for key in selected {
        lab_out.write_all(dump(&label_of(scan, *key, &decisions)).as_bytes())?;
    }
    lab_out.flush()?;
    let missing = selected.iter().filter(|k| !decisions.contains_key(k)).count();
    Ok((sit_path, lab_path, missing))
}

fn file_entry(path: &Path) -> Result<Value> {
    let mut digest = Sha256::new();
    io::copy(&mut File::open(path)?, &mut digest)?;
    Ok(json!({ "sha256": hex(digest), "bytes": fs::metadata(path)?.len() }))
}

fn manifest_of(
    source: &Path,
    scan: &Scan,
    options: &Options,
    files: (&Path, &Path),
    counts: (usize, usize),
) -> Result<Value> {
    let sampling = options.sample.map(|size| {
        json!({ "algorithm": ALGORITHM, "size": size, "seed": options.seed })
    });
    let (selected, missing) = counts;
    Ok(json!({
        "schema_version": 1,
        "extractor": "extract-situations",
        "extractor_version": env!("CARGO_PKG_VERSION"),
        "source": {
            "path": source.to_string_lossy(),
            "run_id": scan.run_id,
            "config_id": scan.config_id,
            "bytes": scan.size,
        },
        "outputs": {
            "situations": file_entry(files.0)?,
            "labels": file_entry(files.1)?,
        },
        "metadata": scan.metadata,
        "sampling": sampling,
        "counts": {
            "requests": scan.requests.len(),
            "responses": scan.responses.len(),
            "situations": selected,
            "labels": selected,
            "missing_labels": missing,
        },
    }))
}

fn check_absent(paths: &Paths) -> Result<()> {
    for path in [&paths.situations, &paths.labels, &paths.manifest] {
        if path.exists() {
            return Err(ExtractError::new(
                "exists",
                format!("{} exists; pass --overwrite to replace it", path.display()),
            ));
        }
    }
    Ok(())
}

/// Rename the data files, then write the manifest last through a temp file.
fn publish(
    paths: &Paths,
    files: (&Path, &Path),
    manifest: &Value,
    options: &Options,
    temps: &mut Temps,
) -> Result<()> {
    if options.overwrite {
        let _ = fs::remove_file(&paths.manifest);
    } else {
        check_absent(paths)?;
    }
    fs::rename(files.0, &paths.situations)?;
    fs::rename(files.1, &paths.labels)?;
    let (temp, mut file) = temps.create()?;
    writeln!(file, "{}", serde_json::to_string_pretty(manifest).map_err(io::Error::from)?)?;
    drop(file);
    fs::rename(temp, &paths.manifest)?;
    Ok(())
}

/// Export the requests of the run log `source` as situations and labels.
///
/// `output` must end in `.jsonl` (see [`output_paths`]); the labels and
/// manifest files are written next to it, the manifest last.
pub fn extract_situations(source: &Path, output: &Path, options: &Options) -> Result<()> {
    let paths = paths_for(output).map_err(|msg| ExtractError::new("io", msg))?;
    if !options.overwrite {
        check_absent(&paths)?;
    }
    let scan = scan(source)?;
    let selected = select(&scan, options);
    let mut temps = Temps::new(output);
    let (sit_tmp, lab_tmp, missing) = write_outputs(source, &scan, &selected, &mut temps)?;
    let files = (sit_tmp.as_path(), lab_tmp.as_path());
    let manifest = manifest_of(source, &scan, options, files, (selected.len(), missing))?;
    publish(&paths, files, &manifest, options, &mut temps)
}
