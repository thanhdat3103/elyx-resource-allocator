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

VALID_STATUSES = set(STATUS_LABELS.keys())

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
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }

    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e5e7eb;
        padding: 1rem;
        border-radius: 0.8rem;
    }

    div[data-testid="stMetricLabel"] {
        color: #475569;
        font-size: 0.88rem;
    }

    div[data-testid="stMetricValue"] {
        font-weight: 700;
    }

    .review-note {
        background-color: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 0.75rem;
        padding: 1rem;
        color: #1e3a8a;
    }

    .small-muted {
        color: #64748b;
        font-size: 0.92rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
        filtered = filtered[filtered["mode"].fillna("").astype(str).isin(selected_modes)]

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


def count_client_overlaps(plan_df: pd.DataFrame) -> int:
    required = {"date", "start_time", "end_time", "status"}
    if plan_df.empty or not required.issubset(plan_df.columns):
        return 0

    scheduled_df = plan_df[plan_df["status"].isin(["scheduled", "backup_used"])].copy()
    if scheduled_df.empty:
        return 0

    scheduled_df["start_dt"] = pd.to_datetime(
        scheduled_df["date"].astype(str) + " " + scheduled_df["start_time"].astype(str),
        errors="coerce",
    )
    scheduled_df["end_dt"] = pd.to_datetime(
        scheduled_df["date"].astype(str) + " " + scheduled_df["end_time"].astype(str),
        errors="coerce",
    )
    scheduled_df = scheduled_df.dropna(subset=["start_dt", "end_dt"])

    overlap_count = 0
    for _, group in scheduled_df.groupby("date"):
        group = group.sort_values("start_dt")
        previous_end = None

        for _, row in group.iterrows():
            if previous_end is not None and row["start_dt"] < previous_end:
                overlap_count += 1

            if previous_end is None:
                previous_end = row["end_dt"]
            else:
                previous_end = max(previous_end, row["end_dt"])

    return overlap_count


def build_validation_checks(
    plan_df: pd.DataFrame,
    action_plan: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> pd.DataFrame:
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

    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "Status": "PASS" if len(action_plan) >= 100 else "REVIEW",
            "Check": "At least 100 activities loaded",
            "Details": f"{len(action_plan)} activities loaded",
        }
    )

    start = pd.to_datetime(metadata.get("start_date"))
    end = pd.to_datetime(metadata.get("end_date"))
    window_days = int((end - start).days + 1) if pd.notna(start) and pd.notna(end) else 0
    has_three_month_window = metadata.get("months") == 3 or window_days >= 80

    checks.append(
        {
            "Status": "PASS" if has_three_month_window else "REVIEW",
            "Check": "Three-month availability window present",
            "Details": f"{metadata.get('start_date')} to {metadata.get('end_date')} ({window_days} days)",
        }
    )

    checks.append(
        {
            "Status": "PASS" if not plan_df.empty else "REVIEW",
            "Check": "Generated calendar is not empty",
            "Details": f"{len(plan_df):,} calendar rows generated",
        }
    )

    missing_columns = sorted(required_columns - set(plan_df.columns))
    checks.append(
        {
            "Status": "PASS" if not missing_columns else "REVIEW",
            "Check": "Required output columns present",
            "Details": "All required columns present" if not missing_columns else f"Missing: {', '.join(missing_columns)}",
        }
    )

    actual_statuses = set(plan_df["status"].dropna().unique()) if "status" in plan_df.columns else set()
    invalid_statuses = sorted(actual_statuses - VALID_STATUSES)
    checks.append(
        {
            "Status": "PASS" if not invalid_statuses else "REVIEW",
            "Check": "Statuses are valid",
            "Details": ", ".join(sorted(actual_statuses)) if actual_statuses else "No statuses found",
        }
    )

    overlap_count = count_client_overlaps(plan_df)
    checks.append(
        {
            "Status": "PASS" if overlap_count == 0 else "REVIEW",
            "Check": "No overlapping scheduled client activities",
            "Details": f"{overlap_count} overlaps detected",
        }
    )

    backup_rows = plan_df[plan_df["status"] == "backup_used"] if "status" in plan_df.columns else pd.DataFrame()
    backup_notes_ok = True
    if not backup_rows.empty and "notes" in backup_rows.columns:
        backup_notes_ok = backup_rows["notes"].fillna("").astype(str).str.len().gt(0).all()

    checks.append(
        {
            "Status": "PASS" if backup_notes_ok else "REVIEW",
            "Check": "Backup rows include explanatory notes",
            "Details": f"{len(backup_rows):,} backup rows inspected",
        }
    )

    unscheduled_rows = plan_df[plan_df["status"] == "unscheduled"] if "status" in plan_df.columns else pd.DataFrame()
    unscheduled_notes_ok = True
    if not unscheduled_rows.empty and "notes" in unscheduled_rows.columns:
        unscheduled_notes_ok = unscheduled_rows["notes"].fillna("").astype(str).str.len().gt(0).all()

    checks.append(
        {
            "Status": "PASS" if unscheduled_notes_ok else "REVIEW",
            "Check": "Unscheduled rows include reason notes",
            "Details": f"{len(unscheduled_rows):,} unscheduled rows inspected",
        }
    )

    return pd.DataFrame(checks)


