---
title: "Behavioural repertoires in JuPedSim"
subtitle: "Model description of the rule-based entrance model, branch behavioural-repertoires (4c5b706d8)"
date: 30 October 2026
geometry: margin=2.4cm
fontsize: 10pt
colorlinks: true
---

# Scope

This note describes the model as implemented at commit `d466aca` (commit
`4c5b706d8` of the JuPedSim branch `behavioural-repertoires`). The library
part lives in `jupedsim_repertoires`, and the entrance repertoires and rules
in `repertoire_examples`. All numerical values are modelling
assumptions; none is calibrated against data. The entry clearance of
0.6 m (Section 6.3) is an exploratory value.

The concept of behavioural repertoires follows Sieben and Postmes (2025).
The rules, equations and values below are choices made for this model and
are not taken from that paper.

# Two levels of control

The operational model of JuPedSim (CFSM or CFSM V3) moves agents
towards a target at a desired speed while avoiding collisions. A
*behavioural layer* above it decides which behaviour each agent engages in
and turns that behaviour into the operational model's two inputs: the
target $\mathbf{x}^{\ast}_i$ and the desired speed $v^0_i$.

Two quantities describe an agent's behaviour:

- the **repertoire** (queueing or overtaking), chosen by a *selector*;
  it fixes the social anchor and the permitted manoeuvre;
- the **execution mode** (standing, advancing, passing), set by the
  repertoire at every control step without a new selection.

![One control interval. The selector (accent) is the only component that
can be replaced, e.g. by a learned or external decision
model.](figures/loop.pdf){width=100%}

The layer acts every $n_c = 10$ iterations of the operational model,
i.e. every $\Delta t_c = n_c\,\Delta t = 0.1$ s with $\Delta t = 0.01$ s.
Agents near the entrance are handed off to an ordinary JuPedSim exit
journey and leave the layer (Section 7).

# Progress and perception

Let $E$ be the entrance and $\mathbf{x}_i(t)$ the position of agent $i$.
Progress and the unit direction towards $E$ are
$$
p_i(t) = -\lVert \mathbf{x}_i(t) - E \rVert,
\qquad
\mathbf{u}(\mathbf{x}) = \frac{E - \mathbf{x}}{\lVert E - \mathbf{x} \rVert}.
$$
Progress increases as the agent approaches $E$.

Agent $i$ perceives agent $j \neq i$ if $j$ is within the perception radius
$R$ and inside the view cone of half-angle $\varphi$ around the heading
$\mathbf{h}_i = \mathbf{u}(\mathbf{x}_i)$:
$$
j \in \mathcal{P}_i
\iff
\lVert \mathbf{r}_{ij} \rVert \le R
\;\wedge\;
\bigl(\mathbf{r}_{ij}\cdot\mathbf{h}_i \ge \cos\varphi\,\lVert \mathbf{r}_{ij} \rVert
\;\vee\; j = \tau_i\bigr),
\qquad \mathbf{r}_{ij} = \mathbf{x}_j - \mathbf{x}_i ,
$$
with $R = 4$ m and $\varphi = 90^\circ$, so the cone is the half-plane in
front of the agent. The term $j = \tau_i$ applies only while $i$ is
overtaking: $\tau_i$ is the agent being passed. It stays perceived within
$R$ once it falls behind, so the overtaker can tell when the pass is
complete. Without this exception the target leaves the half-plane before
the completion margin of Section 6.4 is reached. Queueing agents have no
tracked agent.

# Memory

Each agent keeps, for a window of $W = 8$ s, its progress history and
the passes it has observed.

**Progress gained** over a span $T$ is
$$
\Delta p_i(t; T) = p_i(t) - p_i(t_0),
\qquad t_0 = \min\{t_k \ge t - T\},
$$
over the recorded control times $t_k$. If the history does not reach back
to $t - T$, $\Delta p_i = +\infty$, so a newly controlled agent is never
counted as stalled.

**Passes.** Agent $j$ passes $i$ at time $t$ if $j$ was perceived behind
$i$, $p_j - p_i < -\delta$, at some time within the window, has been
perceived at every control step since, and now satisfies
$p_j - p_i > \delta$, with $\delta = 0.2$ m. The number of passes since
$t - T$ is $N_i(t; T)$.

**Anchor lost** is a flag set when the agent's anchor has left the
simulation.

# Selection

## When decisions are taken

An agent requests a decision when one is periodically due or when an event
has occurred:

- *periodic*: every $T_d = 2$ s; agent $k$, numbered in order of entry
  into the layer, is due at $t = \tfrac{k \bmod 10}{10}\,T_d + m\,T_d$
  for $m = 0, 1, \dots$, which spreads decisions over the period;
