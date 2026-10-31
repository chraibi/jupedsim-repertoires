"""Geometry of the queue target and the passing points (figure 3)."""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

INK, MUTED, ACCENT, SOFT = "#2d3142", "#4f5d75", "#bf4520", "#9aa3b5"
E = np.array([7.6, 1.6])
s, d, ell, r_in, r_cont, wall = 0.7, 0.8, 0.8, 0.6, 0.4, 0.25

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.3), sharey=True)


def unit(a, b):
    v = b - a
    return v / np.linalg.norm(v)


def person(ax, p, label, colour=INK, offset=(0.0, -0.32)):
    ax.add_patch(Circle(p, 0.18, fc="white", ec=colour, lw=1.2, zorder=3))
    ax.annotate(label, p + np.array(offset), ha="center", va="center",
                color=colour)


def point(ax, p, label, colour=INK, offset=(0.0, 0.22), marker="x"):
    ax.plot(*p, marker=marker, color=colour, ms=6, mew=1.4, zorder=4)
    ax.annotate(label, p + np.array(offset), ha="center", va="center",
                color=colour)


def frame(ax, title):
    ax.axhspan(-0.2, 0.0, color="#d9dce3", lw=0)
    ax.axhline(wall, color=SOFT, lw=0.8, ls=(0, (4, 3)))
    ax.text(0.25, wall + 0.08, "wall clearance 0.25 m", color=MUTED, fontsize=7)
    point(ax, E, "$E$", INK, (0.0, 0.25), marker="o")
    ax.set_title(title, loc="left", color=INK, fontsize=10)
    ax.set_xlim(0.0, 8.2)
    ax.set_ylim(-0.2, 3.4)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)


# (a) queueing
ax = axes[0]
frame(ax, "(a) Queueing: target behind the predecessor")
xp, xi, xb = np.array([4.2, 1.4]), np.array([2.6, 1.6]), np.array([1.5, 2.5])
u = unit(xp, E)
q = xp - s * u
ax.fill_between([xi[0], 8.2], -0.2, 3.4, color=ACCENT, alpha=0.05, lw=0)
ax.axvline(xi[0], color=ACCENT, lw=0.8, alpha=0.6)
ax.text(xi[0] + 0.08, 3.15, "view half-plane, $\\mathbf{h}_i$", color=ACCENT,
        fontsize=7)
ax.annotate("", q, xi, arrowprops=dict(arrowstyle="->", color=MUTED, lw=1))
ax.annotate("", xp + 0.9 * u, xp,
            arrowprops=dict(arrowstyle="->", color=SOFT, lw=1))
ax.text(*(xp + 0.95 * u + np.array([0.0, 0.12])), "$\\mathbf{u}_p$",
        color=MUTED)
person(ax, xp, "$p$")
person(ax, xi, "$i$")
person(ax, xb, "$b$", SOFT)
point(ax, q, "$\\mathbf{q}_i$", ACCENT, (0.0, 0.25))
ax.annotate("$s$ = 0.7 m", (q + xp) / 2 + np.array([0.0, -0.55]),
            ha="center", color=MUTED, fontsize=7)

# (b) overtaking
ax = axes[1]
frame(ax, "(b) Overtaking: passing points and clearances")
xp, xi = np.array([4.4, 1.75]), np.array([3.4, 1.65])
u = unit(xp, E)
n = np.array([-u[1], u[0]])
c_plus, c_minus = xp + d * n, xp - d * n
a = xp + ell * u
xk = c_minus + np.array([0.2, -0.38])
for c in (c_plus, c_minus):
    ax.add_patch(Circle(c, r_in, fill=False, ec=MUTED, lw=0.9, ls=(0, (4, 3))))
    ax.add_patch(Circle(c, r_cont, fill=False, ec=MUTED, lw=0.9))
ax.plot(*np.array([xi, c_plus, a]).T, color=ACCENT, lw=1.2, ls=(0, (1, 2)))
person(ax, xp, "$p$", INK, (0.42, 0.0))
person(ax, xi, "$i$", INK, (-0.38, 0.0))
person(ax, xk, "$k$", SOFT, (0.38, -0.05))
ax.plot(*c_plus, "x", color=ACCENT, ms=6, mew=1.4)
ax.plot(*c_minus, "x", color=MUTED, ms=6, mew=1.4)
ax.annotate("$\\mathbf{c}^{+}$", c_plus + np.array([-0.85, 0.05]),
            ha="center", color=ACCENT)
ax.annotate("$\\mathbf{c}^{-}$", c_minus + np.array([-0.85, 0.05]),
            ha="center", color=MUTED)
point(ax, a, "$\\mathbf{a}$", ACCENT, (0.2, 0.2))
ax.annotate("$r_\\mathrm{in}$ = 0.6 m", c_plus + np.array([0.75, 0.3]),
            color=MUTED, fontsize=7)
ax.annotate("$r_\\mathrm{cont}$ = 0.4 m", c_plus + np.array([0.75, 0.04]),
            color=MUTED, fontsize=7)
ax.plot(*np.array([xp, c_plus]).T, color=SOFT, lw=0.8)
fig.tight_layout()
fig.savefig("geometry.pdf")
fig.savefig("geometry.svg")
