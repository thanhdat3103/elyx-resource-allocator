from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.utils import daterange, ensure_dir, save_json

RANDOM_SEED = 42

ACTIVITY_TYPES = [
    "Fitness routine / exercise",
    "Food consumption",
    "Medication consumption",
    "Therapy",
    "Consultation",
]

EXERCISE_TEMPLATES = [
    ("Zone 2 Run", "Maintain heart rate between 120-140 bpm", ["heart_rate", "duration", "perceived_exertion"], ["Park", "Gym", "Hotel Gym"], ["Treadmill"]),
    ("Strength Training", "Full-body resistance session with controlled tempo", ["sets", "reps", "load", "RPE"], ["Gym", "Home Gym"], ["Dumbbells", "Resistance Bands"]),
    ("Mobility Flow", "Hip, ankle, thoracic spine, and shoulder mobility", ["duration", "pain_score", "range_of_motion"], ["Home", "Hotel Room", "Gym"], ["Yoga Mat"]),
    ("Eye Exercise", "Near-far focus drill and 20-20-20 visual breaks", ["duration", "eye_strain_score"], ["Home", "Office", "Hotel Room"], []),
    ("Brisk Walk", "Low-intensity walk after meals", ["steps", "duration", "glucose_response"], ["Park", "Home", "Hotel"], []),
]

FOOD_TEMPLATES = [
    ("High-Protein Breakfast", "Consume 30-40g protein within 2 hours of waking", ["protein_g", "calories", "satiety_score"], ["Home", "Hotel", "Office"], []),
    ("Mediterranean Lunch", "Vegetables, lean protein, olive oil, and whole grains", ["calories", "fiber_g", "protein_g"], ["Home", "Office", "Restaurant"], []),
    ("Hydration Protocol", "Drink 500ml water with electrolytes", ["water_ml", "electrolyte_serving"], ["Home", "Office", "Hotel"], []),
    ("Low-Glycemic Dinner", "Control evening carbohydrate load", ["carbs_g", "glucose_response", "sleep_quality"], ["Home", "Restaurant", "Hotel"], []),
    ("Fermented Food Serving", "Add yogurt, kimchi, kefir, or sauerkraut", ["serving_size", "GI_comfort_score"], ["Home", "Office", "Hotel"], []),
]

MEDICATION_TEMPLATES = [
    ("Omega-3 Supplement", "Take after meal to improve tolerance", ["dose_mg", "adherence"], ["Home", "Office", "Hotel"], []),
    ("Vitamin D3", "Take with fat-containing meal", ["dose_IU", "adherence"], ["Home", "Office", "Hotel"], []),
    ("Magnesium Glycinate", "Take 60 minutes before bedtime", ["dose_mg", "sleep_quality", "adherence"], ["Home", "Hotel"], []),
    ("Glucose Monitor Check", "Record fasting glucose and notes", ["glucose_mg_dL", "fasting_hours"], ["Home", "Hotel"], ["Glucose Meter"]),
    ("Blood Pressure Reading", "Measure seated blood pressure after 5 minutes rest", ["systolic", "diastolic", "resting_hr"], ["Home", "Hotel", "Clinic"], ["Blood Pressure Cuff"]),
]

THERAPY_TEMPLATES = [
    ("Sauna Session", "15-20 minutes moderate heat exposure", ["duration", "temperature", "recovery_score"], ["Wellness Center", "Gym"], ["Sauna"]),
    ("Cold Plunge", "2-3 minutes controlled cold exposure", ["duration", "temperature", "stress_score"], ["Wellness Center", "Gym"], ["Cold Plunge"]),
    ("Breathwork", "Box breathing or physiological sigh protocol", ["duration", "stress_score", "HRV"], ["Home", "Office", "Hotel"], []),
    ("Guided Meditation", "Mindfulness session with body scan", ["duration", "mood_score", "sleep_quality"], ["Home", "Hotel", "Office"], []),
    ("Recovery Stretch", "Parasympathetic evening stretch routine", ["duration", "muscle_tightness_score"], ["Home", "Hotel", "Gym"], ["Yoga Mat"]),
]

