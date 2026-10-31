"""GIF of a 2C120 run with the rules, coloured by behaviour.

The corridor is drawn rotated, walking direction left to right; the
door is drawn red while closed. With a wait slack, queueing agents that
keep their place are shown as "waiting".

Usage:
    gif_2c120.py MODEL OUT.gif [--data FILE] [--wait-slack none|VALUE]
        [--seed N]

Run with `uv run python` from the repository root (see README).
"""

import argparse
import dataclasses
import pathlib

import jupedsim as jps
import matplotlib.pyplot as plt
import shapely
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Polygon

from repertoire_examples import EntranceRuleSelector, RuleParameters
from repertoire_examples.croma import (
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
MODELS = {
    "cfsm-v2": (jps.CollisionFreeSpeedModelV2, "Collision-free speed model V2"),
    "warpdriver": (jps.WarpDriverModel, "WarpDriver"),
}
COLOURS = {
    "waiting": "#9fc3e7",
    "queueing": "#4c72b0",
    "overtaking": "#dd8452",
    "exit": "#8c8c8c",
}


def label(state, waits):
    if state is None:
        return "exit"
    if waits and state.repertoire == "queueing" and state.execution == "standing":
        return "waiting"
    return state.repertoire


class FrameRecorder:
    """Observer of a 2C120 run that keeps a frame every 50 iterations."""

    def __init__(self, waits):
        self.frames = []
        self._waits = waits

    def __call__(self, sim, ctrl):
        if sim.iteration_count() % 50 != 0:
            return
        self.frames.append(
            (
                sim.elapsed_time(),
                [
                    (a.position[1], -a.position[0], label(ctrl.states.get(a.id), self._waits))
                    for a in sim.agents()
                ],
            )
        )


def record(model, entrance, data, seed=0):
    sim, ctrl, inflow = build_2c120(
        model(),
        entries=load_entries(data),
        selector=EntranceRuleSelector(RuleParameters(), entrance, corridor()),
        log_path=pathlib.Path("/dev/null"),
        entrance=entrance,
        speed_seed=seed,
    )
    waits = entrance.wait_slack is not None
    recorder = FrameRecorder(waits)
    run_2c120(sim, ctrl, inflow, 250.0, observe=recorder)
    return recorder.frames, waits


def animate(frames, waits, title, out):
    def rot(g):
        return shapely.affinity.affine_transform(g, [0, 1, -1, 0, 0, 0])

    area = rot(shapely.union(corridor(), shapely.box(-0.42, 19.5, 0.38, 20.0)))
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.plot(*area.exterior.xy, color="#2d3142", lw=1.2)
    ax.set_aspect("equal")
    ax.axis("off")
    for name, colour in COLOURS.items():
        if name != "waiting" or waits:
            ax.scatter([], [], color=colour, label=name)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    door_box = rot(shapely.box(-0.42, 19.57, 0.38, 20.0))
    door = Polygon(list(door_box.exterior.coords), fc="#d62728", ec="#d62728", alpha=0.85, zorder=4)
    ax.add_patch(door)
    dots = ax.scatter([], [], s=14)
    fig.tight_layout()

    def draw(k):
        t, pts = frames[k]
        dots.set_offsets([(x, y) for x, y, _ in pts] or [(-9, 0)])
        dots.set_color([COLOURS[r] for *_, r in pts] or ["white"])
        door.set_visible(t < ENTRANCE.door_open_time)
        ax.set_title(f"{title}   t = {t:.0f} s", loc="left", color="#2d3142", fontsize=10)

    FuncAnimation(fig, draw, frames=len(frames)).save(out, writer=PillowWriter(fps=10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=sorted(MODELS))
    parser.add_argument("out", type=pathlib.Path)
    parser.add_argument(
        "--data", type=pathlib.Path, default=DATA, help="2C120 PeTrack file"
    )
    parser.add_argument("--wait-slack", default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    entrance = ENTRANCE
    if args.wait_slack is not None:
        slack = None if args.wait_slack == "none" else float(args.wait_slack)
        entrance = dataclasses.replace(ENTRANCE, wait_slack=slack)
    model, title = MODELS[args.model]
    frames, waits = record(model, entrance, args.data, args.seed)
    animate(frames, waits, title, args.out)
    print(f"{args.model}: {frames[-1][0]:.1f} s, {len(frames)} frames -> {args.out}")


if __name__ == "__main__":
    main()
