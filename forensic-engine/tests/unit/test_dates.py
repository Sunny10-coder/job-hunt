import pytest

from wfs_engine.parsers import dates


def test_detect_day_first_from_observed_values():
    det = dates.detect_date_order(["31/12/2023", "01/01/2024", "05/02/2024"])
    assert det.order == "dmy"
    assert det.decisive is True
    assert det.confidence == 1.0


def test_detect_month_first_from_observed_values():
    det = dates.detect_date_order(["12/31/23", "01/02/24", "03/04/24"])
    assert det.order == "mdy"
    assert det.decisive is True


def test_detect_iso_year_first():
    det = dates.detect_date_order(["2024-01-05", "2024-02-05"])
    assert det.order == "ymd"


def test_ambiguous_order_reports_low_confidence():
    det = dates.detect_date_order(["01/02/24", "03/04/24"], fallback="dmy")
    assert det.decisive is False
    assert det.order == "dmy"
    assert det.confidence < 0.7


def test_twelve_hour_meridiem():
    ts = dates.parse_timestamp("12/31/23", "11:59 PM", "mdy", "UTC")
    assert ts is not None
    assert ts.naive_local.hour == 23
    assert ts.naive_local.minute == 59


def test_midnight_12am_is_zero():
    ts = dates.parse_timestamp("01/01/24", "12:05 AM", "mdy", "UTC")
    assert ts.naive_local.hour == 0


def test_timezone_offset_applied_for_utc_conversion():
    ts = dates.parse_timestamp("01/05/24", "10:00", "mdy", "Asia/Kolkata")
    assert ts.offset_minutes == 330
    assert dates.to_utc_iso(ts.utc) == "2024-01-05T04:30:00Z"


def test_dst_ambiguous_local_time_is_flagged():
    ts = dates.parse_timestamp("11/03/24", "01:30", "mdy", "America/New_York")
    assert ts.ambiguous is True


def test_invalid_calendar_dates_are_rejected():
    assert dates.parse_timestamp("02/31/24", "10:00", "mdy", "UTC") is None
    assert dates.parse_timestamp("13/13/24", "10:00", "mdy", "UTC") is None


@pytest.mark.parametrize("stamp", ["25:00", "10:75", "abc"])
def test_invalid_times_are_rejected(stamp):
    assert dates.parse_timestamp("01/05/24", stamp, "mdy", "UTC") is None
