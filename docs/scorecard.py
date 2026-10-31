"""Scorecard of a model version against experiment 2C120.

Runs 2C120 with the rule selector and writes one JSON file with:
- movement in the last 40 s before the door opens (per person present
  for all of it, median over people): distance walked, sideways
  movement and share of time moving;
- outflow after the door opens: removal times of the 25th, 50th and 75th
  person and of the last one, and the largest difference in the number
  of people out compared with the experiment;
- event counts from the run log.

The same smoothing (1 s moving average of positions sampled every 0.1 s)
is applied to the simulation and to the head trajectories of the people.

Usage:
    scorecard.py experiment OUT.json
    scorecard.py MODEL OUT.json [--wait-slack none|VALUE]
        [--queue-speed V --overtake-speed V] [--desired-speeds none|LO,HI]
        [--seeds N]

With --seeds N the run is repeated with speed seeds 0..N-1; the card
holds the median of every number over the seeds and the per-seed cards.

Run with `uv run python` from the repository root (see README).
"""

import argparse
import collections
import dataclasses
import json
import pathlib

import jupedsim as jps
import numpy as np

from repertoire_examples import EntranceRuleSelector, RuleParameters
from repertoire_examples.croma import (
    DESIRED_SPEEDS,
    DOOR_OPEN_TIME,
    ENTRANCE,
    build_2c120,
    corridor,
    load_entries,
    run_2c120,
)

DATA = pathlib.Path(
    "/Users/chraibi/workspace/Writing/Motivation/motivation_code/"
    "trajectories_croma/2C120_cam6_cam5_frameshift0_Combined.txt"
)
DOOR_Y = 20.0
WINDOW = 400  # samples of 0.1 s: the last 40 s before the door opens
MODELS = {
    "cfsm-v2": jps.CollisionFreeSpeedModelV2,
    "warpdriver": jps.WarpDriverModel,
}


def movement(tracks, entrance):
    """Median distance, sideways movement (m/min) and moving share."""
    rows = []
    kernel = np.ones(10) / 10
    for p in tracks.values():
        if len(p) < WINDOW:
            continue
        p = p[-WINDOW:]
        p = np.column_stack(
            [np.convolve(p[:, k], kernel, "valid") for k in (0, 1)]
        )
        d = np.diff(p, axis=0)
        u = entrance - p[:-1]
        u /= np.linalg.norm(u, axis=1)[:, None]
        lateral = np.abs(d[:, 0] * u[:, 1] - d[:, 1] * u[:, 0])
        step = np.linalg.norm(d, axis=1)
        minutes = len(d) * 0.1 / 60
        rows.append(
            [step.sum() / minutes, lateral.sum() / minutes, np.mean(step > 0.01)]
        )
    med = np.median(rows, axis=0)
    return {
        "people_waiting": len(rows),
        "walked_m_per_min": round(med[0], 2),
        "sideways_m_per_min": round(med[1], 2),
        "moving_share": round(med[2], 2),
    }


def outflow(times, reference=None):
    times = np.sort(times)
    out = {
        "person_25": round(times[24], 1),
        "person_50": round(times[49], 1),
        "person_75": round(times[74], 1),
        "last": round(times[-1], 1),
    }
    if reference is not None:
        grid = np.arange(DOOR_OPEN_TIME, 250, 0.1)
        n = np.searchsorted(times, grid, side="right")
        n_ref = np.searchsorted(reference, grid, side="right")
        out["max_count_difference"] = int(np.abs(n - n_ref).max())
    return out


def experiment():
    d = np.loadtxt(DATA, comments="#")
    d = d[d[:, 1] % 5 == 0]
    # Simulation time starts at the first recorded frame, as in load_entries.
    t = (d[:, 1] - d[:, 1].min()) / 50
    waiting = d[(t < DOOR_OPEN_TIME) & (d[:, 3] < DOOR_Y)]
    tracks = {}
    for i in np.unique(waiting[:, 0]):
        rows = waiting[waiting[:, 0] == i]
        tracks[i] = rows[np.argsort(rows[:, 1])][:, 2:4]
    crossings = []
    for i in np.unique(d[:, 0]):
        rows = d[(d[:, 0] == i) & (t > DOOR_OPEN_TIME) & (d[:, 3] >= DOOR_Y)]
        if len(rows):
            crossings.append(t[(d[:, 0] == i) & (t > DOOR_OPEN_TIME) & (d[:, 3] >= DOOR_Y)].min())
    return tracks, np.array(crossings)


def simulate(model, entrance, log_path, desired_speeds=DESIRED_SPEEDS, seed=0):
    sim, ctrl, inflow = build_2c120(
        MODELS[model](),
        entries=load_entries(DATA),
        selector=EntranceRuleSelector(RuleParameters(), entrance, corridor()),
        log_path=log_path,
        entrance=entrance,
        desired_speeds=desired_speeds,
        speed_seed=seed,
    )
    tracks, removed, alive = collections.defaultdict(list), [], set()
    step = ctrl.step

    def record():
        nonlocal alive
        now = {a.id for a in sim.agents()}
        removed.extend([sim.elapsed_time()] * len(alive - now))
        alive = now
        if sim.elapsed_time() < DOOR_OPEN_TIME:
            for a in sim.agents():
                if a.id in ctrl.states:
                    tracks[a.id].append(a.position)
        step()

    ctrl.step = record
    run_2c120(sim, ctrl, inflow, 300.0)
    removed.extend([sim.elapsed_time()] * len(alive))
    tracks = {i: np.array(p) for i, p in tracks.items()}
    return tracks, np.array(removed), dict(inflow.added)


def events(log_path):
    counts = collections.Counter()
    for line in open(log_path):
        rec = json.loads(line)
        for cause in str(rec.get("cause", "")).split(","):
            if cause.startswith("overtake_"):
                counts[cause] += 1
    return dict(counts)


def run(args, entrance, speeds, seed, crossings):
    """Card of one simulation run with the given speed seed."""
    log = args.out.with_suffix(".jsonl")
    if args.seeds > 1:
        log = args.out.with_suffix(f".seed{seed}.jsonl")
    tracks, removed, _ = simulate(args.model, entrance, log, speeds, seed)
    card = {"seed": seed}
    card |= movement(tracks, np.array(entrance.entrance))
    card |= outflow(removed, crossings)
    card["events"] = events(log)
    return card


def median(runs):
    """Median of every number over the runs, with the runs themselves."""
    keys = [k for k in runs[0] if k not in ("seed", "events")]
    card = {k: round(float(np.median([r[k] for r in runs])), 2) for k in keys}
    causes = sorted({c for r in runs for c in r["events"]})
    card["events"] = {
        c: float(np.median([r["events"].get(c, 0) for r in runs])) for c in causes
    }
    return card | {"seeds": len(runs), "per_seed": runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=["experiment", *MODELS])
    parser.add_argument("out", type=pathlib.Path)
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
    tracks, crossings = experiment()
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
