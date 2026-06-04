# Elyx Resource Allocator

A simple but realistic implementation of a **Resource Allocator** for Elyx's HealthSpan AI workflow. The app converts a prioritized health action plan into a personalized calendar while considering client schedule, travel plans, equipment availability, specialists, allied health professionals, remote feasibility, backup activities, and skipped-activity adjustments.

## Hosted Demo

The app is hosted here: https://elyx-health-resource-allocator.streamlit.app/

## GitHub Repository

Source code: https://github.com/thanhdat3103/elyx-resource-allocator

## 1. Overview

The assignment asks for a simple scheduler that takes an action plan and resource schedules, then outputs a personalized plan. This implementation is intentionally designed to be explainable and reviewable rather than overly complex.

The project includes:

- Synthetic but realistic action-plan data for **100 activities**.
- Three months of availability data for:
  - Client schedule
  - Travel plans
  - Equipment
  - Specialists
  - Allied health professionals
- A constraint-aware scheduler.
- A Streamlit web app for viewing and filtering the personalized calendar.
- Downloadable CSV output.
- Prompt documentation in `PROMPTS.md`.

## 2. Features

- Priority-based scheduling: high-priority health activities are placed first.
- Frequency expansion: daily, weekly, and monthly recommendations are expanded into calendar occurrences.
- Travel-aware scheduling: in-person activities are blocked during travel unless a remote alternative is allowed.
- Resource-aware scheduling: specialists, allied health professionals, and equipment must be available for the full time slot.
- Backup handling: if the primary activity cannot be scheduled, a backup activity is attempted.
- Explainability: unscheduled activities are retained with a reason instead of being silently dropped.
- Calendar-style output: readable date/time table with activity, facilitator, equipment, mode, status, notes, and metrics.
- Streamlit dashboard with filtering and CSV download.

## 3. Project Structure

```text
elyx-resource-allocator/
├── app.py
├── README.md
├── PROMPTS.md
├── requirements.txt
├── data/
│   ├── action_plan_100_activities.json
│   ├── client_schedule.json
│   ├── travel_plans.json
│   ├── equipment_availability.json
│   ├── specialists_availability.json
│   ├── allied_health_availability.json
│   ├── metadata.json
│   └── generated_personalized_plan.csv
├── src/
│   ├── data_generator.py
│   ├── scheduler.py
│   └── utils.py
└── tests/
    └── test_scheduler.py
```

## 4. Data Model

Each activity contains the fields requested in the assignment:

- Activity type
- Frequency
- Activity details
- Facilitator type and role
- Possible locations
- Remote feasibility
- Prep requirements
- Backup activities
- Adjustment if skipped
- Metrics to collect

Example activity:

```json
{
  "activity_id": "ACT001",
  "priority": 1,
  "activity_type": "Fitness routine / exercise",
  "name": "Zone 2 Run #001",
  "frequency": {"times": 3, "period": "week"},
  "duration_minutes": 45,
  "details": "Maintain heart rate between 120-140 bpm",
  "facilitator_type": "specialist",
  "facilitator_role": "Fitness Trainer",
  "location_options": ["Park", "Gym", "Hotel Gym"],
  "can_be_remote": false,
  "required_equipment": ["Treadmill"],
  "prep_required": "Wear appropriate training clothes, prepare water, and confirm recovery status.",
  "backup_activities": ["Brisk Walk", "Mobility Flow", "Indoor Cycling"],
  "if_skipped_adjustment": "Reschedule within the same week if possible; otherwise reduce next session intensity by 10%.",
  "metrics_to_collect": ["heart_rate", "duration", "perceived_exertion"],
  "preferred_time_windows": ["morning"]
}
```

## 5. Scheduling Logic

The scheduler follows an explainable greedy algorithm:

1. Load the action plan and all availability data.
2. Expand each activity into required occurrences based on frequency.
3. Sort occurrences by activity priority.
4. Search for feasible slots near the target date.
5. Check client availability.
6. Apply travel constraints.
7. Check facilitator availability.
8. Check required equipment availability.
9. Prevent double-booking of the client and resources.
10. Select the best slot using a simple score based on:
    - Backup penalty
    - Distance from target date
    - Preferred time window
    - Daily load
    - Earliest feasible time
11. If no primary slot is available, try a backup activity.
12. If no feasible backup exists, mark the occurrence as `unscheduled` with a reason.

## 6. How to Run Locally

### Step 1: Clone the repository

```bash
git clone <YOUR_GITHUB_REPO_URL>
cd elyx-resource-allocator
```

### Step 2: Create and activate a virtual environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Generate sample data

```bash
python -m src.data_generator --output-dir data --start-date 2026-06-09 --months 3 --num-activities 100
```

### Step 5: Run the scheduler from the command line

```bash
python -m src.scheduler --data-dir data --output data/generated_personalized_plan.csv
```

### Step 6: Run the Streamlit app

```bash
streamlit run app.py
```

Then open the local URL shown in your terminal, usually:

```text
http://localhost:8501
```

## 7. How to Use the App

1. Open the Streamlit app.
2. Use the sidebar to choose the scheduling start date and end date.
3. Review the summary metrics:
   - Total calendar rows
   - Scheduled activities
   - Backup activities used
   - Unscheduled activities
4. Use filters to narrow the calendar by:
   - Activity type
   - Status
   - Activity/facilitator/location search text
5. Review the personalized calendar table.
6. Click **Download personalized plan as CSV** to export the generated plan.
7. Review the action-plan preview at the bottom to inspect the source activities.

## 8. Deploying to Streamlit Community Cloud

1. Push this project to a GitHub repository.
2. Go to Streamlit Community Cloud.
3. Connect your GitHub account if it is not already connected.
4. Create a new app from your GitHub repository.
5. Set the app entry point to:

```text
app.py
```

6. Deploy the app.
7. Copy the public app URL and include it in your submission email.

## 9. Tests

Run unit tests with:

```bash
python -m unittest discover -s tests
```

## 10. Assumptions and Limitations

- The scheduler uses 15-minute slot granularity.
- The data is synthetic but designed to be realistic.
- The algorithm is greedy and explainable, not a global optimization solver.
- Remote activities may be scheduled during travel if the activity and facilitator support remote mode.
- Some activities may remain unscheduled if no feasible slot satisfies all constraints.
- Backup activities are simplified and inherit some metadata from the original activity.

## 11. Future Improvements

- Add optimization using integer programming or constraint programming.
- Add calendar export in iCalendar `.ics` format.
- Add user authentication and multiple clients.
- Add richer resource utilization analytics.
- Add conflict resolution recommendations.
- Add drag-and-drop calendar UI.

## 12. Submission Checklist

- [ ] GitHub repository link is public or accessible.
- [ ] Streamlit app is hosted and accessible.
- [ ] `README.md` explains the project and how to run it.
- [ ] `PROMPTS.md` documents GenAI prompts used.
- [ ] Data files include at least 100 activities.
- [ ] Availability data covers 3 months.
- [ ] Scheduler output is readable as a calendar.
- [ ] Final email includes both the GitHub link and hosted app link.
