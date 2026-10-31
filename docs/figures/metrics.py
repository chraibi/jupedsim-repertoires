"""Figure introducing the scorecard metrics, from version 0 with CFSM V2.

(a) One person's track while the door is closed, experiment and simulation.
(b) The same person's speed, with the 0.1 m/s threshold for "moving".
(c) Number of people out after the door opens, with quartile times and
    the largest gap.

Usage:
    metrics.py [--data FILE]

Run with `uv run python` from the repository root (see README).
"""

import argparse
import dataclasses
import pathlib

import matplotlib.pyplot as plt
import numpy as np

from repertoire_examples.croma import DOOR_OPEN_TIME, ENTRANCE
from repertoire_examples.evaluation import experiment, simulate

DATA = pathlib.Path(
    "/Users/chraibi/workspace/Writing/Motivation/motivation_code/"
    "trajectories_croma/2C120_cam6_cam5_frameshift0_Combined.txt"
)

EXP = "#2d3142"
SIM = "#4575b4"


def smooth(p):
    kernel = np.ones(10) / 10
    return np.column_stack([np.convolve(p[:, k], kernel, "valid") for k in (0, 1)])


def pick_person(exp_tracks, sim_tracks, added, window=400):
    """A person with a median-length wait and the agent that replays them.

    Only the last ``window`` samples (0.1 s each) before the door opens
    are kept, when the person stands in the queue.
    """
    ids = sorted(exp_tracks, key=lambda i: len(exp_tracks[i]))
    person = ids[len(ids) // 2]
    return exp_tracks[person][-window:], sim_tracks[added[int(person)]][-window:]


def main():
    """Draw the metrics figure.

    Saves
    -----
    docs/repertoires/slides/public/metrics.png and metrics.pdf
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=pathlib.Path, default=DATA, help="2C120 PeTrack file"
    )
    args = parser.parse_args()

    # --- Data ---
    entrance = dataclasses.replace(ENTRANCE, wait_slack=None)
    exp_tracks, crossings = experiment(args.data)
    sim_tracks, removed, added = simulate(
        "cfsm-v2", entrance, pathlib.Path("/dev/null"), args.data
    )
    exp_p, sim_p = (smooth(p) for p in pick_person(exp_tracks, sim_tracks, added))
    crossings, removed = np.sort(crossings), np.sort(removed)

    # --- Style Setup ---
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(
        1, 3, figsize=(13, 3.6), gridspec_kw={"width_ratios": [1.3, 1, 1]}
    )

    # --- Plot (a): track while waiting, centred on its mean position ---
    ax = axes[0]
    door = np.array(ENTRANCE.entrance)
    for p, colour, style, name in (
        (exp_p, EXP, "-", "experiment"),
        (sim_p, SIM, "--", "simulation"),
    ):
        d = np.diff(p, axis=0)
        u = (door - p[:-1]) / np.linalg.norm(door - p[:-1], axis=1)[:, None]
        walked = np.linalg.norm(d, axis=1).sum()
        sideways = np.abs(d[:, 0] * u[:, 1] - d[:, 1] * u[:, 0]).sum()
        c = p - p.mean(axis=0)
        ax.plot(c[:, 1], -c[:, 0], style, color=colour, lw=1.4,
                label=f"{name}: walked {walked:.1f} m, sideways {sideways:.1f} m")
    ax.set_aspect("equal")
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.8, 0.8)
    ax.set_xlabel("towards the door (m)", color="dimgrey")
    ax.set_ylabel("sideways (m)", color="dimgrey")
    ax.set_title("(a) walked and sideways, last 40 s", loc="left", fontsize=11)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), frameon=True,
              facecolor="white", framealpha=0.8, edgecolor="lightgrey",
              labelcolor="dimgrey", fontsize=8.5)

    # --- Plot (b): speed and the moving threshold ---
    ax = axes[1]
    for p, colour, style in ((exp_p, EXP, "-"), (sim_p, SIM, "--")):
        speed = np.linalg.norm(np.diff(p, axis=0), axis=1) / 0.1
        t = np.arange(len(speed)) * 0.1
        ax.plot(t, speed, style, color=colour, lw=1.0)
        share = np.mean(speed > 0.1)
        ax.annotate(
            f"moving {share:.0%}", xy=(t[-1], 0.9 if colour == EXP else 0.8),
            ha="right", fontsize=9, color=colour,
        )
    ax.axhline(0.1, color="#bd0c0c", lw=1.0)
    ax.text(1.01, 0.1, "0.1 m/s", transform=ax.get_yaxis_transform(),
            va="center", fontsize=8.5, color="#bd0c0c")
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("last 40 s before the door opens (s)", color="dimgrey")
    ax.set_ylabel("speed (m/s)", color="dimgrey")
    ax.set_title("(b) share of time moving", loc="left", fontsize=11)

    # --- Plot (c): people out after the door opens ---
    ax = axes[2]
    n = np.arange(1, len(crossings) + 1)
    ax.step(crossings, n, where="post", color=EXP, lw=1.4, label="experiment")
    ax.step(removed, np.arange(1, len(removed) + 1), where="post",
            color=SIM, ls="--", lw=1.4, label="simulation")
    for k in (25, 50, 75):
        ax.plot(crossings[k - 1], k, "o", color=EXP, ms=4)
        ax.annotate(f"{k}th", xy=(crossings[k - 1] - 2, k + 3), ha="right",
                    fontsize=8.5, color="dimgrey")
    grid = np.arange(DOOR_OPEN_TIME, 200, 0.1)
    gap = np.searchsorted(removed, grid, "right") - np.searchsorted(crossings, grid, "right")
    k = np.argmax(np.abs(gap))
    lo, hi = sorted((np.searchsorted(crossings, grid[k], "right"),
                     np.searchsorted(removed, grid[k], "right")))
    ax.annotate("", xy=(grid[k], hi), xytext=(grid[k], lo),
                arrowprops=dict(arrowstyle="<->", color="#bd0c0c", lw=1.2))
    ax.annotate(f"largest gap\n{abs(gap[k])} people", xy=(grid[k] + 1, lo - 1),
                xytext=(grid[k] + 6, 35), ha="center", fontsize=8.5,
                color="#bd0c0c", arrowprops=dict(arrowstyle="-", color="#bd0c0c", lw=0.8))
    ax.set_xlim(DOOR_OPEN_TIME - 2, 185)
    ax.set_xlabel("time (s)", color="dimgrey")
    ax.set_ylabel("people out", color="dimgrey")
    ax.set_title("(c) outflow", loc="left", fontsize=11)
    ax.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.8,
              edgecolor="lightgrey", labelcolor="dimgrey", fontsize=9)

    for ax in axes:
        ax.grid(False)
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.tight_layout(w_pad=2.0)

    # --- Save ---
    out = pathlib.Path(__file__).resolve().parents[1] / "slides" / "public"
    for ext in ("png", "pdf"):
        fig.savefig(out / f"metrics.{ext}", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
