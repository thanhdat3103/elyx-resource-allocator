from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import combine_dt, contains_interval, daterange, load_json, overlaps, parse_date

WINDOW_RANGES = {
    "morning": (6, 11),
    "midday": (11, 14),
    "afternoon": (14, 17),
    "evening": (17, 22),
}


@dataclass
class Booking:
    resource_id: str
    start: datetime
    end: datetime


@dataclass
class SchedulerState:
    client_bookings_by_date: dict[str, list[Booking]] = field(default_factory=lambda: defaultdict(list))
    resource_bookings: dict[str, list[Booking]] = field(default_factory=lambda: defaultdict(list))
    daily_load_minutes: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class ResourceAllocator:
    """Constraint-aware scheduler for a simplified Elyx Resource Allocator.

    The algorithm is intentionally explainable rather than mathematically optimal:
    1. Expand each action-plan item into required occurrences.
    2. Sort occurrences by activity priority.
    3. Try to place each occurrence into the earliest feasible client slot.
    4. Respect travel, facilitator, equipment, and double-booking constraints.
    5. Fall back to backup activities when the primary activity cannot be scheduled.
    """

    def __init__(
        self,
        action_plan: list[dict[str, Any]],
        client_schedule: list[dict[str, Any]],
        travel_plans: list[dict[str, Any]],
        equipment_availability: list[dict[str, Any]],
        specialists_availability: list[dict[str, Any]],
        allied_health_availability: list[dict[str, Any]],
        slot_granularity_minutes: int = 15,
    ) -> None:
        self.action_plan = sorted(action_plan, key=lambda item: item["priority"])
        self.client_schedule = client_schedule
        self.travel_plans = travel_plans
        self.equipment = equipment_availability
        self.specialists = specialists_availability
        self.allied_health = allied_health_availability
        self.slot_granularity = slot_granularity_minutes
        self.state = SchedulerState()
        self.client_slots_by_date = self._index_client_slots_by_date()
        self.people_by_role = self._index_people_by_role()
        self.equipment_by_name = self._index_equipment_by_name()
        self.available_slots_by_resource_date = self._index_available_slots_by_resource_date()

    def schedule(self, start_date: str | date | None = None, end_date: str | date | None = None) -> pd.DataFrame:
        start, end = self._resolve_schedule_dates(start_date, end_date)
        occurrences = self._expand_occurrences(start, end)
        rows: list[dict[str, Any]] = []

        for occurrence in occurrences:
            row = self._schedule_one(occurrence, start, end)
            rows.append(row)

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["date", "start_time", "priority", "activity_id"]).reset_index(drop=True)
        return df

    def _resolve_schedule_dates(self, start_date: str | date | None, end_date: str | date | None) -> tuple[date, date]:
        if start_date is not None and isinstance(start_date, str):
            start_date = parse_date(start_date)
        if end_date is not None and isinstance(end_date, str):
            end_date = parse_date(end_date)
        schedule_dates = [parse_date(slot["date"]) for slot in self.client_schedule]
        start = start_date or min(schedule_dates)
        end = end_date or max(schedule_dates)
        return start, end

    def _expand_occurrences(self, start: date, end: date) -> list[dict[str, Any]]:
        occurrences: list[dict[str, Any]] = []
        for activity in self.action_plan:
            frequency = activity["frequency"]
            times = int(frequency["times"])
            period = frequency["period"]

            if period == "day":
                for day in daterange(start, end):
                    for n in range(times):
                        occurrences.append({"activity": activity, "target_date": day, "occurrence_number": n + 1, "period": period})
            elif period == "week":
                current = start
                while current <= end:
                    week_start = current
                    week_end = min(week_start + timedelta(days=6), end)
                    candidate_days = list(daterange(week_start, week_end))
                    selected_days = self._spread_days(candidate_days, times)
                    for n, day in enumerate(selected_days, start=1):
                        occurrences.append({"activity": activity, "target_date": day, "occurrence_number": n, "period": period})
                    current = week_end + timedelta(days=1)
            elif period == "month":
                month_cursor = date(start.year, start.month, 1)
                while month_cursor <= end:
                    month_days = [d for d in daterange(max(start, month_cursor), min(end, self._last_day_of_month(month_cursor))) ]
                    selected_days = self._spread_days(month_days, times)
                    for n, day in enumerate(selected_days, start=1):
                        occurrences.append({"activity": activity, "target_date": day, "occurrence_number": n, "period": period})
                    if month_cursor.month == 12:
                        month_cursor = date(month_cursor.year + 1, 1, 1)
                    else:
                        month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
            else:
                raise ValueError(f"Unsupported frequency period: {period}")

        occurrences.sort(key=lambda item: (item["activity"]["priority"], item["target_date"], item["occurrence_number"]))
        return occurrences

    @staticmethod
    def _last_day_of_month(day: date) -> date:
        if day.month == 12:
            return date(day.year, 12, 31)
        return date(day.year, day.month + 1, 1) - timedelta(days=1)

    @staticmethod
    def _spread_days(days: list[date], count: int) -> list[date]:
        if not days or count <= 0:
            return []
        if count >= len(days):
            return days
        if count == 1:
            return [days[len(days) // 2]]
        selected = []
        for i in range(count):
            index = round(i * (len(days) - 1) / (count - 1))
            selected.append(days[index])
        return selected

    def _schedule_one(self, occurrence: dict[str, Any], start: date, end: date) -> dict[str, Any]:
        activity = occurrence["activity"]
        placement = self._find_placement(activity, occurrence["target_date"], start, end, is_backup=False)
        if placement is not None:
            return self._build_row(activity, occurrence, placement, status="scheduled", notes="Primary activity scheduled.")

        backup_placement = self._find_placement(activity, occurrence["target_date"], start, end, is_backup=True)
        if backup_placement is not None:
            backup_name = activity["backup_activities"][0] if activity.get("backup_activities") else "Backup activity"
            return self._build_row(activity, occurrence, backup_placement, status="backup_used", notes=f"Primary activity unavailable. Used backup: {backup_name}.", display_name=backup_name)

        return self._unscheduled_row(activity, occurrence, reason="No feasible slot satisfied client, travel, facilitator, equipment, and conflict constraints.")

    def _find_placement(
        self,
        activity: dict[str, Any],
        target_date: date,
        start: date,
        end: date,
        is_backup: bool,
    ) -> dict[str, Any] | None:
        search_days = self._candidate_dates(target_date, start, end, is_backup)
        duration = min(activity["duration_minutes"], 30) if is_backup else activity["duration_minutes"]
        required_equipment = [] if is_backup else activity.get("required_equipment", [])
        facilitator_type = "self" if is_backup else activity.get("facilitator_type", "self")
        facilitator_role = "Self" if is_backup else activity.get("facilitator_role", "Self")
        preferred_windows = activity.get("preferred_time_windows", [])

        candidates: list[dict[str, Any]] = []
        for day in search_days:
            for client_slot in self._client_slots_for_day(day):
                slot_start = combine_dt(day, client_slot["start"])
                slot_end = combine_dt(day, client_slot["end"])
                current = slot_start
                while current + timedelta(minutes=duration) <= slot_end:
                    candidate_end = current + timedelta(minutes=duration)
                    if not self._client_is_free(current, candidate_end):
                        current += timedelta(minutes=self.slot_granularity)
                        continue

                    in_travel = self._is_travel_day(day)
                    mode = "remote" if in_travel and (activity.get("can_be_remote") or is_backup) else "in_person"
                    if in_travel and mode != "remote":
                        current += timedelta(minutes=self.slot_granularity)
                        continue

                    facilitator = self._reserve_candidate_facilitator(
                        facilitator_type=facilitator_type,
                        facilitator_role=facilitator_role,
                        start_dt=current,
                        end_dt=candidate_end,
                        mode=mode,
                    )
                    if facilitator is None:
                        current += timedelta(minutes=self.slot_granularity)
                        continue

                    equipment = self._reserve_candidate_equipment(required_equipment, current, candidate_end, mode)
                    if equipment is None:
                        current += timedelta(minutes=self.slot_granularity)
                        continue

                    score = self._score_candidate(activity, current, target_date, preferred_windows, is_backup)
                    candidates.append({
                        "start_dt": current,
                        "end_dt": candidate_end,
                        "mode": mode,
                        "facilitator": facilitator,
                        "equipment": equipment,
                        "score": score,
                    })
                    current += timedelta(minutes=self.slot_granularity)

        if not candidates:
            return None

        candidates.sort(key=lambda item: item["score"])
        chosen = candidates[0]
        self._commit_booking(chosen)
        return chosen

    def _candidate_dates(self, target_date: date, start: date, end: date, is_backup: bool) -> list[date]:
        # Primary activities search near the target date. Backup activities can be placed in a wider window.
        radius = 3 if is_backup else 2
        dates = []
        for offset in range(0, radius + 1):
            for sign in [1, -1] if offset != 0 else [1]:
                candidate = target_date + timedelta(days=sign * offset)
                if start <= candidate <= end and candidate not in dates:
                    dates.append(candidate)
        return dates

    def _client_slots_for_day(self, day: date) -> list[dict[str, Any]]:
        return self.client_slots_by_date.get(day.isoformat(), [])

    def _client_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        bookings = self.state.client_bookings_by_date[start_dt.date().isoformat()]
        return not any(overlaps(start_dt, end_dt, booking.start, booking.end) for booking in bookings)

    def _resource_is_free(self, resource_id: str, start_dt: datetime, end_dt: datetime) -> bool:
        return not any(overlaps(start_dt, end_dt, booking.start, booking.end) for booking in self.state.resource_bookings[resource_id])

    def _is_travel_day(self, day: date) -> bool:
        for trip in self.travel_plans:
            if parse_date(trip["start_date"]) <= day <= parse_date(trip["end_date"]):
                return True
        return False

    def _index_client_slots_by_date(self) -> dict[str, list[dict[str, Any]]]:
        slots_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for slot in self.client_schedule:
            slots_by_date[slot["date"]].append(slot)
        return slots_by_date

    def _index_people_by_role(self) -> dict[str, list[dict[str, Any]]]:
        people: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for resource in self.specialists + self.allied_health:
            people[resource["role"]].append(resource)
        return people

    def _index_equipment_by_name(self) -> dict[str, list[dict[str, Any]]]:
        equipment: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for resource in self.equipment:
            equipment[resource["name"]].append(resource)
        return equipment

    def _index_available_slots_by_resource_date(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        index: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for resource in self.specialists + self.allied_health + self.equipment:
            resource_id = resource["resource_id"]
            for slot in resource["available_slots"]:
                index[resource_id][slot["date"]].append(slot)
        return index

    def _reserve_candidate_facilitator(
        self,
        facilitator_type: str,
        facilitator_role: str,
        start_dt: datetime,
        end_dt: datetime,
        mode: str,
    ) -> dict[str, str]:
        if facilitator_type == "self" or facilitator_role == "Self":
            return {"resource_id": "SELF", "name": "Self", "role": "Self"}

        resources = self.people_by_role.get(facilitator_role, [])
        for resource in resources:
            if self._resource_has_available_slot(resource, start_dt, end_dt, mode):
                return {"resource_id": resource["resource_id"], "name": resource["name"], "role": resource["role"]}
        return None

    def _reserve_candidate_equipment(
        self,
        equipment_names: list[str],
        start_dt: datetime,
        end_dt: datetime,
        mode: str,
    ) -> list[dict[str, str]] | None:
        reserved = []
        if mode == "remote":
            # During travel, only portable self-managed equipment is assumed available.
            portable = {"Yoga Mat", "Glucose Meter", "Blood Pressure Cuff", "Resistance Bands"}
            if all(name in portable for name in equipment_names):
                return [{"resource_id": f"PORTABLE-{name}", "name": name, "role": name} for name in equipment_names]
            return [] if not equipment_names else None

        for name in equipment_names:
            resources = self.equipment_by_name.get(name, [])
            matched = None
            for resource in resources:
                if self._resource_has_available_slot(resource, start_dt, end_dt, mode="in_person"):
                    matched = {"resource_id": resource["resource_id"], "name": resource["name"], "role": resource["role"]}
                    break
            if matched is None:
                return None
            reserved.append(matched)
        return reserved

    def _resource_has_available_slot(self, resource: dict[str, Any], start_dt: datetime, end_dt: datetime, mode: str) -> bool:
        for slot in self.available_slots_by_resource_date[resource["resource_id"]].get(start_dt.date().isoformat(), []):
            slot_start = combine_dt(slot["date"], slot["start"])
            slot_end = combine_dt(slot["date"], slot["end"])
            slot_mode = slot.get("mode", "both")
            mode_ok = slot_mode == "both" or slot_mode == mode or mode == "remote" and slot_mode == "remote"
            if mode_ok and contains_interval(slot_start, slot_end, start_dt, end_dt) and self._resource_is_free(resource["resource_id"], start_dt, end_dt):
                return True
        return False

    def _score_candidate(self, activity: dict[str, Any], start_dt: datetime, target_date: date, preferred_windows: list[str], is_backup: bool) -> tuple[int, int, int, int, datetime]:
        day_distance = abs((start_dt.date() - target_date).days)
        hour = start_dt.hour
        preferred_penalty = 0 if any(WINDOW_RANGES[w][0] <= hour < WINDOW_RANGES[w][1] for w in preferred_windows if w in WINDOW_RANGES) else 1
        daily_load = self.state.daily_load_minutes[start_dt.date().isoformat()]
        backup_penalty = 1 if is_backup else 0
        return (backup_penalty, day_distance, preferred_penalty, daily_load, start_dt)

    def _commit_booking(self, placement: dict[str, Any]) -> None:
        start_dt = placement["start_dt"]
        end_dt = placement["end_dt"]
        date_key = start_dt.date().isoformat()
        self.state.client_bookings_by_date[date_key].append(Booking("CLIENT", start_dt, end_dt))
        self.state.daily_load_minutes[date_key] += int((end_dt - start_dt).total_seconds() // 60)
        facilitator = placement["facilitator"]
        if facilitator["resource_id"] != "SELF":
            self.state.resource_bookings[facilitator["resource_id"]].append(Booking(facilitator["resource_id"], start_dt, end_dt))
        for resource in placement.get("equipment", []) or []:
            if not resource["resource_id"].startswith("PORTABLE"):
                self.state.resource_bookings[resource["resource_id"]].append(Booking(resource["resource_id"], start_dt, end_dt))

    def _build_row(
        self,
        activity: dict[str, Any],
        occurrence: dict[str, Any],
        placement: dict[str, Any],
        status: str,
        notes: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        start_dt = placement["start_dt"]
        end_dt = placement["end_dt"]
        equipment = placement.get("equipment", []) or []
        return {
            "date": start_dt.date().isoformat(),
            "start_time": start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M"),
            "activity_id": activity["activity_id"],
            "activity_name": display_name or activity["name"],
            "original_activity_name": activity["name"],
            "activity_type": activity["activity_type"],
            "priority": activity["priority"],
            "occurrence_number": occurrence["occurrence_number"],
            "frequency_period": occurrence["period"],
            "duration_minutes": int((end_dt - start_dt).total_seconds() // 60),
            "facilitator": placement["facilitator"]["name"],
            "facilitator_role": placement["facilitator"]["role"],
            "equipment": ", ".join(resource["name"] for resource in equipment),
            "location": self._choose_location(activity, placement["mode"]),
            "mode": placement["mode"],
            "status": status,
            "details": activity["details"],
            "prep_required": activity["prep_required"],
            "metrics_to_collect": ", ".join(activity["metrics_to_collect"]),
            "if_skipped_adjustment": activity["if_skipped_adjustment"],
            "notes": notes,
        }

    def _unscheduled_row(self, activity: dict[str, Any], occurrence: dict[str, Any], reason: str) -> dict[str, Any]:
        target_date = occurrence["target_date"]
        return {
            "date": target_date.isoformat(),
            "start_time": "",
            "end_time": "",
            "activity_id": activity["activity_id"],
            "activity_name": activity["name"],
            "original_activity_name": activity["name"],
            "activity_type": activity["activity_type"],
            "priority": activity["priority"],
            "occurrence_number": occurrence["occurrence_number"],
            "frequency_period": occurrence["period"],
            "duration_minutes": activity["duration_minutes"],
            "facilitator": activity["facilitator_role"],
            "facilitator_role": activity["facilitator_role"],
            "equipment": ", ".join(activity.get("required_equipment", [])),
            "location": ", ".join(activity.get("location_options", [])),
            "mode": "",
            "status": "unscheduled",
            "details": activity["details"],
            "prep_required": activity["prep_required"],
            "metrics_to_collect": ", ".join(activity["metrics_to_collect"]),
            "if_skipped_adjustment": activity["if_skipped_adjustment"],
            "notes": reason,
        }

    @staticmethod
    def _choose_location(activity: dict[str, Any], mode: str) -> str:
        if mode == "remote":
            return "Online"
        locations = activity.get("location_options", [])
        preferred = [loc for loc in locations if loc != "Online"]
        return preferred[0] if preferred else "Home"


def load_allocator_from_dir(data_dir: str | Path) -> ResourceAllocator:
    data_dir = Path(data_dir)
    return ResourceAllocator(
        action_plan=load_json(data_dir / "action_plan_100_activities.json"),
        client_schedule=load_json(data_dir / "client_schedule.json"),
        travel_plans=load_json(data_dir / "travel_plans.json"),
        equipment_availability=load_json(data_dir / "equipment_availability.json"),
        specialists_availability=load_json(data_dir / "specialists_availability.json"),
        allied_health_availability=load_json(data_dir / "allied_health_availability.json"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Elyx Resource Allocator scheduler.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="data/generated_personalized_plan.csv")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()

    allocator = load_allocator_from_dir(args.data_dir)
    df = allocator.schedule(start_date=args.start_date, end_date=args.end_date)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    scheduled = int((df["status"] == "scheduled").sum()) if not df.empty else 0
    backups = int((df["status"] == "backup_used").sum()) if not df.empty else 0
    unscheduled = int((df["status"] == "unscheduled").sum()) if not df.empty else 0
    print(f"Wrote {len(df)} calendar rows to {output_path}")
    print(f"Scheduled: {scheduled} | Backup used: {backups} | Unscheduled: {unscheduled}")


if __name__ == "__main__":
    main()
