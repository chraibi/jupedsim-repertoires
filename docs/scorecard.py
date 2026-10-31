"""Scorecard of a model version against experiment 2C120.

Runs 2C120 with the rule selector and writes one JSON file with:
- movement in the last 40 s before the door opens (per person present
  for all of it, median over people): distance walked, sideways
  movement and share of time moving;
- outflow after the door opens: removal times of the 25th, 50th and 75th
  person and of the last one, and the largest difference in the number
  of people out compared with the experiment;
- completion: agents still inside and entries not yet added when the run
  stopped; a run with either is marked incomplete and its missing
  removal times are null;
- event counts from the run log.

The same smoothing (1 s moving average of positions sampled every 0.1 s)
is applied to the simulation and to the head trajectories of the people.

Usage:
    scorecard.py experiment OUT.json [--data FILE]
    scorecard.py MODEL OUT.json [--data FILE] [--wait-slack none|VALUE]
        [--queue-speed V --overtake-speed V] [--desired-speeds none|LO,HI]
        [--seeds N]

With --seeds N the run is repeated with speed seeds 0..N-1; the card
holds the median of every number over the seeds and the per-seed cards.

Run with `uv run python` from the repository root (see README).
"""

import argparse
import dataclasses
import json
import pathlib

import numpy as np

from repertoire_examples.croma import DESIRED_SPEEDS, ENTRANCE
from repertoire_examples.evaluation import (
    MODELS,
    card,
    experiment,
    median,
    movement,
    outflow,
)

DATA = pathlib.Path(
    "/Users/chraibi/workspace/Writing/Motivation/motivation_code/"
    "trajectories_croma/2C120_cam6_cam5_frameshift0_Combined.txt"
)


def run(args, entrance, speeds, seed, crossings):
    """Card of one simulation run with the given speed seed."""
    log = args.out.with_suffix(".jsonl")
    if args.seeds > 1:
        log = args.out.with_suffix(f".seed{seed}.jsonl")
    return card(args.model, entrance, log, args.data, crossings, speeds, seed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=["experiment", *MODELS])
    parser.add_argument("out", type=pathlib.Path)
    parser.add_argument(
        "--data", type=pathlib.Path, default=DATA, help="2C120 PeTrack file"
    )
    parser.add_argument("--wait-slack", default=None)
    parser.add_argument("--queue-speed", type=float, default=None)
    parser.add_argument("--overtake-speed", type=float, default=None)
    parser.add_argument("--desired-speeds", default=None)
    parser.add_argument("--seeds", type=int, default=1)
    args = parser.parse_args()
    entrance = ENTRANCE
    if args.wait_slack is not None:
        slack = None if args.wait_slack == "none" else float(args.wait_slack)
        entrance = dataclasses.replace(entrance, wait_slack=slack)
    if args.queue_speed is not None:
        entrance = dataclasses.replace(
            entrance,
            queue_speed=args.queue_speed,
            overtake_speed=args.overtake_speed,
        )
    speeds = DESIRED_SPEEDS
    if args.desired_speeds == "none":
        speeds = None
    elif args.desired_speeds is not None:
        speeds = tuple(float(v) for v in args.desired_speeds.split(","))
    tracks, crossings = experiment(args.data)
    card = {"model": args.model}
    if args.model == "experiment":
        card |= movement(tracks, np.array(ENTRANCE.entrance))
        card |= outflow(crossings)
    else:
        card["entrance"] = dataclasses.asdict(entrance)
        card["desired_speeds"] = speeds
        runs = [
            run(args, entrance, speeds, seed, np.sort(crossings))
            for seed in range(args.seeds)
        ]
        card |= runs[0] if len(runs) == 1 else median(runs)
    args.out.write_text(json.dumps(card, indent=2))
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
