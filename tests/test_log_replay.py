import json
from pathlib import Path

LOG_PATH = Path("chat.log")
REQUIRED_EVENTS = ("chat.turn", "tool.call", "context.compress")


def read_records():
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def test_every_line_is_valid_json():
    records = read_records()
    assert len(records) > 0


def test_required_events_present():
    events = set()
    for record in read_records():
        events.add(record["event"])
    for name in REQUIRED_EVENTS:
        assert name in events
