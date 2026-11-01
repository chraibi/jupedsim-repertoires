# SPDX-License-Identifier: LGPL-3.0-or-later

"""Smallest repertoire run: a square room, one repertoire, one exit.

Starting point for prototyping repertoires: edit ``Walk`` or add another
repertoire to ``REPERTOIRES`` and a selector that chooses between them.
"""

import dataclasses
import pathlib

import jupedsim as jps
import shapely

from jupedsim_repertoires import (
    Capability,
    Command,
    FixedSelector,
    JuPedSimAdapter,
    RepertoireController,
    model_capabilities,
)
from jupedsim_repertoires.log import RunLog
from jupedsim_repertoires.perception import MemoryTracker, Perception

ROOM = shapely.box(0, 0, 10, 10)
SPAWN = shapely.box(1, 1, 5, 9)
EXIT = shapely.box(9.5, 4, 10, 6)
EXIT_CENTRE = (9.75, 5.0)


class Walk:
    """Walk straight to the exit; hand over to the exit journey near it."""

    name = "walk"
    requires = frozenset({Capability.TARGET_CONTROL})

    def enter(self, obs, state):
        return dataclasses.replace(state, commitment_since=obs.time)

    def control(self, obs, state):
        return Command(
            target=EXIT_CENTRE,
            desired_speed=None,
            execution="walking",
            state=dataclasses.replace(state, target=EXIT_CENTRE),
            handoff=obs.position[0] > 8.5,
        )


REPERTOIRES = {r.name: r for r in [Walk()]}


def main() -> None:
    # Geometry, journeys and agents: plain JuPedSim.
    surface = jps.WalkableSurface()
    room = surface.add_region(polygon=ROOM)
    sim = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=surface, dt=0.01
    )
    steering = sim.add_direct_steering_stage()
    steering_journey = sim.add_journey(jps.JourneyDescription([steering]))
    exit_stage = sim.add_exit_stage([(EXIT.exterior.coords[:-1], room)])
    exit_journey = sim.add_journey(jps.JourneyDescription([exit_stage]))
    ids = [
        sim.add_agent(
            journey_id=steering_journey,
            stage_id=steering,
            position=p,
            state=jps.CollisionFreeSpeedModelState(),
            region_id=room,
        )
        for p in jps.distribute_by_number(
            polygon=SPAWN,
            number_of_agents=20,
            distance_to_agents=0.5,
            distance_to_polygon=0.2,
            seed=1,
        )
    ]

    # The repertoire layer.
    log = RunLog(pathlib.Path("square.jsonl"), {"scenario": "square"})
    controller = RepertoireController(
        JuPedSimAdapter(sim),
        repertoires=REPERTOIRES,
        selector=FixedSelector(),
        perception=Perception(
            progress=lambda p: p[0],
            radius=3.0,
            half_angle_deg=90.0,
            heading=lambda p: (1.0, 0.0),
        ),
        memory=MemoryTracker(window=8.0, pass_tolerance=0.2),
        log=log,
        steering_journey=steering_journey,
        steering_stage=steering,
        exit_journey=exit_journey,
        exit_stage=exit_stage,
        walkable=ROOM,
        control_interval=10,
        decision_period=2.0,
        capabilities=model_capabilities(sim.agent(ids[0]).state),
    )
    for agent_id in ids:
        controller.add(agent_id, "walk")

    with log:
        while sim.agent_count() > 0 and sim.elapsed_time() < 60.0:
            controller.step()
    print(f"t={sim.elapsed_time():.2f} s, {sim.agent_count()} agents left")


if __name__ == "__main__":
    main()
