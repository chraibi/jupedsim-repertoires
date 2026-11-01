# SPDX-License-Identifier: LGPL-3.0-or-later

from collections.abc import Sequence
from typing import Protocol

Point = tuple[float, float]


class Simulation(Protocol):
    """What the layer reads from and writes to the simulation."""

    def elapsed_time(self) -> float:
        """Current simulation time in seconds."""
        ...

    def agent_ids(self) -> set[int]:
        """Ids of the agents still in the simulation."""
        ...

    def position(self, agent_id: int) -> Point:
        """Position of one agent."""
        ...

    def agents_in_range(
        self, position: Point, radius: float
    ) -> Sequence[tuple[int, Point]]:
        """Ids and positions of the agents within ``radius``."""
        ...

    def journey_stage(self, agent_id: int) -> tuple[int, int]:
        """Journey id and stage id an agent follows."""
        ...

    def set_target(self, agent_id: int, target: Point) -> None:
        """Set the target an agent walks towards."""
        ...

    def set_desired_speed(self, agent_id: int, speed: float) -> None:
        """Set an agent's desired speed."""
        ...

    def switch_journey(self, agent_id: int, journey: int, stage: int) -> None:
        """Hand an agent over to another journey."""
        ...

    def iterate(self, count: int) -> None:
        """Advance the simulation by ``count`` iterations."""
        ...


class JuPedSimAdapter:
    """:class:`Simulation` backed by a ``jupedsim.Simulation``.

    Args:
        sim: The JuPedSim simulation.
    """

    def __init__(self, sim):
        self._sim = sim

    def elapsed_time(self) -> float:
        return self._sim.elapsed_time()

    def agent_ids(self) -> set[int]:
        return {agent.id for agent in self._sim.agents()}

    def position(self, agent_id: int) -> Point:
        return tuple(self._sim.agent(agent_id).position)

    def agents_in_range(
        self, position: Point, radius: float
    ) -> list[tuple[int, Point]]:
        return [
            (agent.id, tuple(agent.position))
            for agent in self._sim.agents_in_range(position, radius)
        ]

    def journey_stage(self, agent_id: int) -> tuple[int, int]:
        agent = self._sim.agent(agent_id)
        return agent.journey_id, agent.stage_id

    def set_target(self, agent_id: int, target: Point) -> None:
        self._sim.agent(agent_id).final_target = target

    def set_desired_speed(self, agent_id: int, speed: float) -> None:
        self._sim.agent(agent_id).state.desired_speed = speed

    def switch_journey(self, agent_id: int, journey: int, stage: int) -> None:
        self._sim.switch_agent_journey(agent_id, journey, stage)

    def iterate(self, count: int) -> None:
        self._sim.iterate(count)