def render_header() -> None:
    st.title("Elyx Resource Allocator")
    st.markdown(
        """
        A reviewer-friendly Streamlit demo that converts prioritized HealthSpan AI recommendations
        into a personalized calendar while considering client availability, travel, equipment,
        specialists, allied health professionals, remote feasibility, backup activities,
        and skipped-activity handling.
        """
    )


def render_kpis(plan_df: pd.DataFrame, action_plan: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    total_rows = len(plan_df)
    scheduled_count = int((plan_df["status"] == "scheduled").sum()) if not plan_df.empty else 0
    backup_count = int((plan_df["status"] == "backup_used").sum()) if not plan_df.empty else 0
    unscheduled_count = int((plan_df["status"] == "unscheduled").sum()) if not plan_df.empty else 0
    scheduled_rate = scheduled_count / total_rows * 100 if total_rows else 0
    activity_type_count = len({activity["activity_type"] for activity in action_plan})

    start = pd.to_datetime(metadata["start_date"])
    end = pd.to_datetime(metadata["end_date"])
    window_days = int((end - start).days + 1)

    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1.25, 0.85])

    col1.metric("Scheduled", f"{scheduled_count:,}", f"{scheduled_rate:.1f}% of rows")
    col2.metric("Backup used", f"{backup_count:,}")
    col3.metric("Unscheduled", f"{unscheduled_count:,}")
    col4.metric("Scheduling window", f"{window_days} days")
    col4.caption(f"{metadata['start_date']} to {metadata['end_date']}")
    col5.metric("Activity types", f"{activity_type_count}")