- *events*: the event emitted by the active repertoire at the previous
  step (completion or abandonment), a pass observed at this step, or the
  anchor-lost flag.

All requests of one control step are built from the same snapshot of
perception and memory and are sent to the selector in one batch. The
selector's answers are applied together.

## Rule-based selector

**Incentive** to overtake is
$$
I_i = \bigl[\Delta p_i(t; T_s) < \Delta p_s\bigr]
\;\vee\;
\bigl[N_i(t; T_n) \ge n_p\bigr],
$$
with $T_s = 4$ s, $\Delta p_s = 0.3$ m, $T_n = 6$ s and $n_p = 2$: the agent
is stalled, or it has been passed repeatedly.

**Feasibility** is a passing point beside the anchor that satisfies the
entry clearance (Section 6.3):
$$
G_i = \bigl[\pi_i \in \mathcal{P}_i\bigr] \;\wedge\;
\mathcal{C}_i(r_\text{in}) \neq \emptyset .
$$

The transitions are:

| Current repertoire | Condition | New repertoire | Logged reason |
|---|---|---|---|
| queueing | $I_i \wedge G_i$ | overtaking | |
| queueing | $I_i \wedge \neg G_i$ | queueing | `overtake_withheld_no_gap` |
| queueing | $\neg I_i$ | queueing | |
| overtaking | event *completed* or *abandoned* | queueing | |
| overtaking | otherwise | overtaking | |

The incentive is not stored. It holds as long as the memory supports it, so
an agent with an incentive enters overtaking as soon as a gap opens within that time.

![Repertoire and phase transitions of one agent. Abandonment from the
lateral phase has three causes (no gap, target lost, stalled); from the
passing phase, two (target lost, stalled).](figures/states.pdf){width=100%}

# Repertoires

## Queueing

The **predecessor** is the nearest perceived agent ahead by more than the
margin $\delta_a = 0.2$ m:
$$
\pi_i = \operatorname*{arg\,min}_{j \in \mathcal{P}_i,\; p_j > p_i + \delta_a}
\lVert \mathbf{x}_j - \mathbf{x}_i \rVert ,
$$
with ties broken by the smaller id. The agent keeps its predecessor until
the predecessor is lost, no longer perceived or no longer ahead by
$\delta_a$, and then acquires a new one. The predecessor is the agent's
own belief; no global queue order exists.

The **queue target** lies at spacing $s$ behind the predecessor, along the
predecessor's direction to the entrance:
$$
\mathbf{q}_i =
\begin{cases}
\mathbf{x}_{\pi_i} - s\,\mathbf{u}(\mathbf{x}_{\pi_i}) & \text{if } \pi_i \text{ exists},\\
E & \text{otherwise},
\end{cases}
\qquad s = 0.7 \text{ m}.
$$
The desired speed is $v_q = 1.0$ m/s. The execution mode is *standing*
if $\lVert \mathbf{x}_i - \mathbf{q}_i \rVert < 0.15$ m and *advancing*
otherwise.

## Overtaking

On entry the anchor becomes the passing target $\tau_i$, and the manoeuvre
starts in phase 1. The desired speed is $v_o = 1.4$ m/s.

## Passing points

With the normal $\mathbf{n} = (-u_y, u_x)$ of
$\mathbf{u} = \mathbf{u}(\mathbf{x}_{\tau})$, the two lateral candidates
beside the target are
$$
\mathbf{c}^{\pm} = \mathbf{x}_{\tau} \pm d\,\mathbf{n},
\qquad d = 0.8 \text{ m}.
$$
A candidate is feasible with clearance $r$ if it lies in the walkable area
$\mathcal{W}$ shrunk by the wall clearance $w$ and no perceived agent other
than the target is closer than $r$:
$$
\mathcal{C}_i(r) =
\bigl\{\mathbf{c} \in \{\mathbf{c}^{+}, \mathbf{c}^{-}\} :
\mathbf{c} \in \mathcal{W} \ominus B_w
\;\wedge\;
\lVert \mathbf{c} - \mathbf{x}_j \rVert \ge r
\;\;\forall j \in \mathcal{P}_i \setminus \{\tau_i\}\bigr\},
\qquad w = 0.25 \text{ m}.
$$
The chosen point is the feasible candidate closest to the agent, ties going
to $\mathbf{c}^{+}$:
$\mathbf{c}^{\ast}_i = \operatorname{arg\,min}_{\mathbf{c} \in \mathcal{C}_i(r)}
\lVert \mathbf{x}_i - \mathbf{c} \rVert$.

