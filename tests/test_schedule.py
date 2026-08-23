from datetime import datetime, timezone

import pytest

from backend.trading_floor import parse_run_at, seconds_until


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 3, 10, hour, minute, second, tzinfo=timezone.utc)


def test_seconds_until_later_today():
    assert seconds_until("15:00", at(9)) == 6 * 3600


def test_seconds_until_rolls_over_to_tomorrow():
    assert seconds_until("15:00", at(16)) == 23 * 3600


def test_seconds_until_at_the_target_waits_a_full_day():
    """Equal counts as past, so a round never fires twice on one tick."""
    assert seconds_until("15:00", at(15)) == 24 * 3600


def test_seconds_until_keeps_the_minutes():
    assert seconds_until("15:30", at(15, 0, 30)) == 29 * 60 + 30


@pytest.mark.parametrize("run_at", ["15:00", "00:00", "23:59", "9:05"])
def test_parse_run_at_accepts_valid_times(run_at):
    hour, minute = parse_run_at(run_at)
    assert 0 <= hour <= 23 and 0 <= minute <= 59


@pytest.mark.parametrize("run_at", ["15.00", "15", "3pm", "25:00", "15:60", "-1:00", "", "15:00:00"])
def test_parse_run_at_rejects_the_rest(run_at):
    """A typo has to fail at import, not hours later inside the scheduler."""
    with pytest.raises(ValueError):
        parse_run_at(run_at)
