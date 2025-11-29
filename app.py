from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Optional, Tuple

import pywhatkit

from flask import Flask, redirect, render_template, request, url_for

from data_store import (
    add_schedule,
    find_patient,
    get_patients,
    mark_reminder_sent,
    upsert_patient,
)

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
    "Humira",
    "Enbrel",
    "Remsima",
    "Simponi",
    "Cimzia",
    "Stelara",
    "Taltz",
    "Cosentyx",
    "Ilaris",
    "Kineret",
    "Mabthera",
    "Skyrizi",
    "Cellcept",
    "Otezla",
    "Orencia",
    "Kevzara",
    "Actemra",
    "Benlysta",
    "Rinvoq",
    "Xeljanz",
    "Olumiant",
    "Arava",
    "Saphnelo",
    "Bimzelx"
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
    reminder_status = request.args.get("reminder_status")
    reminder_level = request.args.get("reminder_level") or "info"
    return render_template(
        "physician.html",
        patients=patients,
        patient=patient,
        medication_options=MEDICATION_OPTIONS,
        reminder_status=reminder_status,
        reminder_level=reminder_level,
    )


@app.route("/physician/select", methods=["POST"])
def select_patient():
    patient_id = request.form.get("patient_id") or request.form.get("new_patient_id")
    patient_name = request.form.get("patient_name") or request.form.get("new_patient_name")
    patient_phone = request.form.get("patient_phone") or ""

    if not patient_id:
        return redirect(url_for("physician"))

    upsert_patient(
        patient_id=patient_id.strip(),
        name=(patient_name or "").strip(),
        phone_number=patient_phone.strip(),
    )
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


def _last_reminder_sent_at(schedule: Dict) -> Optional[datetime]:
    raw = schedule.get("last_reminder_sent_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _send_whatsapp_message(phone_number: str, message: str) -> Tuple[bool, Optional[str]]:
    try:
        pywhatkit.sendwhatmsg_instantly(
            phone_no=phone_number,
            message=message,
            wait_time=10,
            tab_close=True,
        )
    except Exception as exc:  # noqa: BLE001 - show failure to user
        return False, str(exc)

    return True, None


@app.route("/physician/send_reminders", methods=["POST"])
def send_reminders():
    patient_id = request.form.get("patient_id")
    if not patient_id:
        return redirect(url_for("physician"))

    window_minutes = int(request.form.get("window_minutes") or 15)
    patient = find_patient(patient_id)
    if not patient:
        return redirect(url_for("physician"))

    phone_number = (patient.get("phone_number") or "").strip()
    if not phone_number:
        return redirect(
            url_for(
                "physician",
                patient_id=patient_id,
                reminder_status="No WhatsApp number on file for this patient.",
                reminder_level="warning",
            )
        )

    now = datetime.now()
    end_time = now + timedelta(minutes=max(1, window_minutes))
    occurrences: List[Dict] = []
    for schedule in patient.get("schedules", []):
        occurrences.extend(
            expand_schedule(schedule, now=now, end_time=end_time, limit=200)
        )

    reminders_to_send: List[Dict] = []
    for occ in occurrences:
        schedule = occ.get("schedule", {})
        occurrence_time = occ.get("time")
        if not occurrence_time:
            continue

        last_sent = _last_reminder_sent_at(schedule)
        if last_sent and last_sent >= occurrence_time:
            continue
        reminders_to_send.append(occ)

    sent_count = 0
    errors: List[str] = []
    for occ in reminders_to_send:
        schedule = occ.get("schedule", {})
        occurrence_time = occ.get("time")
        if not occurrence_time:
            continue

        reminder_message = (
            f"Hi {patient.get('name') or 'there'}, this is your reminder to take "
            f"{schedule.get('medication', 'your medication')} ({schedule.get('dose', '')}) "
            f"at {occurrence_time.strftime('%I:%M %p on %B %d, %Y')}."
        )

        success, error_message = _send_whatsapp_message(phone_number, reminder_message)
        if success:
            sent_count += 1
            mark_reminder_sent(
                patient_id=patient_id,
                schedule_id=schedule.get("id", ""),
                occurrence_time=occurrence_time.isoformat(),
            )
        elif error_message:
            errors.append(error_message)

    if errors:
        status = "Some reminders failed: " + "; ".join(errors)
        level = "danger"
    elif sent_count == 0:
        status = "No reminders to send in the selected window."
        level = "info"
    else:
        status = f"Sent {sent_count} WhatsApp reminder(s)."
        level = "success"

    return redirect(
        url_for(
            "physician",
            patient_id=patient_id,
            reminder_status=status,
            reminder_level=level,
        )
    )


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
            "patient.html",
            patient=None,
            todays_meds=[],
            next_week_meds=[],
            calendar_weeks=[],
            schedules=[]
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

    # Group occurrences by day
    occurrences_by_day: Dict[datetime.date, List[Dict]] = {}
    for occurrence in occurrences:
        occ_date = occurrence["time"].date()
        if occ_date > end_date:
            continue
        occurrences_by_day.setdefault(occ_date, []).append(occurrence)

    # Today's medications
    todays_meds = sorted(
        occurrences_by_day.get(today, []),
        key=lambda item: item["time"]
    )

    # Next 7 days medications
    next_week_meds = []
    for day_offset in range(1, 8):
        day_date = today + timedelta(days=day_offset)
        day_meds = sorted(
            occurrences_by_day.get(day_date, []),
            key=lambda item: item["time"]
        )
        if day_meds:
            next_week_meds.append({
                "date": day_date,
                "meds": day_meds
            })

    # Build calendar weeks (4 weeks, aligned to start of week)
    # Find the Monday of the current week
    days_since_monday = today.weekday()  # 0=Monday, 6=Sunday
    week_start = today - timedelta(days=days_since_monday)

    calendar_weeks = []
    for week_num in range(4):
        week = []
        for day_num in range(7):  # Monday to Sunday
            day_date = week_start + timedelta(days=week_num * 7 + day_num)
            day_meds = sorted(
                occurrences_by_day.get(day_date, []),
                key=lambda item: item["time"]
            )
            week.append({
                "date": day_date,
                "meds": day_meds,
                "is_today": day_date == today,
                "is_past": day_date < today,
                "is_future": day_date > end_date
            })
        calendar_weeks.append(week)

    return render_template(
        "patient.html",
        patient=patient,
        todays_meds=todays_meds,
        next_week_meds=next_week_meds,
        calendar_weeks=calendar_weeks,
        schedules=patient.get("schedules", [])
    )


@app.context_processor
def inject_now():
    return {"now": datetime.now()}


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8011)