CONSULTATION_TEMPLATES = [
    ("Fitness Coaching Check-in", "Review training load, soreness, and next progression", ["training_load", "soreness", "adherence"], ["Gym", "Online"], []),
    ("Dietitian Consultation", "Review food log and adjust macro targets", ["protein_g", "fiber_g", "weight_trend"], ["Clinic", "Online"], []),
    ("Physiotherapy Review", "Assess mobility limitation and exercise form", ["pain_score", "range_of_motion", "exercise_tolerance"], ["Clinic", "Online"], ["Yoga Mat"]),
    ("Physician Follow-up", "Review biomarkers and medication tolerance", ["blood_markers", "symptoms", "adherence"], ["Clinic", "Online"], []),
    ("Sleep Coaching Session", "Review sleep timing, routine, and wearable trends", ["sleep_duration", "sleep_efficiency", "HRV"], ["Online", "Clinic"], []),
]

SPECIALIST_ROLES = ["Fitness Trainer", "Physician", "Health Coach", "Sleep Specialist", "Phlebotomist"]
ALLIED_ROLES = ["Dietitian", "Physiotherapist", "Occupational Therapist", "Psychologist"]


def add_months_approx(start: date, months: int) -> date:
    return start + timedelta(days=30 * months - 1)


def frequency_for(activity_type: str, index: int) -> dict[str, Any]:
    # The generated dataset contains 100+ action-plan entries. To keep the final
    # three-month calendar realistic, each entry is recurring but not excessively dense.
    if activity_type == "Medication consumption":
        return {"times": random.choice([1, 1, 2]), "period": "week"}
    if activity_type == "Food consumption":
        return {"times": random.choice([1, 2]), "period": "week"}
    if activity_type == "Fitness routine / exercise":
        return {"times": random.choice([1, 2]), "period": "week"}
    if activity_type == "Therapy":
        return {"times": 1, "period": "week"}
    return {"times": 1, "period": "month"}


def preferred_windows_for(activity_type: str, name: str) -> list[str]:
    if "Breakfast" in name:
        return ["morning"]
    if "Lunch" in name:
        return ["midday"]
    if "Dinner" in name or "Magnesium" in name or "Recovery" in name:
        return ["evening"]
    if activity_type == "Fitness routine / exercise":
        return random.choice([["morning"], ["evening"], ["morning", "evening"]])
    if activity_type == "Consultation":
        return ["midday", "afternoon"]
    if activity_type == "Therapy":
        return ["evening", "afternoon"]
    return ["morning", "midday", "evening"]


def facilitator_for(activity_type: str, name: str) -> tuple[str, str]:
    if activity_type in ["Food consumption", "Medication consumption"]:
        return "self", "Self"
    if "Dietitian" in name:
        return "allied_health", "Dietitian"
    if "Physiotherapy" in name:
        return "allied_health", "Physiotherapist"
    if "Physician" in name:
        return "specialist", "Physician"
    if "Sleep" in name:
        return "specialist", "Sleep Specialist"
    if "Fitness" in name or activity_type == "Fitness routine / exercise":
        return "specialist", "Fitness Trainer"
    if activity_type == "Therapy":
        return random.choice([("self", "Self"), ("specialist", "Health Coach")])
    return "specialist", "Health Coach"


def duration_for(activity_type: str, name: str) -> int:
    if activity_type == "Medication consumption":
        return random.choice([10, 15])
    if activity_type == "Food consumption":
        return random.choice([20, 30, 45])
    if activity_type == "Consultation":
        return random.choice([30, 45, 60])
    if "Run" in name or "Strength" in name:
        return random.choice([45, 60])
    if activity_type == "Therapy":
        return random.choice([20, 30, 45])
    return random.choice([15, 30, 45])