Starting needs more room than continuing. The clearance is
$$
r =
\begin{cases}
r_\text{in} = 0.6 \text{ m} & \text{at entry and on the first control step},\\
r_\text{cont} = 0.4 \text{ m} & \text{afterwards}.
\end{cases}
$$
The first control step shares the snapshot of the entry decision, so the
agent steers to the point that justified the entry and not to a nearer
point that only meets $r_\text{cont}$. Overtakes started with a clearance
just above a single threshold of 0.4 m were otherwise ended within a few
control steps by small sideways movements of neighbours (Section 10).

![Geometry. (a) Queue target $\mathbf{q}_i$ at $s = 0.7$ m behind
predecessor $p$; agent $b$ is behind $i$'s view half-plane and is not
perceived. (b) Lateral candidates $\mathbf{c}^{\pm}$ at $d = 0.8$ m beside
target $p$, with entry (dashed) and continuation (solid) clearance; $k$
blocks $\mathbf{c}^{-}$, so $i$ moves to $\mathbf{c}^{+}$ and then to the
ahead point $\mathbf{a}$.](figures/geometry.pdf){width=100%}

## Execution and termination of an overtake

At every control step the overtaking repertoire checks, in this order:

1. **Handoff** (Section 7).
2. **Target lost**: $\tau_i \notin \mathcal{P}_i$ $\Rightarrow$ abandon
   (`overtake_abandoned_target_lost`).
3. **Completion**: $p_i > p_{\tau} + m_c$ with $m_c = 0.3$ m
   $\Rightarrow$ event `overtake_completed`; target $E$, mode *advancing*.
4. **Stall**: $t - t_\text{commit} \ge T_a$ and
   $\Delta p_i(t; T_a) < \Delta p_a$, with $T_a = 2$ s and
   $\Delta p_a = 0.1$ m $\Rightarrow$ abandon
   (`overtake_abandoned_stalled`).
5. **Phase 1** (lateral): if $\mathcal{C}_i(r) = \emptyset$, abandon
   (`overtake_abandoned_no_gap`). If
   $\lVert \mathbf{x}_i - \mathbf{c}^{\ast}_i \rVert < 0.3$ m, switch to
   phase 2. Otherwise steer to $\mathbf{c}^{\ast}_i$.
6. **Phase 2** (passing): steer to the ahead point
   $\mathbf{a}_i = \mathbf{x}_{\tau} + \ell\,\mathbf{u}(\mathbf{x}_{\tau})$,
   $\ell = 0.8$ m.

Abandoning sets the target to the agent's own position, the desired speed
to $v_q$ and the mode to *standing*. Losing the target is never counted
as completion. A completion or abandonment event triggers a decision at
the next control step, where the selector returns the agent to queueing.

# Handoff

An agent leaves the layer when
$$
\lVert \mathbf{x}_i - E \rVert < r_h
\quad\text{and}\quad
t \ge t_\text{open},
\qquad r_h = 1 \text{ m},
$$
from either repertoire and in any phase. It is switched to the exit
journey and is then routed by JuPedSim alone. Handoff is not a completed
overtake. The door opening time $t_\text{open}$ is 0 in the entrance and
demo scenarios and 90.5 s in the 2C120 scenario, where the door is closed
until then.

# One control step

1. Release agents that have left the simulation; set the anchor-lost flag
   of agents whose anchor has left.
2. Observe every controlled agent (perception and memory) at the same time
   $t$.
3. Enter the initial repertoire for agents added since the last step.
4. Collect decision requests (periodic or event-triggered) and pass them to
   the selector in one batch.
5. Apply all decisions; an agent whose repertoire changes enters the new
   one with $t_\text{commit} = t$.
6. Run the active repertoire of every agent: set its target and desired
   speed, or hand it off.
7. Log diagnostics and advance the operational model by $n_c$ iterations.

A target outside the walkable area is not applied: the agent holds its
position and its mode becomes *standing*.

# Parameters

| Symbol | Meaning | Value | Code name |
|---|---|---|---|
| $\Delta t$, $n_c$ | time step; iterations per control step | 0.01 s; 10 | `dt`, `control_interval` |
| $T_d$ | decision period | 2 s | `decision_period` |
| $R$, $\varphi$ | perception radius; half-angle | 4 m; 90° | `radius`, `half_angle_deg` |
| $W$, $\delta$ | memory window; pass tolerance | 8 s; 0.2 m | `window`, `pass_tolerance` |
| $T_s$, $\Delta p_s$ | stall span; minimum progress | 4 s; 0.3 m | `t_stall`, `stall_progress` |
| $T_n$, $n_p$ | pass span; passes needed | 6 s; 2 | `t_passes`, `n_passes` |
| $\delta_a$ | "ahead" margin | 0.2 m | `ahead_margin` |
| $s$ | queue spacing | 0.7 m | `spacing` |
| $v_q$, $v_o$ | desired speed queueing; overtaking | 1.0; 1.4 m/s | `queue_speed`, `overtake_speed` |
| $d$ | lateral offset | 0.8 m | `lateral_offset` |
| $w$ | wall clearance | 0.25 m | `wall_clearance` |
| $r_\text{in}$, $r_\text{cont}$ | entry; continuation clearance | 0.6; 0.4 m | `entry_free_radius`, `continuation_free_radius` |
| — | lateral point reached | 0.3 m | `lateral_reach` |
| $\ell$ | ahead offset | 0.8 m | `ahead_offset` |
| $m_c$ | completion margin | 0.3 m | `complete_margin` |
| $T_a$, $\Delta p_a$ | overtake stall span; minimum progress | 2 s; 0.1 m | `abandon_span`, `abandon_progress` |
| — | standing tolerance | 0.15 m | `standing_tol` |
| $r_h$ | handoff radius | 1 m | `handoff_radius` |
| $t_\text{open}$ | door opening time | 0 s | `door_open_time` |

