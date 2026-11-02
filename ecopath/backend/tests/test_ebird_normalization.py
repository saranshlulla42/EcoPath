"""
eBird observation normalisation.

These expectations moved here from the frontend when the eBird call moved
server-side; the raw-record contract now lives in `data.sources.ebird`.
"""

from data.sources.ebird import normalize_observation


def test_normalises_a_complete_record():
    raw = {
        "speciesCode": "bartgo",
        "comName": "Bar-tailed Godwit",
        "sciName": "Limosa lapponica",
        "locName": "Miranda Shorebird Centre",
        "lat": -37.203,
        "lng": 175.463,
        "obsDt": "2024-03-15 08:30",
        "howMany": 42,
    }
    assert normalize_observation(raw) == {
        "lat": -37.203,
        "lng": 175.463,
        "date": "2024-03-15 08:30",
        "count": 42,
        "species_code": "bartgo",
        "species_name": "Bar-tailed Godwit",
        "location_name": "Miranda Shorebird Centre",
    }


def test_defaults_missing_fields():
    assert normalize_observation({}) == {
        "lat": 0.0,
        "lng": 0.0,
        "date": "",
        "count": 1,
        "species_code": "",
        "species_name": "Unknown",
        "location_name": "Unknown",
    }


def test_defaults_count_when_how_many_is_not_numeric():
    assert normalize_observation({"howMany": "X"})["count"] == 1


def test_parses_count_from_how_many_str():
    assert normalize_observation({"howManyStr": "1,250"})["count"] == 1250


def test_falls_back_to_scientific_name():
    assert normalize_observation({"sciName": "Limosa lapponica"})["species_name"] == "Limosa lapponica"


def test_preserves_negative_coordinates():
    result = normalize_observation({"lat": -45.5, "lng": -122.3})
    assert result["lat"] == -45.5
    assert result["lng"] == -122.3


def test_preserves_a_zero_count():
    """A surveyed zero is data, not a missing value."""
    assert normalize_observation({"howMany": 0})["count"] == 0
