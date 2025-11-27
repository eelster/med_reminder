from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Optional

from flask import Flask, redirect, render_template, request, url_for

from data_store import add_schedule, find_patient, get_patients, load_data, upsert_patient

app = Flask(__name__)

MEDICATION_OPTIONS = [
    "Methotrexate",
    "Hydroxychloroquine",
    "Sulfasalazine",
    "Leflunomide",
    "Prednisone",
    "Naproxen",
    "Ibuprofen",
    "Etanercept",
    "Adalimumab",
    "Tofacitinib",
]


@app.route("/")
def home():
    return redirect(url_for("physician"))


@app.route("/physician", methods=["GET"])
def physician():
    patient_id = request.args.get("patient_id")
    patient = find_patient(patient_id) if patient_id else None
    if patient is not None and "schedules" not in patient:
        patient["schedules"] = []
    patients = get_patients()
    return render_template(
        "physician.html",
        patients=patients,
        patient=patient,
        medication_options=MEDICATION_OPTIONS,
    )


@app.route("/physician/select", methods=["POST"])
def select_patient():
    patient_id = request.form.get("patient_id") or request.form.get("new_patient_id")
    patient_name = request.form.get("patient_name") or request.form.get("new_patient_name")

    if not patient_id:
        return redirect(url_for("physician"))

    upsert_patient(patient_id=patient_id.strip(), name=(patient_name or "").strip())
    return redirect(url_for("physician", patient_id=patient_id))


@app.route("/physician/add_schedule", methods=["POST"])
def create_schedule():
    patient_id = request.form.get("patient_id")
    if not patient_id:
        return redirect(url_for("physician"))

    medication = request.form.get("medication")
    dose = request.form.get("dose")
    frequency_value = int(request.form.get("frequency_value") or 1)
    frequency_unit = request.form.get("frequency_unit") or "days"
    repeat_mode = request.form.get("repeat_mode") or "single"
    repeat_count_value = request.form.get("repeat_count")
    repeat_count = int(repeat_count_value) if repeat_count_value else None
    start_time_raw = request.form.get("start_time")

    start_time = (
        datetime.fromisoformat(start_time_raw)
        if start_time_raw
        else datetime.now()
    )

    schedule = {
        "id": str(uuid.uuid4()),
        "medication": medication,
        "dose": dose,
        "frequency_value": frequency_value,
        "frequency_unit": frequency_unit,
        "repeat_mode": repeat_mode,
        "repeat_count": repeat_count,
        "start_time": start_time.isoformat(),
    }

    add_schedule(patient_id, schedule)
    return redirect(url_for("physician", patient_id=patient_id))


def _schedule_delta(frequency_value: int, frequency_unit: str) -> timedelta:
    if frequency_unit == "hours":
        return timedelta(hours=frequency_value)
    return timedelta(days=frequency_value)


def expand_schedule(
    schedule: Dict,
    limit: int = 10,
    now: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[Dict]:
    now = now or datetime.now()
    try:
        start_raw = schedule.get("start_time")
        start = datetime.fromisoformat(start_raw) if start_raw else None
    except (TypeError, ValueError):
        return []

    if start is None:
        return []
    frequency_value = max(1, int(schedule.get("frequency_value", 1)))
    frequency_unit = schedule.get("frequency_unit", "days")
    repeat_mode = schedule.get("repeat_mode", "single")
    repeat_count = schedule.get("repeat_count")

    delta = _schedule_delta(frequency_value, frequency_unit)

    occurrences: List[Dict] = []

    if repeat_mode == "single":
        if start >= now and (end_time is None or start <= end_time):
            occurrences.append({"time": start, "schedule": schedule})
        return occurrences

    current_time = start
    count = 0
    max_occurrences = repeat_count if repeat_mode == "count" and repeat_count else limit

    while True:
        if repeat_mode == "count" and repeat_count is not None and count >= repeat_count:
            break

        if end_time and current_time > end_time:
            break

        if repeat_mode == "count" and not end_time and len(occurrences) >= max_occurrences:
            break

        if repeat_mode == "indefinite" and not end_time and len(occurrences) >= limit:
            break

        if current_time >= now and (end_time is None or current_time <= end_time):
            occurrences.append({"time": current_time, "schedule": schedule})

        count += 1
        current_time += delta

    return occurrences


@app.route("/patient/<patient_id>")
def patient_view(patient_id: str):
    patient = find_patient(patient_id)
    if not patient:
        return render_template(
            "patient.html", patient=None, occurrences=[], calendar_days=[]
        )

    if "schedules" not in patient:
        patient["schedules"] = []

    occurrences: List[Dict] = []
    now = datetime.now()
    calendar_end = now + timedelta(days=28)
    today = now.date()
    end_date = today + timedelta(days=27)
    for schedule in patient.get("schedules", []):
        occurrences.extend(
            expand_schedule(schedule, now=now, end_time=calendar_end, limit=200)
        )

    occurrences.sort(key=lambda item: item["time"])

    occurrences_by_day: Dict[datetime.date, List[Dict]] = {}
    for occurrence in occurrences:
        occ_date = occurrence["time"].date()
        if occ_date > end_date:
            continue
        occurrences_by_day.setdefault(occ_date, []).append(occurrence)

    calendar_days = []
    for day_offset in range(28):
        day_date = today + timedelta(days=day_offset)
        day_occurrences = sorted(
            occurrences_by_day.get(day_date, []), key=lambda item: item["time"]
        )
        calendar_days.append(
            {
                "date": day_date,
                "items": day_occurrences,
                "is_today": day_date == today,
                "is_highlight": day_date <= today + timedelta(days=1),
            }
        )

    return render_template(
        "patient.html",
        patient=patient,
        occurrences=occurrences,
        calendar_days=calendar_days,
    )


@app.context_processor
def inject_now():
    return {"now": datetime.now()}


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