The 2C120 scenario uses $v_q = 2.5$ m/s and $v_o = 3.5$ m/s: the median of
the participants' 90th-percentile speeds over the first 20 s is 2.5 m/s.

# What the simulations show so far

Entrance scenario (20 m × 10 m approach area, 1 m wide entrance), CFSM,
90 agents, seeds 1–3, continuation clearance 0.4 m:

| Entry clearance | 0.4 m | 0.5 m | 0.6 m |
|---|---:|---:|---:|
| Overtakes started | 639 | 299 | 215 |
| Completed | 209 | 149 | 134 |
| Abandoned: no gap / stalled / target lost | 368 / 45 / 3 | 100 / 39 / 2 | 57 / 18 / 1 |
| Abandoned within 0.5 s | 198 | 25 | 7 |
| Completed per run | 55, 66, 88 | 54, 40, 55 | 48, 42, 44 |
| Final exit time per run (s) | 102.3, 109.4, 106.0 | 103.5, 107.2, 109.0 | 102.7, 108.4, 103.8 |

Before the target was tracked outside the view cone, no overtake completed
(0 of 627 in the same runs); successful passes were logged as target loss.

Open points:

- In the 2C120 scenario with CFSM V3 and the rule-based selector, agents
  jam in front of the door after it opens (48 of 87 remain at 200 s,
  measured before the entry clearance was raised to 0.6 m). With
  CFSM, or with queueing only, the corridor empties. The cause is not yet
  identified.
- The labels *completed* and *abandoned* describe the controller, not
  observed behaviour. Whether the trajectories show queueing and
  overtaking has to be established by coding them as the experiments were
  coded.
- The rule-based selector can be replaced by another selector (for example
  one estimating a Jev-like value) without changing the repertoires.

# What the layer uses from JuPedSim

The layer reaches JuPedSim in two files and only through its public Python
API. State, memory, selectors, decision scheduling and logs do not use
JuPedSim.

| Where | JuPedSim call | Used for |
|---|---|---|
| `perception.py` | `sim.agent(id).position` | Own position |
| `perception.py` | `sim.agents_in_range(position, radius)` | Agents within the perception radius |
| `controller.py` | `agent.journey_id`, `agent.stage_id` | Check that an added agent is at the direct steering stage |
| `controller.py` | `sim.elapsed_time()` | Time of observations and decisions |
| `controller.py` | `sim.iterate(n)` | Advance the movement between control steps |
| `controller.py` | `sim.agents()` | Detect agents that have left the simulation |
| `controller.py` | `agent.state` (has `desired_speed`?) | Capabilities of the operational model |
| `controller.py` | `agent.state.desired_speed` | Speed set by a repertoire |
| `controller.py` | `agent.final_target` | Target set by a repertoire |
| `controller.py` | `sim.switch_agent_journey(...)` | Handoff to the exit journey |

The scenario additionally builds the geometry, the journeys with a direct
steering stage, and the agents with JuPedSim.

`agent.state` and WarpDriver are only on JuPedSim master, so the
dependency is pinned to a master commit. No separate adapter layer exists:
with one simulator and this few calls, it would add an interface without a
second implementation. It becomes worth it if a second simulator is
supported, or if JuPedSim's API changes in more than these places. A
capability missing here goes upstream into JuPedSim; behavioural
assumptions stay in this repository.

## Run log

Observations are written only in diagnostic mode (`--diagnostic`), as
they make the log large. Analyses of what agents saw between decisions,
such as the no-gap investigation, need a run with `--diagnostic`.

The metadata record holds `diagnostic`, `code_revision` and, for 2C120,
`input_checksum`, so a log states the code and the input data it came
from.

# Reference

Sieben, A. and Postmes, T. (2025). Behavioural repertoires in moving
crowds: an observational approach. *Royal Society Open Science* 12, 241561.
doi:10.1098/rsos.241561.