def render_assignment_coverage(action_count: int, metadata: dict[str, Any]) -> None:
    coverage_df = pd.DataFrame(
        [
            {
                "Requirement": "100+ activities",
                "Implementation": f"{action_count} synthetic but realistic health activities",
            },
            {
                "Requirement": "3 months of availability data",
                "Implementation": f"{metadata['start_date']} to {metadata['end_date']}",
            },
            {
                "Requirement": "Constraint-aware scheduling",
                "Implementation": "Client schedule, travel, facilitators, equipment, and booking conflicts",
            },
            {
                "Requirement": "Backup handling",
                "Implementation": "Backup activities are attempted when primary activities cannot be placed",
            },
            {
                "Requirement": "Readable calendar output",
                "Implementation": "Calendar table with filters, status labels, notes, metrics, and CSV export",
            },
        ]
    )

    st.dataframe(coverage_df, width="stretch", hide_index=True)


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

    return summary[
        ["activity_type", "scheduled", "backup_used", "unscheduled", "total"]
    ].sort_values("total", ascending=False)


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
            The scheduler is intentionally explainable rather than overly optimized:

            1. Load the prioritized action plan and all availability data.
            2. Expand daily, weekly, and monthly recommendations into calendar occurrences.
            3. Schedule higher-priority activities first.
            4. Search feasible time slots near each target date.
            5. Check client availability, travel, facilitators, equipment, and existing bookings.
            6. Try a backup activity if the primary activity cannot be scheduled.
            7. Keep unscheduled rows with a reason instead of silently dropping them.
            """
        )

    with st.expander("Constraints considered", expanded=False):
        st.markdown(
            """
            - **Client schedule:** activities must fit inside available client windows.
            - **Travel plans:** in-person activities are blocked during travel unless remote execution is possible.
            - **Specialists and allied health:** facilitator availability must cover the full duration.
            - **Equipment:** required equipment must be available for in-person activities.
            - **Double-booking:** the scheduler avoids overlapping client and resource bookings.
            - **Backup activities:** backup options are attempted when the original activity cannot be placed.
            """
        )


def render_sidebar(metadata: dict[str, Any], action_plan: list[dict[str, Any]]) -> tuple[Any, Any]:
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
        st.write(f"Availability window: **{metadata['start_date']} to {metadata['end_date']}**")
        st.caption("Includes client schedule, travel plans, equipment, specialists, and allied health availability.")

        with st.expander("Advanced", expanded=False):
            st.warning("Regenerating sample data changes the synthetic dataset. Use only for local experimentation.")
            regenerate = st.button("Regenerate sample data")
            if regenerate:
                generate_all_data(output_dir=DATA_DIR)
                st.cache_data.clear()
                st.rerun()

    return start_date, end_date


def render_filter_sidebar(display_df: pd.DataFrame) -> tuple[list[str], list[str], list[str], list[str], list[str], str]:
    with st.sidebar:
        st.divider()
        st.subheader("Calendar filters")

        activity_types = safe_unique(display_df, "activity_type")
        facilitators = safe_unique(display_df, "facilitator")
        statuses = safe_unique(display_df, "status")
        locations = safe_unique(display_df, "location")
        modes = safe_unique(display_df, "mode", include_blank=True)

        selected_activity_types = st.multiselect("Activity type", activity_types, default=activity_types)
        selected_facilitators = st.multiselect("Facilitator", facilitators, default=facilitators)
        selected_statuses = st.multiselect(
            "Status",
            statuses,
            default=statuses,
            format_func=lambda value: STATUS_LABELS.get(value, value),
        )
        selected_locations = st.multiselect("Location", locations, default=locations)
        selected_modes = st.multiselect(
            "Mode",
            modes,
            default=modes,
            format_func=lambda value: MODE_LABELS.get(value, value),
        )
        text_query = st.text_input("Search", placeholder="Activity, facilitator, equipment, notes...")

    return (
        selected_activity_types,
        selected_facilitators,
        selected_statuses,
        selected_locations,
        selected_modes,
        text_query,
    )


def render_calendar_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.warning("No calendar rows match the current filters.")
        return

    available_columns = [column for column in CALENDAR_COLUMNS if column in df.columns]

    st.dataframe(
        df[available_columns],
        width="stretch",
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


def render_overview_tab(action_plan: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    st.subheader("Assignment Coverage")
    render_assignment_coverage(len(action_plan), metadata)

    st.subheader("Reviewer quick check")
    st.markdown(
        """
        <div class="review-note">
        Suggested review path: verify the KPI cards, open the Personalized Calendar tab,
        filter by status, inspect backup and unscheduled rows, check Validation Checks,
        then download the CSV from the Export tab.
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_scheduler_explanation()


