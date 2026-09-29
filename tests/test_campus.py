import pytest

from campusride import campus


@pytest.mark.parametrize(
    "mention,expected",
    [
        ("RB", "rajendra"),
        ("rajendra bhavan", "rajendra"),
        ("Rajendra hostel", "rajendra"),
        ("the library", "mgcl"),
        ("MGCL", "mgcl"),
        ("lecture hall", "lhc"),
        ("convo hall", "convocation_hall"),
        ("rajendr bhawan", "rajendra"),  # typo
        ("sarojni bhawan", "sarojini"),  # typo
        ("Student Activity Centre", "sac"),  # British spelling
        ("front gate", "main_gate"),
        ("railway station", "railway_station"),
    ],
)
def test_resolves(mention, expected):
    r = campus.resolve_place(mention)
    assert r.status == "ok" and r.place_id == expected


@pytest.mark.parametrize("mention", ["my hostel", "the hostel", "bhawan", "the department", "Raj bhawan"])
def test_ambiguous(mention):
    r = campus.resolve_place(mention)
    assert r.status == "ambiguous" and len(r.candidates) >= 2


@pytest.mark.parametrize("mention", ["Delhi airport", "Dehradun", "haridwar", "jolly grant airport"])
def test_out_of_area(mention):
    assert campus.resolve_place(mention).status == "out_of_area"


@pytest.mark.parametrize("mention", ["quarter", "xyz", "narnia", ""])
def test_unknown_is_not_guessed(mention):
    assert campus.resolve_place(mention).status == "unknown"


def test_aliases_unique_and_zones_valid():
    assert all(p.zone in campus.ZONES for p in campus.PLACES.values())
    assert len(campus.ALIASES) > len(campus.PLACES)


def test_geometry_sane():
    d = campus.place_distance_m("rajendra", "main_gate")
    assert 300 < d < 3000
    assert campus.fare_inr(1000, "cab") > campus.fare_inr(1000, "e_rickshaw")
