from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FMT).date()


def parse_time(value: str) -> time:
    return datetime.strptime(value, TIME_FMT).time()


def combine_dt(day: str | date, clock: str | time) -> datetime:
    if isinstance(day, str):
        day = parse_date(day)
    if isinstance(clock, str):
        clock = parse_time(clock)
    return datetime.combine(day, clock)


def minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def contains_interval(outer_start: datetime, outer_end: datetime, inner_start: datetime, inner_end: datetime) -> bool:
    return outer_start <= inner_start and inner_end <= outer_end


def daterange(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
