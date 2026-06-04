import tempfile
import unittest
from pathlib import Path

from src.data_generator import generate_all_data
from src.scheduler import load_allocator_from_dir


class SchedulerTests(unittest.TestCase):
    def test_generated_data_has_at_least_100_activities(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = generate_all_data(output_dir=tmp, num_activities=100)
            self.assertGreaterEqual(len(data["action_plan"]), 100)
            self.assertTrue((Path(tmp) / "action_plan_100_activities.json").exists())

    def test_scheduler_outputs_expected_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_all_data(output_dir=tmp, start_date="2026-06-09", months=1, num_activities=100)
            allocator = load_allocator_from_dir(tmp)
            df = allocator.schedule(start_date="2026-06-09", end_date="2026-06-15")
            required_columns = {
                "date",
                "start_time",
                "end_time",
                "activity_id",
                "activity_name",
                "activity_type",
                "priority",
                "facilitator_role",
                "status",
                "notes",
            }
            self.assertTrue(required_columns.issubset(df.columns))
            self.assertGreater(len(df), 0)

    def test_scheduler_uses_valid_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_all_data(output_dir=tmp, start_date="2026-06-09", months=1, num_activities=100)
            allocator = load_allocator_from_dir(tmp)
            df = allocator.schedule(start_date="2026-06-09", end_date="2026-06-20")
            valid_statuses = {"scheduled", "backup_used", "unscheduled"}
            self.assertTrue(set(df["status"].unique()).issubset(valid_statuses))


if __name__ == "__main__":
    unittest.main()
