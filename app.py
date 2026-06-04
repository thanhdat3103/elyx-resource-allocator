from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_generator import generate_all_data
from src.scheduler import load_allocator_from_dir
from src.utils import load_json

DATA_DIR = Path("data")
REQUIRED_FILES = [
    DATA_DIR / "action_plan_100_activities.json",
    DATA_DIR / "client_schedule.json",
    DATA_DIR / "travel_plans.json",
    DATA_DIR / "equipment_availability.json",
    DATA_DIR / "specialists_availability.json",
    DATA_DIR / "allied_health_availability.json",
    DATA_DIR / "metadata.json",
]

st.set_page_config(page_title="Elyx Resource Allocator", layout="wide")


def ensure_sample_data() -> None:
    if not all(path.exists() for path in REQUIRED_FILES):
        generate_all_data(output_dir=DATA_DIR)


@st.cache_data(show_spinner=False)
def load_action_plan() -> list[dict]:
    return load_json(DATA_DIR / "action_plan_100_activities.json")


@st.cache_data(show_spinner=False)
def run_scheduler_cached(start_date: str | None, end_date: str | None) -> pd.DataFrame:
    allocator = load_allocator_from_dir(DATA_DIR)
    return allocator.schedule(start_date=start_date, end_date=end_date)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def main() -> None:
    ensure_sample_data()
    metadata = load_json(DATA_DIR / "metadata.json")
    action_plan = load_action_plan()

    st.title("Elyx Resource Allocator")
    st.caption("A constraint-aware scheduler that converts prioritized health recommendations into a personalized calendar.")

    with st.sidebar:
        st.header("Scheduler controls")
        st.write(f"Sample data range: **{metadata['start_date']}** to **{metadata['end_date']}**")
        start_date = st.date_input("Start date", value=pd.to_datetime(metadata["start_date"]).date())
        end_date = st.date_input("End date", value=pd.to_datetime(metadata["end_date"]).date())
        st.divider()
        st.write("Data included")
        st.write(f"Activities: **{len(action_plan)}**")
        st.write("Availability: client, travel, equipment, specialists, allied health")
        regenerate = st.button("Regenerate sample data")
        if regenerate:
            generate_all_data(output_dir=DATA_DIR)
            st.cache_data.clear()
            st.rerun()

    if start_date > end_date:
        st.error("Start date must be before end date.")
        return

    with st.spinner("Building personalized plan..."):
        plan_df = run_scheduler_cached(start_date.isoformat(), end_date.isoformat())

    scheduled_count = int((plan_df["status"] == "scheduled").sum()) if not plan_df.empty else 0
    backup_count = int((plan_df["status"] == "backup_used").sum()) if not plan_df.empty else 0
    unscheduled_count = int((plan_df["status"] == "unscheduled").sum()) if not plan_df.empty else 0
    total_count = len(plan_df)
    scheduled_rate = scheduled_count / total_count * 100 if total_count else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calendar rows", f"{total_count:,}")
    c2.metric("Scheduled", f"{scheduled_count:,}", f"{scheduled_rate:.1f}%")
    c3.metric("Backup used", f"{backup_count:,}")
    c4.metric("Unscheduled", f"{unscheduled_count:,}")

    st.subheader("Personalized calendar")
    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        activity_types = sorted(plan_df["activity_type"].dropna().unique().tolist()) if not plan_df.empty else []
        statuses = sorted(plan_df["status"].dropna().unique().tolist()) if not plan_df.empty else []
        selected_types = col1.multiselect("Activity type", activity_types, default=activity_types)
        selected_statuses = col2.multiselect("Status", statuses, default=statuses)
        text_query = col3.text_input("Search activity/facilitator/location")

    filtered = plan_df.copy()
    if selected_types:
        filtered = filtered[filtered["activity_type"].isin(selected_types)]
    if selected_statuses:
        filtered = filtered[filtered["status"].isin(selected_statuses)]
    if text_query:
        query = text_query.lower().strip()
        mask = (
            filtered["activity_name"].str.lower().str.contains(query, na=False)
            | filtered["facilitator"].str.lower().str.contains(query, na=False)
            | filtered["location"].str.lower().str.contains(query, na=False)
        )
        filtered = filtered[mask]

    display_columns = [
        "date",
        "start_time",
        "end_time",
        "activity_name",
        "activity_type",
        "priority",
        "facilitator_role",
        "facilitator",
        "equipment",
        "location",
        "mode",
        "status",
        "details",
        "metrics_to_collect",
        "notes",
    ]
    st.dataframe(filtered[display_columns], use_container_width=True, height=520)

    st.download_button(
        label="Download personalized plan as CSV",
        data=dataframe_to_csv_bytes(plan_df),
        file_name="generated_personalized_plan.csv",
        mime="text/csv",
    )

    st.subheader("Action plan preview")
    activity_df = pd.DataFrame(action_plan)
    st.dataframe(activity_df[["activity_id", "priority", "activity_type", "name", "frequency", "duration_minutes", "facilitator_role", "can_be_remote"]], use_container_width=True, height=300)

    st.subheader("Scheduling assumptions")
    st.markdown(
        """
        - Activities are scheduled by priority: lower priority number means higher health importance.
        - The scheduler uses 15-minute slot granularity.
        - During travel, in-person activities are blocked unless they can be performed remotely.
        - Required facilitators and equipment must both be available for the full activity duration.
        - Backup activities are used when the primary activity cannot be scheduled within the search window.
        - Unscheduled rows are retained with a reason instead of silently dropping activities.
        """
    )


if __name__ == "__main__":
    main()
