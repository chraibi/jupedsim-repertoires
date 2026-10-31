"""What agent i sees: the view half-disc and the people in it (slides)."""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Wedge

INK, MUTED, ACCENT, SOFT, BLUE = "#2d3142", "#4f5d75", "#bf4520", "#9aa3b5", "#4c72b0"
R = 4.0
me, E = np.array([1.0, 1.6]), np.array([6.1, 1.6])
seen = {"17": (np.array([2.2, 1.6]), "standing"), "23": (np.array([3.4, 2.5]), "")}
unseen = {"behind": np.array([0.2, -0.2]), "beyond 4 m": np.array([5.4, -0.6])}
spot = seen["17"][0] + np.array([0.0, 1.0])

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 14})
fig, ax = plt.subplots(figsize=(4.6, 4.4))
ax.add_patch(Wedge(me, R, -90, 90, fc=BLUE, alpha=0.07, ec=BLUE, lw=0.8))
ax.text(*(me + np.array([0.3, R - 0.6])), "view: 4 m, ahead", color=BLUE,
        fontsize=13)


def person(p, colour, fill="white", ls="-"):
    ax.add_patch(Circle(p, 0.18, fc=fill, ec=colour, lw=1.3, ls=ls, zorder=3))


person(me, INK, fill=INK)
ax.annotate("me", me + np.array([-0.3, 0.0]), ha="right", va="center", color=INK)
for name, (p, note) in seen.items():
    person(p, BLUE)
    ax.annotate(f"{name}" + (f"\n{note}" if note else ""), p + np.array([0.0, -0.6]),
                ha="center", va="center", color=BLUE, fontsize=13)
for note, p in unseen.items():
    person(p, SOFT, ls=(0, (2, 2)))
    ax.annotate(f"not seen:\n{note}", p + np.array([0.0, -0.7]), ha="center",
                va="center", color=SOFT, fontsize=12)
ax.plot(*spot, marker="x", color=ACCENT, ms=6, mew=1.4)
ax.annotate("free spot\nbeside 17", spot + np.array([0.0, 0.6]), ha="center",
            va="center", color=ACCENT, fontsize=13)
ax.plot(*E, "o", color=INK, ms=5)
ax.annotate("entrance", E + np.array([0.0, 0.3]), ha="center", color=INK)
ax.annotate("", E - np.array([0.3, 0.0]), me + np.array([R + 0.25, 0.0]),
            arrowprops=dict(arrowstyle="->", color=SOFT, lw=1))
ax.set_xlim(-0.6, 6.8)
ax.set_ylim(-2.5, 5.7)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig("sees.svg")
fig.savefig("sees.pdf")
