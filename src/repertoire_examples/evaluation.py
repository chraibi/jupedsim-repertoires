# SPDX-License-Identifier: LGPL-3.0-or-later
"""Evaluation of 2C120 runs against the experiment.

Movement in the last 40 s before the door opens, outflow after it opens,
completion of a run and medians over speed seeds. The same smoothing
(1 s moving average of positions sampled every 0.1 s) is applied to the
simulation and to the head trajectories of the people.
"""

import collections
import json
import pathlib

import jupedsim as jps
import numpy as np

from .croma import (
    DESIRED_SPEEDS,
    DOOR_OPEN_TIME,
    build_2c120,
    corridor,
    load_entries,
    run_2c120,
)
from .entrance import EntranceParameters
from .rules import EntranceRuleSelector, RuleParameters

DOOR_Y = 20.0
WINDOW = 400  # samples of 0.1 s: the last 40 s before the door opens
MAX_TIME = 300.0
MODELS = {
    "cfsm-v2": jps.CollisionFreeSpeedModelV2,
    "warpdriver": jps.WarpDriverModel,
}


def movement(tracks, entrance):
    """Median distance, sideways movement (m/min) and moving share."""
    rows = [_movement_row(p, entrance) for p in tracks.values()]
    rows = [r for r in rows if r is not None]
    med = np.median(rows, axis=0)
    return {
        "people_waiting": len(rows),
        "walked_m_per_min": round(med[0], 2),
        "sideways_m_per_min": round(med[1], 2),
        "moving_share": round(med[2], 2),
    }


def _movement_row(p, entrance):
    """Distance, sideways movement and moving share of one track."""
    if len(p) < WINDOW:
        return None
    p = p[-WINDOW:]
    kernel = np.ones(10) / 10
    p = np.column_stack(
        [np.convolve(p[:, k], kernel, "valid") for k in (0, 1)]
    )
    d = np.diff(p, axis=0)
    u = entrance - p[:-1]
    u /= np.linalg.norm(u, axis=1)[:, None]
    lateral = np.abs(d[:, 0] * u[:, 1] - d[:, 1] * u[:, 0])
    step = np.linalg.norm(d, axis=1)
    minutes = len(d) * 0.1 / 60
    return [step.sum() / minutes, lateral.sum() / minutes, np.mean(step > 0.01)]


def outflow(times, reference=None, complete=True):
    """Removal times of the 25th, 50th, 75th and last person.

    With ``reference`` (sorted removal times of the experiment), also
    the largest difference in the number of people out.
    """
    times = np.sort(times)
    out = {
        "person_25": nth(times, 25),
        "person_50": nth(times, 50),
        "person_75": nth(times, 75),
        "last": round(times[-1], 1) if complete else None,
    }
    if reference is not None:
        grid = np.arange(DOOR_OPEN_TIME, 250, 0.1)
        n = np.searchsorted(times, grid, side="right")
        n_ref = np.searchsorted(reference, grid, side="right")
        out["max_count_difference"] = int(np.abs(n - n_ref).max())
    return out


def nth(times, n):
    """Removal time of the n-th person, None if fewer were removed."""
    return round(times[n - 1], 1) if len(times) >= n else None


def experiment(data):
    """Tracks while waiting and door crossing times of the people."""
    d = np.loadtxt(data, comments="#", ndmin=2)
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
        out = (d[:, 0] == i) & (t > DOOR_OPEN_TIME) & (d[:, 3] >= DOOR_Y)
        if out.any():
            crossings.append(t[out].min())
    return tracks, np.array(crossings)


class Recorder:
    """Observer of a 2C120 run for :func:`run_2c120`.

    Records the positions of controlled agents before the door opens and
    the time at which each agent is first seen to have left.
    """

    def __init__(self):
        self.tracks = collections.defaultdict(list)
        self.removed = []
        self._alive = set()

    def __call__(self, sim, controller):
        now = {a.id for a in sim.agents()}
        self.removed.extend([sim.elapsed_time()] * len(self._alive - now))
        self._alive = now
        if sim.elapsed_time() >= DOOR_OPEN_TIME:
            return
        for a in sim.agents():
            if a.id in controller.states:
                self.tracks[a.id].append(a.position)


def simulate(
    model, entrance, log_path, data, desired_speeds=DESIRED_SPEEDS, seed=0
):
    """Run 2C120; removal times hold only agents that actually left."""
    sim, ctrl, inflow = build_2c120(
        MODELS[model](),
        entries=load_entries(data),
        selector=EntranceRuleSelector(RuleParameters(), entrance, corridor()),
        log_path=log_path,
        entrance=entrance,
        desired_speeds=desired_speeds,
        speed_seed=seed,
    )
    recorder = Recorder()
    run_2c120(sim, ctrl, inflow, MAX_TIME, observe=recorder)
    tracks = {i: np.array(p) for i, p in recorder.tracks.items()}
    return tracks, np.array(recorder.removed), dict(inflow.added)


def completion(n_entries, n_added, n_removed):
    """Agents still inside, entries not yet added and whether neither."""
    remaining = n_added - n_removed
    pending = n_entries - n_added
    return {
        "remaining": remaining,
        "pending": pending,
        "completed": remaining == 0 and pending == 0,
    }


def events(log_path):
    """Number of overtaking events of each cause in a run log."""
    counts = collections.Counter()
    for line in open(log_path):
        rec = json.loads(line)
        for cause in str(rec.get("cause", "")).split(","):
            if cause.startswith("overtake_"):
                counts[cause] += 1
    return dict(counts)


def card(
    model,
    entrance: EntranceParameters,
    log_path: pathlib.Path,
    data: pathlib.Path,
    crossings,
    desired_speeds=DESIRED_SPEEDS,
    seed=0,
):
    """Card of one simulation run with the given speed seed."""
    tracks, removed, added = simulate(
        model, entrance, log_path, data, desired_speeds, seed
    )
    out = {"seed": seed}
    out |= movement(tracks, np.array(entrance.entrance))
    out |= completion(len(load_entries(data)), len(added), len(removed))
    out |= outflow(removed, crossings, out["completed"])
    out["events"] = events(log_path)
    return out


def median(runs):
    """Median of every number over the runs, with the runs themselves."""
    keys = [k for k in runs[0] if k not in ("seed", "events", "completed")]
    out = {k: median_of([r[k] for r in runs]) for k in keys}
    out["completed"] = all(r["completed"] for r in runs)
    causes = sorted({c for r in runs for c in r["events"]})
    out["events"] = {
        c: float(np.median([r["events"].get(c, 0) for r in runs]))
        for c in causes
    }
    return out | {"seeds": len(runs), "per_seed": runs}


def median_of(values):
    """Median rounded to 0.01, None if any run lacks the value."""
    if None in values:
        return None
    return round(float(np.median(values)), 2)
