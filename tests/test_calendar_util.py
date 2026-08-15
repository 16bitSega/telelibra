"""
Unit tests for calendar_util.py.
"""

from calendar_util import CalendarManager


def test_calendar_simulation_event_structure():
    manager = CalendarManager()
    event = manager.create_job_event(
        title="Senior Python Backend Developer",
        url="https://linkedin.com/jobs/view/999",
        notes="Requires AsyncIO and PostgreSQL experience",
    )

    assert event is not None
    assert event.get("simulated") is True
    body = event["event"]

    assert "Senior Python Backend Developer" in body["summary"]
    assert "https://linkedin.com/jobs/view/999" in body["description"]
    assert "start" in body
    assert "09:00:00" in body["start"]["dateTime"]
