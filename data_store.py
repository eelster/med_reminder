import json
from pathlib import Path
from typing import Dict, List, Optional

DATA_PATH = Path("data.json")


def _default_data() -> Dict:
    return {"patients": []}


def load_data() -> Dict:
    if not DATA_PATH.exists():
        return _default_data()
    with DATA_PATH.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return _default_data()


def save_data(data: Dict) -> None:
    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_patients() -> List[Dict]:
    data = load_data()
    return data.get("patients", [])


def find_patient(patient_id: str) -> Optional[Dict]:
    patients = get_patients()
    for patient in patients:
        if patient.get("id") == patient_id:
            return patient
    return None


def upsert_patient(patient_id: str, name: str, phone_number: str = "") -> Dict:
    data = load_data()
    patients = data.setdefault("patients", [])
    for patient in patients:
        if patient.get("id") == patient_id:
            patient["name"] = name or patient.get("name", "")
            if phone_number:
                patient["phone_number"] = phone_number
            save_data(data)
            return patient

    new_patient = {
        "id": patient_id,
        "name": name,
        "phone_number": phone_number,
        "schedules": [],
    }
    patients.append(new_patient)
    save_data(data)
    return new_patient


def add_schedule(patient_id: str, schedule: Dict) -> None:
    data = load_data()
    patients = data.setdefault("patients", [])
    for patient in patients:
        if patient.get("id") == patient_id:
            patient.setdefault("schedules", []).append(schedule)
            save_data(data)
            return
    raise ValueError("Patient not found")


def mark_reminder_sent(patient_id: str, schedule_id: str, occurrence_time: str) -> bool:
    """Record the timestamp for the last reminder sent for a schedule occurrence."""

    data = load_data()
    patients = data.setdefault("patients", [])
    for patient in patients:
        if patient.get("id") != patient_id:
            continue

        for schedule in patient.get("schedules", []):
            if schedule.get("id") == schedule_id:
                schedule["last_reminder_sent_at"] = occurrence_time
                save_data(data)
                return True

    return False
