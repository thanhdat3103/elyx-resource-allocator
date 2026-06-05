import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_generator import generate_all_data
from src.scheduler import load_allocator_from_dir


class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls.temp_dir.name)

        generate_all_data(
            output_dir=cls.data_dir,
            start_date="2026-06-09",
            months=1,
            num_activities=100,
        )

        cls.allocator = load_allocator_from_dir(cls.data_dir)
        cls.df = cls.allocator.schedule(
            start_date="2026-06-09",
            end_date="2026-06-20",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_generated_data_has_at_least_100_activities(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = generate_all_data(output_dir=tmp, num_activities=100)

            self.assertGreaterEqual(len(data["action_plan"]), 100)
            self.assertTrue((Path(tmp) / "action_plan_100_activities.json").exists())

    def test_required_source_files_exist_after_generation(self):
        expected_files = [
            "action_plan_100_activities.json",
            "client_schedule.json",
            "travel_plans.json",
            "equipment_availability.json",
            "specialists_availability.json",
            "allied_health_availability.json",
            "metadata.json",
        ]

        for filename in expected_files:
            with self.subTest(filename=filename):
                self.assertTrue((self.data_dir / filename).exists())

    def test_scheduler_outputs_expected_columns(self):
        required_columns = {
            "date",
            "start_time",
            "end_time",
            "activity_id",
            "activity_name",
            "activity_type",
            "priority",
            "facilitator_role",
            "facilitator",
            "equipment",
            "location",
            "mode",
            "status",
            "notes",
        }

        self.assertTrue(required_columns.issubset(self.df.columns))
        self.assertGreater(len(self.df), 0)

    def test_scheduler_uses_valid_statuses(self):
        valid_statuses = {"scheduled", "backup_used", "unscheduled"}
        self.assertTrue(set(self.df["status"].unique()).issubset(valid_statuses))

    def test_scheduled_rows_have_valid_times(self):
        scheduled = self.df[self.df["status"].isin(["scheduled", "backup_used"])].copy()

        self.assertGreater(len(scheduled), 0)
        self.assertTrue(scheduled["start_time"].fillna("").astype(str).str.len().gt(0).all())
        self.assertTrue(scheduled["end_time"].fillna("").astype(str).str.len().gt(0).all())

        scheduled["start_dt"] = pd.to_datetime(
            scheduled["date"].astype(str) + " " + scheduled["start_time"].astype(str),
            errors="coerce",
        )
        scheduled["end_dt"] = pd.to_datetime(
            scheduled["date"].astype(str) + " " + scheduled["end_time"].astype(str),
            errors="coerce",
        )

        self.assertFalse(scheduled["start_dt"].isna().any())
        self.assertFalse(scheduled["end_dt"].isna().any())
        self.assertTrue((scheduled["end_dt"] > scheduled["start_dt"]).all())

    def test_no_overlapping_scheduled_client_rows(self):
        scheduled = self.df[self.df["status"].isin(["scheduled", "backup_used"])].copy()

        scheduled["start_dt"] = pd.to_datetime(
            scheduled["date"].astype(str) + " " + scheduled["start_time"].astype(str),
            errors="coerce",
        )
        scheduled["end_dt"] = pd.to_datetime(
            scheduled["date"].astype(str) + " " + scheduled["end_time"].astype(str),
            errors="coerce",
        )

        scheduled = scheduled.dropna(subset=["start_dt", "end_dt"])

        for date, group in scheduled.groupby("date"):
            group = group.sort_values("start_dt")
            previous_end = None

            for _, row in group.iterrows():
                if previous_end is not None:
                    self.assertGreaterEqual(
                        row["start_dt"],
                        previous_end,
                        msg=f"Overlap detected on {date}",
                    )

                if previous_end is None:
                    previous_end = row["end_dt"]
                else:
                    previous_end = max(previous_end, row["end_dt"])

    def test_backup_rows_have_notes_when_present(self):
        backup_rows = self.df[self.df["status"] == "backup_used"]

        if not backup_rows.empty:
            self.assertTrue(backup_rows["notes"].fillna("").astype(str).str.len().gt(0).all())

    def test_unscheduled_rows_have_reason_notes_when_present(self):
        unscheduled_rows = self.df[self.df["status"] == "unscheduled"]

        if not unscheduled_rows.empty:
            self.assertTrue(unscheduled_rows["notes"].fillna("").astype(str).str.len().gt(0).all())


if __name__ == "__main__":
    unittest.main()