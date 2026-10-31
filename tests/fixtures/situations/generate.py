# SPDX-License-Identifier: LGPL-3.0-or-later

"""Write the static run-log fixtures for the situation extractor tests.

The files next to this script are committed; this script records how they
were made. Run it with ``python generate.py`` to rewrite them.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent

METADATA = {"scenario": "fixture", "type": "metadata"}


def dump(record: dict) -> str:
    return json.dumps(record, sort_keys=True)


def request(unit_index: int, decision_index: int) -> dict:
    unit_id = unit_index + 1
    return {
        "decision_index": decision_index,
        "events": [],
        "members": [unit_id],
        "observations": [{"agent_id": unit_id, "distance": 1.5}],
        "snapshot_time": float(decision_index),
        "states": [{"commitment_since": 0.0, "repertoire": "queueing"}],
        "type": "request",
        "unit_id": unit_id,
        "unit_index": unit_index,
    }


def response(unit_index: int, decision_index: int) -> dict:
    return {
        "decision_index": decision_index,
        "reasons": ["fixture"],
        "repertoires": ["queueing"],
        "snapshot_time": float(decision_index),
        "type": "response",
        "unit_id": unit_index + 1,
        "unit_index": unit_index,
    }


OBSERVATION = {"agent_id": 1, "time": 0.0, "type": "observation"}
TRANSITION = {
    "after": "queueing",
    "agent_id": 1,
    "before": "walking",
    "cause": "fixture",
    "group_id": None,
    "time": 0.0,
    "type": "transition",
    "unit_id": 1,
}


def pair(unit_index: int, decision_index: int) -> list[str]:
    return [
        dump(request(unit_index, decision_index)),
        dump(response(unit_index, decision_index)),
    ]


def complete() -> list[str]:
    lines = [dump(METADATA)]
    for key in [(0, 0), (1, 0), (0, 1)]:
        lines += pair(*key)
    return lines + [dump(OBSERVATION), dump(TRANSITION)]


def write(name: str, lines: list[str], *, final_newline: bool = True) -> None:
    text = "\n".join(lines) + ("\n" if final_newline and lines else "")
    (HERE / name).write_bytes(text.encode("utf-8"))


def main() -> None:
    base = complete()
    write("complete.jsonl", base)
    write("missing_response.jsonl", base[:6] + base[7:])
    write("duplicate_request.jsonl", base + [dump(request(0, 0))])
    write("duplicate_response.jsonl", base + [dump(response(0, 0))])
    write("orphan_response.jsonl", base + [dump(response(5, 0))])
    truncated = base[:-1] + [base[-1][: len(base[-1]) // 2]]
    write("not_json.jsonl", truncated, final_newline=False)
    nan_request = dump(request(0, 0)).replace('"snapshot_time": 0.0', '"snapshot_time": NaN')
    write("nan.jsonl", [dump(METADATA), nan_request])
    write("no_metadata.jsonl", base[1:])
    write("empty.jsonl", [])
    write("no_requests.jsonl", [dump(METADATA), dump(TRANSITION)])
    sampling = [dump(METADATA)]
    for i in range(20):
        sampling += pair(i % 3, i // 3)
    write("sampling.jsonl", sampling)
    expected = {
        "sampling.jsonl": {
            "5,42": [[0, 1], [1, 2], [0, 3], [2, 3], [0, 6]],
            "5,0": [[2, 0], [0, 1], [1, 3], [1, 4], [0, 6]],
            "50,42": "all",
        }
    }
    (HERE / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
