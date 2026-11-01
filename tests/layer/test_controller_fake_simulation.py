# SPDX-License-Identifier: LGPL-3.0-or-later

"""Controller tests on a scripted simulation, without JuPedSim."""

import dataclasses

import pytest
import shapely

from jupedsim_repertoires import (
    Capability,
    Command,
    Decision,
    RepertoireController,
)
from jupedsim_repertoires.log import RunLog, load_records
from jupedsim_repertoires.perception import MemoryTracker, Perception

STEERING = (1, 10)
EXIT = (2, 20)
DT = 0.01
BOTH = frozenset({Capability.TARGET_CONTROL, Capability.DESIRED_SPEED})


class FakeSimulation:
    """Agents stand still; writes are recorded instead of applied."""

    def __init__(self, positions):
        self.positions = dict(positions)
        self.journeys = {agent_id: STEERING for agent_id in positions}
        self.iterations = 0
        self.targets = {}
        self.speeds = {}
        self.switches = []

    def elapsed_time(self):
        return self.iterations * DT

    def agent_ids(self):
        return set(self.positions)

    def position(self, agent_id):
        return self.positions[agent_id]

    def agents_in_range(self, position, radius):
        return [
            (agent_id, p)
            for agent_id, p in sorted(self.positions.items())
            if (p[0] - position[0]) ** 2 + (p[1] - position[1]) ** 2
            <= radius**2
        ]

    def journey_stage(self, agent_id):
        return self.journeys[agent_id]

    def set_target(self, agent_id, target):
        self.targets[agent_id] = target

    def set_desired_speed(self, agent_id, speed):
        self.speeds[agent_id] = speed

    def switch_journey(self, agent_id, journey, stage):
        self.switches.append((agent_id, journey, stage))
        self.journeys[agent_id] = (journey, stage)

    def iterate(self, count):
        self.iterations += count


class Walk:
    """Walks towards a fixed target at a fixed speed."""

    requires = frozenset({Capability.TARGET_CONTROL})

    def __init__(self, name, target, speed, handoff=False):
        self.name = name
        self.target = target
        self.speed = speed
        self.handoff = handoff

    def enter(self, obs, state):
        return dataclasses.replace(state, commitment_since=obs.time)

    def control(self, obs, state):
        return Command(
            target=self.target,
            desired_speed=self.speed,
            execution="walking",
            state=dataclasses.replace(state, target=self.target),
            handoff=self.handoff,
        )


class Recording:
    """Keeps every unit in ``choice`` and records who was asked when."""

    def __init__(self, choice="a"):
        self.choice = choice
        self.asked = []

    def decide(self, requests):
        self.asked.extend((r.snapshot_time, r.unit_id) for r in requests)
        return [
            Decision(r.unit_id, (self.choice,) * len(r.members))
            for r in requests
        ]


def make_controller(sim, repertoires, selector, log):
    return RepertoireController(
        sim,
        repertoires={r.name: r for r in repertoires},
        selector=selector,
        perception=Perception(
            progress=lambda p: p[0],
            radius=5.0,
            half_angle_deg=90.0,
            heading=lambda p: (1.0, 0.0),
        ),
        memory=MemoryTracker(window=10.0, pass_tolerance=0.2),
        log=log,
        steering_journey=STEERING[0],
        steering_stage=STEERING[1],
        exit_journey=EXIT[0],
        exit_stage=EXIT[1],
        walkable=shapely.box(0, 0, 10, 10),
        control_interval=10,
        decision_period=1.0,
        capabilities=BOTH,
    )


def run(sim, repertoires, selector, path, steps, start="a"):
    with RunLog(path, {}) as log:
        ctrl = make_controller(sim, repertoires, selector, log)
        for agent_id in sorted(sim.positions):
            ctrl.add(agent_id, start)
        for _ in range(steps):
            ctrl.step()
    return ctrl


def test_units_are_asked_once_per_period_at_their_phase(tmp_path):
    sim = FakeSimulation({7: (1.0, 2.0), 3: (1.0, 8.0)})
    selector = Recording()
    run(sim, [Walk("a", (8.0, 5.0), 1.0)], selector, tmp_path / "l", 25)
    # Unit indices follow ascending ids: 3 gets phase 0, 7 phase 0.1 s.
    asked = [(round(t, 6), unit) for t, unit in selector.asked]
    assert asked == [
        (0.0, 3),
        (0.1, 7),
        (1.0, 3),
        (1.1, 7),
        (2.0, 3),
        (2.1, 7),
    ]
    assert sim.iterations == 25 * 10


def test_transition_applies_the_new_repertoire(tmp_path):
    sim = FakeSimulation({1: (1.0, 5.0)})
    reps = [Walk("a", (8.0, 5.0), 1.0), Walk("b", (8.0, 2.0), 0.5)]
    ctrl = run(sim, reps, Recording("b"), tmp_path / "l", 1)
    assert ctrl.states[1].repertoire == "b"
    assert sim.targets == {1: (8.0, 2.0)}
    assert sim.speeds == {1: 0.5}
    (transition,) = [
        r for r in load_records(tmp_path / "l") if r["type"] == "transition"
    ]
    assert (transition["before"], transition["after"]) == ("a", "b")
    assert transition["cause"] == "periodic"


def test_target_outside_walkable_area_holds_position(tmp_path):
    sim = FakeSimulation({1: (1.0, 5.0)})
    ctrl = run(
        sim, [Walk("a", (20.0, 5.0), 1.0)], Recording(), tmp_path / "l", 1
    )
    assert sim.targets == {1: (1.0, 5.0)}
    assert ctrl.states[1].execution == "standing"


def test_handoff_switches_journey_and_releases_agent(tmp_path):
    sim = FakeSimulation({1: (1.0, 5.0)})
    reps = [Walk("a", (8.0, 5.0), 1.0, handoff=True)]
    ctrl = run(sim, reps, Recording(), tmp_path / "l", 1)
    assert sim.switches == [(1, *EXIT)]
    assert 1 not in ctrl.states


def test_agent_not_at_steering_stage_is_refused(tmp_path):
    sim = FakeSimulation({1: (1.0, 5.0)})
    sim.journeys[1] = EXIT
    with RunLog(tmp_path / "l", {}) as log:
        ctrl = make_controller(
            sim, [Walk("a", (8.0, 5.0), 1.0)], Recording(), log
        )
        with pytest.raises(ValueError, match="steering stage"):
            ctrl.add(1, "a")


def test_departed_agent_is_released(tmp_path):
    sim = FakeSimulation({1: (1.0, 5.0), 2: (2.0, 5.0)})
    with RunLog(tmp_path / "l", {}) as log:
        ctrl = make_controller(
            sim, [Walk("a", (8.0, 5.0), 1.0)], Recording(), log
        )
        ctrl.add(1, "a")
        ctrl.add(2, "a")
        ctrl.step()
        del sim.positions[2]
        ctrl.step()
    assert set(ctrl.states) == {1}
