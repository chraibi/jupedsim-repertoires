// SPDX-License-Identifier: LGPL-3.0-or-later

//! Command line entry point of `extract-situations`.

mod extract;
mod splitmix;

use std::path::PathBuf;
use std::process::ExitCode;

use clap::error::ErrorKind;
use clap::{CommandFactory, Parser};

use extract::{extract_situations, check_output_path, Options};

/// Export the decision requests of a run log as situations with labels.
#[derive(Parser)]
#[command(name = "extract-situations", version)]
struct Args {
    /// Run log (JSON Lines)
    run: PathBuf,

    /// Situations file ending in .jsonl; labels and manifest are written next to it
    #[arg(long)]
    output: PathBuf,

    /// Export N requests, uniform over decision requests, not over people or time
    #[arg(long, value_name = "N", value_parser = clap::value_parser!(u64).range(1..))]
    sample: Option<u64>,

    /// Seed of the sample, 0 <= S < 2**64 (default 0; needs --sample)
    #[arg(long, value_name = "S", requires = "sample")]
    seed: Option<u64>,

    /// Replace an existing export
    #[arg(long)]
    overwrite: bool,
}

fn main() -> ExitCode {
    let args = Args::parse();
    if let Err(message) = check_output_path(&args.output) {
        Args::command().error(ErrorKind::ValueValidation, message).exit();
    }
    let options = Options {
        sample: args.sample,
        seed: args.seed.unwrap_or(0),
        overwrite: args.overwrite,
    };
    match extract_situations(&args.run, &args.output, &options) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("{err}");
            ExitCode::from(1)
        }
    }
}