def make_activity(activity_id: int, activity_type: str, template: tuple[str, str, list[str], list[str], list[str]], priority: int) -> dict[str, Any]:
    name, details, metrics, locations, equipment = template
    facilitator_type, facilitator_role = facilitator_for(activity_type, name)
    can_be_remote = (
        activity_type in ["Medication consumption", "Food consumption"]
        or "Online" in locations
        or name in ["Breathwork", "Guided Meditation", "Eye Exercise", "Sleep Coaching Session"]
    )
    prep_map = {
        "Fitness routine / exercise": "Wear appropriate training clothes, prepare water, and confirm recovery status.",
        "Food consumption": "Prepare or order the meal according to the assigned nutrition guideline.",
        "Medication consumption": "Confirm dose, timing, and any meal requirement before taking it.",
        "Therapy": "Confirm facility availability and avoid heavy meals immediately before the session.",
        "Consultation": "Prepare recent logs, wearable data, questions, and any relevant lab results.",
    }
    backup_map = {
        "Fitness routine / exercise": ["Brisk Walk", "Mobility Flow", "Indoor Cycling"],
        "Food consumption": ["Protein Shake", "Mediterranean Meal Bowl", "Low-Glycemic Snack"],
        "Medication consumption": ["Reschedule Dose Reminder", "Clinician Review Required"],
        "Therapy": ["Breathwork", "Guided Meditation", "Recovery Stretch"],
        "Consultation": ["Remote Check-in", "Async Form Review", "Reschedule Consultation"],
    }
    adjustment_map = {
        "Fitness routine / exercise": "Reschedule within the same week if possible; otherwise reduce next session intensity by 10%.",
        "Food consumption": "Return to the plan at the next meal and note the reason for deviation.",
        "Medication consumption": "Follow clinician-approved missed-dose guidance and log the missed dose.",
        "Therapy": "Replace with breathwork or recovery stretch and avoid stacking intense recovery sessions next day.",
        "Consultation": "Use the earliest remote or in-person follow-up slot and share logs asynchronously.",
    }
    return {
        "activity_id": f"ACT{activity_id:03d}",
        "priority": priority,
        "activity_type": activity_type,
        "name": f"{name} #{activity_id:03d}",
        "frequency": frequency_for(activity_type, activity_id),
        "duration_minutes": duration_for(activity_type, name),
        "details": details,
        "facilitator_type": facilitator_type,
        "facilitator_role": facilitator_role,
        "location_options": locations,
        "can_be_remote": can_be_remote,
        "required_equipment": equipment,
        "prep_required": prep_map[activity_type],
        "backup_activities": backup_map[activity_type],
        "if_skipped_adjustment": adjustment_map[activity_type],
        "metrics_to_collect": metrics,
        "preferred_time_windows": preferred_windows_for(activity_type, name),
    }


