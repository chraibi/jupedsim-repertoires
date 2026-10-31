"""Queueing: each person targets 0.7 m behind the nearest person ahead (slides)."""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, Circle

INK, ACCENT, SOFT, BLUE = "#2d3142", "#bf4520", "#9aa3b5", "#4c72b0"
E = np.array([6.6, 1.0])
SPACING = 0.7
first, mid, me = np.array([5.3, 1.0]), np.array([4.2, 0.55]), np.array([2.5, 1.0])
# Only 0.1 m closer to E than me: not ahead.
beside = E + (np.linalg.norm(E - me) - 0.1) * np.array([-np.cos(0.24), np.sin(0.24)])

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
fig, ax = plt.subplots(figsize=(6.4, 2.7))


def person(p, colour, fill="white", ls="-"):
    ax.add_patch(Circle(p, 0.18, fc=fill, ec=colour, lw=1.3, ls=ls, zorder=3))


def target_behind(p):
    u = (E - p) / np.linalg.norm(E - p)
    return p - SPACING * u


def step(src, dst, colour):
    ax.annotate("", dst, src, arrowprops=dict(arrowstyle="->", color=colour,
                                              lw=1.2, shrinkA=8, shrinkB=4))


ax.plot(*E, "o", color=INK, ms=5)
ax.annotate("entrance", E + np.array([0.0, 0.3]), ha="center", color=INK)

person(first, BLUE)
step(first, E, BLUE)
ax.annotate("first:\nto the entrance", first + np.array([0.0, -0.75]),
            ha="center", va="center", color=BLUE, fontsize=11)

for follower, ahead, colour in ((mid, first, BLUE), (me, mid, ACCENT)):
    q = target_behind(ahead)
    person(follower, colour, fill=INK if follower is me else "white")
    ax.plot(*q, marker="x", color=colour, ms=7, mew=1.5, zorder=4)
    ax.plot(*np.column_stack([q, ahead]), ":", color=colour, lw=1)
    step(follower, q, colour)

ax.annotate("me", me + np.array([-0.3, 0.0]), ha="right", va="center", color=INK)
# Boundary of "ahead": 0.2 m closer to the entrance than me.
r = np.linalg.norm(E - me) - 0.2
ax.add_patch(Arc(E, 2 * r, 2 * r, theta1=150, theta2=207, ec=SOFT, lw=1.0,
                 ls=(0, (3, 2))))

person(beside, SOFT, ls=(0, (2, 2)))
ax.plot(*beside, ".", color=SOFT, ms=4, zorder=4)

ax.set_xlim(1.6, 7.1)
ax.set_ylim(-0.9, 2.5)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig("queue.svg")
fig.savefig("queue.pdf")
