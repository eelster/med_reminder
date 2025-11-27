# med_reminder

App to connect physician instructions with patient reminders.

## Running locally

1. Create a virtual environment (optional but recommended) and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the Flask server:
   ```bash
   python app.py
   ```
3. Open the physician view at `http://localhost:5000/physician`. The patient-facing view can be opened from the physician page once a patient is selected.

## Features

- Physician console to select an existing patient or create a new one.
- Define medication schedules with medication name (pre-loaded rheumatology list plus custom entry), dose, start time, frequency (hours/days), and repeat strategy (single, fixed count, or indefinite).
- Patient view that lists upcoming reminders in chronological order.
- Data persisted locally to `data.json` so you can refresh without losing added patients.