def generate_action_plan(num_activities: int = 120) -> list[dict[str, Any]]:
    templates_by_type = {
        "Fitness routine / exercise": EXERCISE_TEMPLATES,
        "Food consumption": FOOD_TEMPLATES,
        "Medication consumption": MEDICATION_TEMPLATES,
        "Therapy": THERAPY_TEMPLATES,
        "Consultation": CONSULTATION_TEMPLATES,
    }
    activities: list[dict[str, Any]] = []
    for i in range(1, num_activities + 1):
        activity_type = ACTIVITY_TYPES[(i - 1) % len(ACTIVITY_TYPES)]
        template = templates_by_type[activity_type][((i - 1) // len(ACTIVITY_TYPES)) % len(templates_by_type[activity_type])]
        priority = i
        activities.append(make_activity(i, activity_type, template, priority))
    return activities


def generate_client_schedule(start: date, end: date) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for day in daterange(start, end):
        weekday = day.weekday()
        if weekday < 5:
            windows = [("06:00", "10:00"), ("12:00", "13:30"), ("17:00", "21:00")]
        else:
            windows = [("08:00", "12:00"), ("14:00", "18:30")]
        for start_time, end_time in windows:
            slots.append({
                "date": day.isoformat(),
                "start": start_time,
                "end": end_time,
                "availability_type": "client_available",
            })
    return slots


def generate_travel_plans(start: date, end: date) -> list[dict[str, Any]]:
    trips = []
    trip_specs = [
        (start + timedelta(days=12), 3, "Singapore business trip"),
        (start + timedelta(days=35), 5, "Tokyo conference"),
        (start + timedelta(days=67), 4, "Seoul family travel"),
    ]
    for idx, (trip_start, length, label) in enumerate(trip_specs, start=1):
        trip_end = min(trip_start + timedelta(days=length - 1), end)
        trips.append({
            "travel_id": f"TRV{idx:03d}",
            "start_date": trip_start.isoformat(),
            "end_date": trip_end.isoformat(),
            "description": label,
            "constraint": "in_person_activities_unavailable; remote_activities_allowed",
        })
    return trips


def resource_windows_for_role(role: str, day: date) -> list[tuple[str, str, str]]:
    weekday = day.weekday()
    if role == "Fitness Trainer":
        return [("06:00", "09:00", "in_person"), ("17:00", "20:00", "both")] if weekday < 6 else [("08:00", "12:00", "both")]
    if role == "Physician":
        return [("10:00", "12:00", "both"), ("14:00", "16:00", "in_person")] if weekday in [1, 3] else []
    if role == "Health Coach":
        return [("07:00", "11:00", "remote"), ("16:00", "20:00", "both")] if weekday < 5 else [("09:00", "11:00", "remote")]
    if role == "Sleep Specialist":
        return [("18:00", "21:00", "remote")] if weekday in [0, 2, 4] else []
    if role == "Phlebotomist":
        return [("07:00", "10:00", "in_person")] if weekday in [0, 2, 4] else []
    if role == "Dietitian":
        return [("12:00", "15:00", "both")] if weekday in [0, 2, 4] else []
    if role == "Physiotherapist":
        return [("08:00", "11:00", "in_person"), ("17:00", "19:00", "both")] if weekday in [1, 3, 5] else []
    if role == "Occupational Therapist":
        return [("13:00", "17:00", "both")] if weekday in [1, 4] else []
    if role == "Psychologist":
        return [("16:00", "20:00", "remote")] if weekday in [1, 3] else []
    return []


def generate_people_availability(start: date, end: date, roles: list[str], prefix: str) -> list[dict[str, Any]]:
    resources = []
    for idx, role in enumerate(roles, start=1):
        slots = []
        for day in daterange(start, end):
            for start_time, end_time, mode in resource_windows_for_role(role, day):
                if random.random() < 0.12:
                    continue
                slots.append({
                    "date": day.isoformat(),
                    "start": start_time,
                    "end": end_time,
                    "mode": mode,
                })
        resources.append({
            "resource_id": f"{prefix}{idx:03d}",
            "name": f"{role} {idx}",
            "role": role,
            "available_slots": slots,
        })
    return resources


def generate_equipment_availability(start: date, end: date) -> list[dict[str, Any]]:
    equipment_specs = {
        "Treadmill": [("06:00", "10:00"), ("17:00", "21:00")],
        "Dumbbells": [("06:00", "21:00")],
        "Resistance Bands": [("06:00", "21:00")],
        "Yoga Mat": [("06:00", "21:00")],
        "Glucose Meter": [("06:00", "22:00")],
        "Blood Pressure Cuff": [("06:00", "22:00")],
        "Sauna": [("07:00", "11:00"), ("16:00", "21:00")],
        "Cold Plunge": [("07:00", "11:00"), ("16:00", "21:00")],
    }
    resources = []
    for idx, (name, windows) in enumerate(equipment_specs.items(), start=1):
        slots = []
        for day in daterange(start, end):
            if random.random() < 0.08:
                continue
            for start_time, end_time in windows:
                slots.append({
                    "date": day.isoformat(),
                    "start": start_time,
                    "end": end_time,
                    "mode": "in_person",
                })
        resources.append({
            "resource_id": f"EQ{idx:03d}",
            "name": name,
            "role": name,
            "available_slots": slots,
        })
    return resources


def generate_all_data(output_dir: str | Path = "data", start_date: str = "2026-06-09", months: int = 3, num_activities: int = 100) -> dict[str, Any]:
    random.seed(RANDOM_SEED)
    out = ensure_dir(output_dir)
    start = date.fromisoformat(start_date)
    end = add_months_approx(start, months)

    data = {
        "action_plan": generate_action_plan(num_activities),
        "client_schedule": generate_client_schedule(start, end),
        "travel_plans": generate_travel_plans(start, end),
        "equipment_availability": generate_equipment_availability(start, end),
        "specialists_availability": generate_people_availability(start, end, SPECIALIST_ROLES, "SP"),
        "allied_health_availability": generate_people_availability(start, end, ALLIED_ROLES, "AH"),
        "metadata": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "months": months,
            "num_activities": num_activities,
            "random_seed": RANDOM_SEED,
        },
    }

    save_json(data["action_plan"], out / "action_plan_100_activities.json")
    save_json(data["client_schedule"], out / "client_schedule.json")
    save_json(data["travel_plans"], out / "travel_plans.json")
    save_json(data["equipment_availability"], out / "equipment_availability.json")
    save_json(data["specialists_availability"], out / "specialists_availability.json")
    save_json(data["allied_health_availability"], out / "allied_health_availability.json")
    save_json(data["metadata"], out / "metadata.json")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic but realistic Elyx Resource Allocator data.")
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--start-date", default="2026-06-09")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--num-activities", type=int, default=100)
    args = parser.parse_args()
    data = generate_all_data(args.output_dir, args.start_date, args.months, args.num_activities)
    print(f"Generated {len(data['action_plan'])} activities from {data['metadata']['start_date']} to {data['metadata']['end_date']} in {args.output_dir}")


if __name__ == "__main__":
    main()
