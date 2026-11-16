"""recommend_sites and check_point against the live BigQuery tables and model.

Run from the repo root: GOOGLE_CLOUD_PROJECT=<project> pytest -v tests/
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from siting.tools import check_point, recommend_sites  # noqa: E402


def ids(result):
    return [s["geo_id"] for s in result["sites"]]


@pytest.fixture(scope="module")
def three_at_102():
    return recommend_sites(3, 102)


def test_three_sites_follow_the_rules(three_at_102):
    r = three_at_102
    assert r["status"] == "ok"
    assert len(r["sites"]) == 3
    box = r["search_area"]
    for s in r["sites"]:
        assert box["south"] <= s["latitude"] <= box["north"]
        assert box["west"] <= s["longitude"] <= box["east"]
        assert s["predicted_offset_f"] > 0
        assert s["expected_high_f"] == round(102 + s["predicted_offset_f"], 1)
        assert len(s["reasons"]) == 4
    no_vehicle = [s["residents"]["households_no_vehicle"] for s in r["sites"]]
    assert no_vehicle == sorted(no_vehicle, reverse=True)


def test_same_question_same_answer(three_at_102):
    again = recommend_sites(3, 102)
    for a, b in zip(three_at_102["sites"], again["sites"], strict=True):
        assert (a["geo_id"], a["rank"], a["predicted_offset_f"], a["reasons"]) == \
               (b["geo_id"], b["rank"], b["predicted_offset_f"], b["reasons"])


def test_south_stays_south(three_at_102):
    south = recommend_sites(3, 102, "south")
    assert south["search_area"]["north"] < three_at_102["search_area"]["north"]
    for s in south["sites"]:
        assert s["latitude"] <= south["search_area"]["north"]
    assert ids(south) != ids(three_at_102)


def test_forecast_moves_only_the_expected_high(three_at_102):
    hotter = recommend_sites(3, 107)
    for a, b in zip(three_at_102["sites"], hotter["sites"], strict=True):
        assert (a["geo_id"], a["predicted_offset_f"]) == (b["geo_id"], b["predicted_offset_f"])
        assert b["expected_high_f"] - a["expected_high_f"] == pytest.approx(5.0)


def test_count_is_capped_and_area_is_checked():
    assert len(recommend_sites(50)["sites"]) == 10
    assert recommend_sites(3, 102, "downtown")["status"] == "error"


def test_point_with_no_reading_nearby():
    r = check_point(32.806, -96.753, 105)
    assert r["status"] == "ok"
    assert -5 < r["predicted_offset_f"] < 5
    assert r["readings_nearby"]["readings_within_500m"] == 0
    assert len(r["reasons"]) == 4
    assert r["expected_high_f"] == round(105 + r["predicted_offset_f"], 1)


def test_point_outside_driven_area_is_refused():
    r = check_point(32.95, -96.82)
    assert r["status"] == "outside_driven_area"
    assert "predicted_offset_f" not in r
