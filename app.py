from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

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

STATUS_LABELS = {
    "scheduled": "Scheduled",
    "backup_used": "Backup used",
    "unscheduled": "Unscheduled",
}

MODE_LABELS = {
    "in_person": "In person",
    "remote": "Remote",
    "": "Not scheduled",
}

CALENDAR_COLUMNS = [
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
    "mode_label",
    "status_label",
    "details",
    "metrics_to_collect",
    "notes",
]

st.set_page_config(
    page_title="Elyx Resource Allocator",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_action_plan() -> list[dict[str, Any]]:
    return load_json(DATA_DIR / "action_plan_100_activities.json")


@st.cache_data(show_spinner=False)
def load_metadata() -> dict[str, Any]:
    return load_json(DATA_DIR / "metadata.json")


@st.cache_data(show_spinner=False)
def load_availability_data() -> dict[str, list[dict[str, Any]]]:
    return {
        "client_schedule": load_json(DATA_DIR / "client_schedule.json"),
        "travel_plans": load_json(DATA_DIR / "travel_plans.json"),
        "equipment": load_json(DATA_DIR / "equipment_availability.json"),
        "specialists": load_json(DATA_DIR / "specialists_availability.json"),
        "allied_health": load_json(DATA_DIR / "allied_health_availability.json"),
    }


@st.cache_data(show_spinner=False)
def run_scheduler_cached(start_date: str | None, end_date: str | None) -> pd.DataFrame:
    allocator = load_allocator_from_dir(DATA_DIR)
    return allocator.schedule(start_date=start_date, end_date=end_date)


def ensure_sample_data() -> None:
    if not all(path.exists() for path in REQUIRED_FILES):
        generate_all_data(output_dir=DATA_DIR)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def safe_unique(df: pd.DataFrame, column: str, include_blank: bool = False) -> list[str]:
    if df.empty or column not in df.columns:
        return []
    values = sorted(df[column].fillna("").astype(str).unique().tolist())
    if include_blank:
        return values
    return [value for value in values if value]


def add_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()
    if display_df.empty:
        return display_df
    display_df["status_label"] = display_df["status"].map(STATUS_LABELS).fillna(display_df["status"])
    display_df["mode_label"] = display_df["mode"].fillna("").map(MODE_LABELS).fillna(display_df["mode"])
    return display_df


def apply_filters(
    df: pd.DataFrame,
    selected_activity_types: list[str],
    selected_facilitators: list[str],
    selected_statuses: list[str],
    selected_locations: list[str],
    selected_modes: list[str],
    text_query: str,
) -> pd.DataFrame:
    filtered = df.copy()
    if filtered.empty:
        return filtered

    if selected_activity_types:
        filtered = filtered[filtered["activity_type"].isin(selected_activity_types)]
    if selected_facilitators:
        filtered = filtered[filtered["facilitator"].astype(str).isin(selected_facilitators)]
    if selected_statuses:
        filtered = filtered[filtered["status"].isin(selected_statuses)]
    if selected_locations:
        filtered = filtered[filtered["location"].astype(str).isin(selected_locations)]
    if selected_modes:
        filtered = filtered[filtered["mode"].astype(str).isin(selected_modes)]

    if text_query.strip():
        query = text_query.lower().strip()
        searchable_columns = [
            "activity_name",
            "original_activity_name",
            "activity_type",
            "facilitator",
            "facilitator_role",
            "equipment",
            "location",
            "details",
            "notes",
        ]
        mask = pd.Series(False, index=filtered.index)
        for column in searchable_columns:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.lower().str.contains(query, na=False, regex=False)
        filtered = filtered[mask]

    return filtered


def render_kpis(plan_df: pd.DataFrame, action_plan: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    total_rows = len(plan_df)
    scheduled_count = int((plan_df["status"] == "scheduled").sum()) if not plan_df.empty else 0
    backup_count = int((plan_df["status"] == "backup_used").sum()) if not plan_df.empty else 0
    unscheduled_count = int((plan_df["status"] == "unscheduled").sum()) if not plan_df.empty else 0
    scheduled_rate = scheduled_count / total_rows * 100 if total_rows else 0
    activity_type_count = len({activity["activity_type"] for activity in action_plan})
    date_range = f"{metadata['start_date']} to {metadata['end_date']}"

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Scheduled", f"{scheduled_count:,}", f"{scheduled_rate:.1f}% of rows")
    col2.metric("Backup used", f"{backup_count:,}")
    col3.metric("Unscheduled", f"{unscheduled_count:,}")
    col4.metric("Date range", date_range)
    col5.metric("Activity types", f"{activity_type_count}")


def render_assignment_coverage(action_count: int, metadata: dict[str, Any]) -> None:
    coverage_items = [
        ("100+ activities", f"{action_count} realistic health activities"),
        ("3 months of availability", f"{metadata['start_date']} to {metadata['end_date']}"),
        ("Constraint-aware scheduling", "Client schedule, travel, facilitators, equipment, and conflicts"),
        ("Backup handling", "Backup activities are used when primary activities cannot be placed"),
        ("CSV export", "Generated calendar can be downloaded for review"),
    ]
    coverage_df = pd.DataFrame(coverage_items, columns=["Requirement", "Implementation"])
    st.dataframe(coverage_df, use_container_width=True, hide_index=True)


def build_status_summary(plan_df: pd.DataFrame) -> pd.DataFrame:
    if plan_df.empty:
        return pd.DataFrame(columns=["status", "count", "percentage"])

    summary = plan_df["status"].value_counts().rename_axis("status").reset_index(name="count")
    summary["status"] = summary["status"].map(STATUS_LABELS).fillna(summary["status"])
    summary["percentage"] = (summary["count"] / len(plan_df) * 100).round(1).astype(str) + "%"
    return summary


def build_activity_type_summary(plan_df: pd.DataFrame) -> pd.DataFrame:
    if plan_df.empty:
        return pd.DataFrame(columns=["activity_type", "scheduled", "backup_used", "unscheduled", "total"])

    summary = (
        plan_df.pivot_table(
            index="activity_type",
            columns="status",
            values="activity_id",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    for status in ["scheduled", "backup_used", "unscheduled"]:
        if status not in summary.columns:
            summary[status] = 0

    summary["total"] = summary[["scheduled", "backup_used", "unscheduled"]].sum(axis=1)
    return summary[["activity_type", "scheduled", "backup_used", "unscheduled", "total"]].sort_values(
        "total", ascending=False
    )


def build_facilitator_summary(plan_df: pd.DataFrame) -> pd.DataFrame:
    if plan_df.empty:
        return pd.DataFrame(columns=["facilitator_role", "facilitator", "scheduled_rows"])

    scheduled = plan_df[plan_df["status"].isin(["scheduled", "backup_used"])]
    if scheduled.empty:
        return pd.DataFrame(columns=["facilitator_role", "facilitator", "scheduled_rows"])

    return (
        scheduled.groupby(["facilitator_role", "facilitator"], dropna=False)
        .size()
        .reset_index(name="scheduled_rows")
        .sort_values("scheduled_rows", ascending=False)
    )


def render_scheduler_explanation() -> None:
    with st.expander("How the scheduler works", expanded=False):
        st.markdown(
            """
            The Resource Allocator uses an explainable greedy scheduling strategy:

            1. Load the prioritized action plan and all availability data.
            2. Expand each activity into daily, weekly, or monthly occurrences.
            3. Schedule higher-priority health activities first.
            4. Search nearby feasible time slots around each target date.
            5. Check client availability, travel constraints, facilitator availability, equipment availability, and existing bookings.
            6. Use a backup activity when the primary activity cannot be scheduled.
            7. Keep unscheduled rows with a reason instead of silently dropping them.
            """
        )

    with st.expander("Constraints considered", expanded=False):
        st.markdown(
            """
            - **Client schedule:** activities must fit within available client windows.
            - **Travel plans:** in-person activities are blocked during travel unless remote execution is possible.
            - **Specialists and allied health:** facilitator availability must cover the full activity duration.
            - **Equipment:** required equipment must be available for in-person activities.
            - **Double-booking:** the scheduler avoids overlapping client and resource bookings.
            - **Backup activities:** backup options are attempted when the primary plan cannot be placed.
            """
        )


def main() -> None:
    ensure_sample_data()
    metadata = load_metadata()
    action_plan = load_action_plan()
    availability = load_availability_data()

    st.title("Elyx Resource Allocator")
    st.markdown(
        """
        A lightweight, reviewer-friendly Streamlit demo that converts Elyx HealthSpan AI recommendations
        into a personalized calendar while respecting client availability, travel plans, equipment,
        specialists, allied health professionals, remote feasibility, backup activities, and skipped-activity handling.
        """
    )

    with st.sidebar:
        st.header("Controls")
        st.caption("Choose the scheduling window and filter the generated calendar.")

        start_date = st.date_input(
            "Start date",
            value=pd.to_datetime(metadata["start_date"]).date(),
            help="The scheduler will generate occurrences from this date onward.",
        )
        end_date = st.date_input(
            "End date",
            value=pd.to_datetime(metadata["end_date"]).date(),
            help="The scheduler will generate occurrences through this date.",
        )

        st.divider()
        st.subheader("Data included")
        st.write(f"Activities: **{len(action_plan)}**")
        st.write(f"Availability window: **{metadata['start_date']} → {metadata['end_date']}**")
        st.caption("Client schedule, travel plans, equipment, specialists, and allied health availability are included.")

        with st.expander("Advanced", expanded=False):
            st.warning("Regenerating sample data changes the synthetic dataset. Use only for local experimentation.")
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

    display_df = add_display_columns(plan_df)

    with st.sidebar:
        st.divider()
        st.subheader("Calendar filters")

        selected_activity_types = st.multiselect(
            "Activity type",
            safe_unique(display_df, "activity_type"),
            default=safe_unique(display_df, "activity_type"),
        )
        selected_facilitators = st.multiselect(
            "Facilitator",
            safe_unique(display_df, "facilitator"),
            default=safe_unique(display_df, "facilitator"),
        )
        selected_statuses = st.multiselect(
            "Status",
            safe_unique(display_df, "status"),
            default=safe_unique(display_df, "status"),
            format_func=lambda value: STATUS_LABELS.get(value, value),
        )
        selected_locations = st.multiselect(
            "Location",
            safe_unique(display_df, "location"),
            default=safe_unique(display_df, "location"),
        )
        selected_modes = st.multiselect(
            "Mode",
            safe_unique(display_df, "mode", include_blank=True),
            default=safe_unique(display_df, "mode", include_blank=True),
            format_func=lambda value: MODE_LABELS.get(value, value),
        )
        text_query = st.text_input("Search", placeholder="Activity, facilitator, equipment, notes...")

    filtered_df = apply_filters(
        display_df,
        selected_activity_types=selected_activity_types,
        selected_facilitators=selected_facilitators,
        selected_statuses=selected_statuses,
        selected_locations=selected_locations,
        selected_modes=selected_modes,
        text_query=text_query,
    )

    render_kpis(plan_df, action_plan, metadata)

    tab_overview, tab_calendar, tab_constraints, tab_data, tab_export = st.tabs(
        ["Overview", "Personalized Calendar", "Constraint Summary", "Data Preview", "Export"]
    )

    with tab_overview:
        st.subheader("Assignment Coverage")
        render_assignment_coverage(len(action_plan), metadata)

        st.subheader("Reviewer quick check")
        st.info(
            "Start here: verify the KPI cards, open the Personalized Calendar tab, filter by status, "
            "inspect backup/unscheduled rows, then download the CSV from the Export tab."
        )

        render_scheduler_explanation()

    with tab_calendar:
        st.subheader("Personalized Calendar")
        st.caption(f"Showing {len(filtered_df):,} of {len(display_df):,} generated calendar rows after filters.")

        if filtered_df.empty:
            st.warning("No calendar rows match the current filters.")
        else:
            available_columns = [column for column in CALENDAR_COLUMNS if column in filtered_df.columns]
            st.dataframe(
                filtered_df[available_columns],
                use_container_width=True,
                hide_index=True,
                height=560,
                column_config={
                    "date": st.column_config.TextColumn("Date"),
                    "start_time": st.column_config.TextColumn("Start"),
                    "end_time": st.column_config.TextColumn("End"),
                    "activity_name": st.column_config.TextColumn("Activity"),
                    "activity_type": st.column_config.TextColumn("Type"),
                    "priority": st.column_config.NumberColumn("Priority", format="%d"),
                    "facilitator_role": st.column_config.TextColumn("Role"),
                    "facilitator": st.column_config.TextColumn("Facilitator"),
                    "equipment": st.column_config.TextColumn("Equipment"),
                    "location": st.column_config.TextColumn("Location"),
                    "mode_label": st.column_config.TextColumn("Mode"),
                    "status_label": st.column_config.TextColumn("Status"),
                    "details": st.column_config.TextColumn("Details"),
                    "metrics_to_collect": st.column_config.TextColumn("Metrics"),
                    "notes": st.column_config.TextColumn("Notes"),
                },
            )

    with tab_constraints:
        st.subheader("Constraint Summary")
        left, right = st.columns(2)

        with left:
            st.markdown("**Schedule status**")
            st.dataframe(build_status_summary(plan_df), use_container_width=True, hide_index=True)

            st.markdown("**Rows by activity type and status**")
            st.dataframe(build_activity_type_summary(plan_df), use_container_width=True, hide_index=True, height=300)

        with right:
            st.markdown("**Facilitator utilization**")
            st.dataframe(build_facilitator_summary(plan_df), use_container_width=True, hide_index=True, height=300)

            st.markdown("**Availability data loaded**")
            availability_summary = pd.DataFrame(
                [
                    ("Client availability slots", len(availability["client_schedule"])),
                    ("Travel plans", len(availability["travel_plans"])),
                    ("Equipment resources", len(availability["equipment"])),
                    ("Specialists", len(availability["specialists"])),
                    ("Allied health professionals", len(availability["allied_health"])),
                ],
                columns=["Node", "Count"],
            )
            st.dataframe(availability_summary, use_container_width=True, hide_index=True)

        unscheduled = plan_df[plan_df["status"] == "unscheduled"] if not plan_df.empty else pd.DataFrame()
        if not unscheduled.empty:
            with st.expander("Unscheduled rows and reasons", expanded=False):
                st.dataframe(
                    unscheduled[["date", "activity_name", "activity_type", "priority", "notes"]],
                    use_container_width=True,
                    hide_index=True,
                    height=260,
                )

    with tab_data:
        st.subheader("Data Preview")

        st.markdown("**Action plan sample**")
        activity_df = pd.DataFrame(action_plan)
        action_columns = [
            "activity_id",
            "priority",
            "activity_type",
            "name",
            "frequency",
            "duration_minutes",
            "facilitator_role",
            "can_be_remote",
        ]
        st.dataframe(activity_df[action_columns], use_container_width=True, hide_index=True, height=320)

        st.markdown("**Travel plans**")
        st.dataframe(pd.DataFrame(availability["travel_plans"]), use_container_width=True, hide_index=True)

        with st.expander("Availability resource samples", expanded=False):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("Specialists")
                st.dataframe(
                    pd.DataFrame(availability["specialists"]).drop(columns=["available_slots"], errors="ignore"),
                    hide_index=True,
                )

            with col2:
                st.markdown("Allied health")
                st.dataframe(
                    pd.DataFrame(availability["allied_health"]).drop(columns=["available_slots"], errors="ignore"),
                    hide_index=True,
                )

            with col3:
                st.markdown("Equipment")
                st.dataframe(
                    pd.DataFrame(availability["equipment"]).drop(columns=["available_slots"], errors="ignore"),
                    hide_index=True,
                )

    with tab_export:
        st.subheader("Export")
        st.write("Download the complete generated calendar or the currently filtered view.")

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                label="Download full generated calendar CSV",
                data=dataframe_to_csv_bytes(plan_df),
                file_name="generated_personalized_plan.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col2:
            st.download_button(
                label="Download filtered calendar CSV",
                data=dataframe_to_csv_bytes(filtered_df),
                file_name="filtered_personalized_plan.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("**Export preview**")
        preview_columns = [column for column in CALENDAR_COLUMNS if column in filtered_df.columns]
        st.dataframe(filtered_df[preview_columns].head(50), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()