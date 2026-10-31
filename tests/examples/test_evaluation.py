# SPDX-License-Identifier: LGPL-3.0-or-later
import json
import types

import numpy as np
import pytest

from repertoire_examples.croma import DOOR_OPEN_TIME
from repertoire_examples.evaluation import (
    WINDOW,
    Recorder,
    completion,
    events,
    experiment,
    median,
    median_of,
    movement,
    nth,
    outflow,
)

FAR = np.array([0.0, 1e6])


def track(step, n=WINDOW):
    """Track of n samples moving by ``step`` (m) per sample."""
    return np.arange(n)[:, None] * np.array(step, dtype=float)


def test_movement_towards_the_entrance():
    # 0.02 m per 0.1 s: 12 m/min, all of it towards the entrance.
    card = movement({1: track((0.0, 0.02))}, FAR)
    assert card == {
        "people_waiting": 1,
        "walked_m_per_min": 12.0,
        "sideways_m_per_min": 0.0,
        "moving_share": 1.0,
    }


def test_movement_sideways():
    card = movement({1: track((0.02, 0.0))}, FAR)
    assert card["walked_m_per_min"] == 12.0
    assert card["sideways_m_per_min"] == 12.0


def test_movement_standing_is_not_moving():
    card = movement({1: track((0.0, 0.0))}, FAR)
    assert card["walked_m_per_min"] == 0.0
    assert card["moving_share"] == 0.0


def test_movement_uses_the_last_window_of_long_tracks_only():
    jump = track((5.0, 0.0), 100)
    standing = np.vstack([jump, np.zeros((WINDOW, 2))])
    short = track((0.0, 0.02), WINDOW - 1)
    card = movement({1: standing, 2: short}, FAR)
    assert card["people_waiting"] == 1
    assert card["walked_m_per_min"] == 0.0


def test_movement_takes_the_median_over_people():
    tracks = {
        1: track((0.0, 0.02)),
        2: track((0.0, 0.04)),
        3: track((0.0, 0.0)),
    }
    assert movement(tracks, FAR)["walked_m_per_min"] == 12.0


def test_nth_is_none_when_fewer_were_removed():
    assert nth(np.array([1.0, 2.0]), 2) == 2.0
    assert nth(np.array([1.0, 2.0]), 3) is None


def test_outflow_of_a_complete_run():
    times = np.random.default_rng(0).permutation(np.arange(1.0, 81.0))
    assert outflow(times) == {
        "person_25": 25.0,
        "person_50": 50.0,
        "person_75": 75.0,
        "last": 80.0,
    }


def test_outflow_with_fewer_than_75_removals():
    card = outflow(np.arange(1.0, 61.0))
    assert card["person_50"] == 50.0
    assert card["person_75"] is None
    assert card["last"] == 60.0


def test_outflow_of_an_incomplete_run_has_no_last():
    assert outflow(np.arange(1.0, 81.0), complete=False)["last"] is None


def test_outflow_counts_against_the_reference():
    reference = DOOR_OPEN_TIME + 1 + np.arange(80.0)
    same = outflow(reference, reference)
    assert same["max_count_difference"] == 0
    # Three people out 1 s earlier: up to one person ahead at a time.
    early = reference.copy()
    early[:3] -= 1.0
    assert outflow(early, reference)["max_count_difference"] == 1
    assert outflow(reference[:70], reference)["max_count_difference"] == 10


def test_completion():
    assert completion(10, 10, 10) == {
        "remaining": 0,
        "pending": 0,
        "completed": True,
    }
    assert completion(10, 8, 8)["pending"] == 2
    left_inside = completion(10, 10, 7)
    assert left_inside["remaining"] == 3
    assert not left_inside["completed"]


def test_median_of_is_none_if_a_run_lacks_the_value():
    assert median_of([1.0, 2.0, 4.0]) == 2.0
    assert median_of([1.0, None, 4.0]) is None


def test_median_over_runs():
    runs = [
        {"seed": 0, "last": 10.0, "completed": True, "events": {"a": 1}},
        {"seed": 1, "last": None, "completed": False, "events": {"b": 4}},
        {"seed": 2, "last": 12.0, "completed": True, "events": {"a": 3}},
    ]
    card = median(runs)
    assert card["last"] is None
    assert card["completed"] is False
    assert card["events"] == {"a": 1.0, "b": 0.0}
    assert card["seeds"] == 3
    assert card["per_seed"] is runs
    assert "seed" not in card


PETRACK = """\
# id frame x y
1 0 0.5 10.0
1 3 0.6 11.0
1 5 0.5 10.0
1 4600 0.5 19.0
1 5000 0.5 20.5
1 5005 0.5 21.0
2 10 -1.0 5.0
2 4500 -1.0 6.0
"""


def test_experiment_reads_tracks_and_crossings(tmp_path):
    path = tmp_path / "petrack.txt"
    path.write_text(PETRACK)
    tracks, crossings = experiment(path)
    # Frames not divisible by 5 are dropped; tracks end at the door
    # opening (90.5 s = frame 4525).
    assert sorted(tracks) == [1.0, 2.0]
    np.testing.assert_array_equal(tracks[1.0], [[0.5, 10.0], [0.5, 10.0]])
    np.testing.assert_array_equal(tracks[2.0], [[-1.0, 5.0], [-1.0, 6.0]])
    np.testing.assert_array_equal(crossings, [100.0])


def fake_sim(time, positions):
    agents = [
        types.SimpleNamespace(id=i, position=p) for i, p in positions.items()
    ]
    return types.SimpleNamespace(
        agents=lambda: agents, elapsed_time=lambda: time
    )


def test_recorder_records_tracks_and_removals():
    ctrl = types.SimpleNamespace(states={1: None, 2: None})
    rec = Recorder()
    rec(fake_sim(0.0, {1: (0, 0), 2: (1, 0), 3: (2, 0)}), ctrl)
    rec(fake_sim(1.0, {1: (0, 1), 3: (2, 1)}), ctrl)
    rec(fake_sim(DOOR_OPEN_TIME, {1: (0, 2)}), ctrl)
    rec(fake_sim(DOOR_OPEN_TIME + 1, {}), ctrl)
    assert rec.tracks == {1: [(0, 0), (0, 1)], 2: [(1, 0)]}
    assert rec.removed == pytest.approx(
        [1.0, DOOR_OPEN_TIME, DOOR_OPEN_TIME + 1]
    )


def test_events_counts_overtaking_causes(tmp_path):
    log = tmp_path / "log.jsonl"
    records = [
        {"type": "metadata"},
        {"cause": "overtake_completed"},
        {"cause": "overtake_completed,overtake_abandoned_no_gap"},
        {"cause": "queue_joined"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in records))
    assert events(log) == {
        "overtake_completed": 2,
        "overtake_abandoned_no_gap": 1,
    }