def render_calendar_tab(display_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    st.subheader("Personalized Calendar")
    st.caption(f"Showing {len(filtered_df):,} of {len(display_df):,} generated calendar rows after filters.")
    render_calendar_table(filtered_df)


def render_constraint_summary_tab(plan_df: pd.DataFrame, availability: dict[str, list[dict[str, Any]]]) -> None:
    st.subheader("Constraint Summary")

    left, right = st.columns(2)

    with left:
        st.markdown("**Schedule status**")
        st.dataframe(build_status_summary(plan_df), width="stretch", hide_index=True)

        st.markdown("**Rows by activity type and status**")
        st.dataframe(build_activity_type_summary(plan_df), width="stretch", hide_index=True, height=300)

    with right:
        st.markdown("**Facilitator utilization**")
        st.dataframe(build_facilitator_summary(plan_df), width="stretch", hide_index=True, height=300)

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
        st.dataframe(availability_summary, width="stretch", hide_index=True)

    unscheduled = plan_df[plan_df["status"] == "unscheduled"] if not plan_df.empty else pd.DataFrame()
    if not unscheduled.empty:
        with st.expander("Unscheduled rows and reasons", expanded=False):
            unscheduled_columns = ["date", "activity_name", "activity_type", "priority", "notes"]
            available_columns = [column for column in unscheduled_columns if column in unscheduled.columns]
            st.dataframe(unscheduled[available_columns], width="stretch", hide_index=True, height=260)


def render_validation_tab(
    plan_df: pd.DataFrame,
    action_plan: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    st.subheader("Validation Checks")
    st.caption("Lightweight quality checks that help reviewers trust the generated schedule.")

    validation_df = build_validation_checks(plan_df, action_plan, metadata)
    st.dataframe(
        validation_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn("Status"),
            "Check": st.column_config.TextColumn("Check"),
            "Details": st.column_config.TextColumn("Details"),
        },
    )

    review_count = int((validation_df["Status"] == "REVIEW").sum())
    if review_count == 0:
        st.success("All validation checks passed.")
    else:
        st.warning(f"{review_count} validation check(s) need review. Inspect the details before submitting.")


def render_data_preview_tab(action_plan: list[dict[str, Any]], availability: dict[str, list[dict[str, Any]]]) -> None:
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
    available_action_columns = [column for column in action_columns if column in activity_df.columns]
    st.dataframe(activity_df[available_action_columns], width="stretch", hide_index=True, height=320)

    st.markdown("**Travel plans**")
    st.dataframe(pd.DataFrame(availability["travel_plans"]), width="stretch", hide_index=True)

    with st.expander("Availability resource samples", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("Specialists")
            st.dataframe(
                pd.DataFrame(availability["specialists"]).drop(columns=["available_slots"], errors="ignore"),
                width="stretch",
                hide_index=True,
            )

        with col2:
            st.markdown("Allied health")
            st.dataframe(
                pd.DataFrame(availability["allied_health"]).drop(columns=["available_slots"], errors="ignore"),
                width="stretch",
                hide_index=True,
            )

        with col3:
            st.markdown("Equipment")
            st.dataframe(
                pd.DataFrame(availability["equipment"]).drop(columns=["available_slots"], errors="ignore"),
                width="stretch",
                hide_index=True,
            )


def render_export_tab(plan_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    st.subheader("Export")
    st.write("Download the complete generated calendar or the currently filtered view.")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="Download full generated calendar CSV",
            data=dataframe_to_csv_bytes(plan_df),
            file_name="generated_personalized_plan.csv",
            mime="text/csv",
            width="stretch",
        )

    with col2:
        st.download_button(
            label="Download filtered calendar CSV",
            data=dataframe_to_csv_bytes(filtered_df),
            file_name="filtered_personalized_plan.csv",
            mime="text/csv",
            width="stretch",
        )

    st.markdown("**Export preview**")
    preview_columns = [column for column in CALENDAR_COLUMNS if column in filtered_df.columns]
    st.dataframe(filtered_df[preview_columns].head(50), width="stretch", hide_index=True)


def main() -> None:
    ensure_sample_data()

    metadata = load_metadata()
    action_plan = load_action_plan()
    availability = load_availability_data()

    render_header()
    start_date, end_date = render_sidebar(metadata, action_plan)

    if start_date > end_date:
        st.error("Start date must be before end date.")
        return

    with st.spinner("Building personalized plan..."):
        plan_df = run_scheduler_cached(start_date.isoformat(), end_date.isoformat())

    display_df = add_display_columns(plan_df)

    (
        selected_activity_types,
        selected_facilitators,
        selected_statuses,
        selected_locations,
        selected_modes,
        text_query,
    ) = render_filter_sidebar(display_df)

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

    tab_overview, tab_calendar, tab_constraints, tab_validation, tab_data, tab_export = st.tabs(
        [
            "Overview",
            "Personalized Calendar",
            "Constraint Summary",
            "Validation Checks",
            "Data Preview",
            "Export",
        ]
    )

    with tab_overview:
        render_overview_tab(action_plan, metadata)

    with tab_calendar:
        render_calendar_tab(display_df, filtered_df)

    with tab_constraints:
        render_constraint_summary_tab(plan_df, availability)

    with tab_validation:
        render_validation_tab(plan_df, action_plan, metadata)

    with tab_data:
        render_data_preview_tab(action_plan, availability)

    with tab_export:
        render_export_tab(plan_df, filtered_df)


if __name__ == "__main__":
    main()