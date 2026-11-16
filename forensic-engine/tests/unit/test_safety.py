import pytest

from wfs_engine.safety import spreadsheet_safe, unique_path


def test_unique_path_never_overwrites_an_existing_product(tmp_path):
    first = unique_path(tmp_path, "case-report", "pdf")
    first.write_bytes(b"first report")
    second = unique_path(tmp_path, "case-report", "pdf")
    assert second != first
    assert not second.exists()
    second.write_bytes(b"second report")
    third = unique_path(tmp_path, "case-report", "pdf")
    assert len({first, second, third}) == 3
    # The earlier evidence product is untouched.
    assert first.read_bytes() == b"first report"
    assert second.read_bytes() == b"second report"


def test_unique_path_sanitises_the_stem(tmp_path):
    path = unique_path(tmp_path, "case/../../evil name", "csv")
    assert path.parent == tmp_path
    assert ".." not in path.name and "/" not in path.name


@pytest.mark.parametrize("value", ["=cmd|' /C calc'!A0", "+1+1", "-2+3",
                                   "@SUM(A1:A9)", "\t=1", "\r=2"])
def test_formula_prefixes_are_neutralised(value):
    safe = spreadsheet_safe(value)
    assert safe == "'" + value
    assert not safe.startswith(("=", "+", "-", "@", "\t", "\r"))


def test_plain_values_are_untouched():
    assert spreadsheet_safe("ordinary chat text") == "ordinary chat text"
    assert spreadsheet_safe("مرحبا") == "مرحبا"
    assert spreadsheet_safe(5) == 5
    assert spreadsheet_safe(None) is None
