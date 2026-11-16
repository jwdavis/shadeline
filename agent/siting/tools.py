"""Shadeline's two tools. Both run the BigQuery ML heat model through ML.EXPLAIN_PREDICT.

- recommend_sites: score every tract center in the driven area, keep the ones predicted
  hotter than the city average, rank them by households with no vehicle.
- check_point: score one location, or refuse it if it lies outside the driven area.

Everything that must come out the same on every run (the gate, the ranking, the forecast
arithmetic, rounding) is done here in code, not left to the language model.
"""
import math
from typing import Optional

from google.cloud import bigquery

from . import config

DS = f"{config.PROJECT}.{config.DATASET}"
MODEL = f"{DS}.{config.BQML_MODEL}"

AREAS = ("all", "north", "south", "east", "west")

LABELS = {
    "latitude": "how far north it sits",
    "longitude": "how far east it sits",
    "year_built": "age of the housing",
    "housing_units": "amount of housing",
}

RANKING_RULE = ("Tract centers inside the driven area that the model predicts hotter than the city "
                "average, ordered by households with no vehicle, most first. A tie goes to the higher "
                "predicted offset.")

# Candidates: tract centers with residents inside the box the volunteers drove (in_driven_area,
# built by sql/01), cut down to the part of that box the planner asked about.
SCORE_SQL = f"""
SELECT geo_id, latitude, longitude, predicted_offset_f, top_feature_attributions,
       total_pop, households, no_cars, no_vehicle_rate, poverty_rate, median_age
FROM ML.EXPLAIN_PREDICT(
  MODEL `{MODEL}`,
  (SELECT geo_id, tract_lat AS latitude, tract_lon AS longitude, year_built, housing_units,
          total_pop, households, no_cars, no_vehicle_rate, poverty_rate, median_age
   FROM `{DS}.tract_features`
   WHERE in_driven_area AND total_pop > 0
     AND tract_lat BETWEEN @south AND @north AND tract_lon BETWEEN @west AND @east),
  STRUCT(4 AS top_k_features))
"""

# A point keeps its own coordinates; housing age and housing units come from the nearest
# tract center, because the tract table has no boundaries.
POINT_SQL = f"""
WITH nearest_tract AS (
  SELECT *, ST_DISTANCE(ST_GEOGPOINT(tract_lon, tract_lat), ST_GEOGPOINT(@lon, @lat)) AS meters_to_tract_center
  FROM `{DS}.tract_features` WHERE total_pop > 0
  ORDER BY meters_to_tract_center LIMIT 1),
nearest_reading AS (
  SELECT MIN(ST_DISTANCE(ST_GEOGPOINT(longitude, latitude), ST_GEOGPOINT(@lon, @lat))) AS meters_to_nearest_reading,
         COUNTIF(ST_DWITHIN(ST_GEOGPOINT(longitude, latitude), ST_GEOGPOINT(@lon, @lat), 500)) AS readings_within_500m
  FROM `{DS}.heat_observations`)
SELECT p.geo_id, p.latitude, p.longitude, p.predicted_offset_f, p.top_feature_attributions,
       p.total_pop, p.households, p.no_cars, p.no_vehicle_rate, p.poverty_rate, p.median_age,
       p.meters_to_tract_center, r.meters_to_nearest_reading, r.readings_within_500m
FROM ML.EXPLAIN_PREDICT(
  MODEL `{MODEL}`,
  (SELECT geo_id, @lat AS latitude, @lon AS longitude, year_built, housing_units, total_pop, households,
          no_cars, no_vehicle_rate, poverty_rate, median_age, meters_to_tract_center FROM nearest_tract),
  STRUCT(4 AS top_k_features)) AS p
CROSS JOIN nearest_reading AS r
"""

# The driven area is the bounding box of the street readings, the same box sql/01 used.
BOX_SQL = f"""
SELECT MIN(latitude) AS south, MAX(latitude) AS north, MIN(longitude) AS west, MAX(longitude) AS east
FROM `{DS}.heat_observations`
"""

# Dallas as a whole: every loaded tract with residents, poverty weighted by population and
# vehicles by households, the same way the picks are summed.
CITY_SQL = f"""
SELECT COUNT(*) AS tracts,
       SUM(poverty_rate * total_pop) / SUM(total_pop) AS poverty_rate,
       SUM(no_cars) / SUM(households) AS no_vehicle_rate
FROM `{DS}.tract_features` WHERE total_pop > 0
"""

_client = None
_box = None
_city = None


def _bq() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT)
    return _client


def _params(**values: float) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(name, "FLOAT64", float(v)) for name, v in values.items()])


def _driven_area() -> dict:
    """The readings' bounding box, queried once per process."""
    global _box
    if _box is None:
        r = list(_bq().query(BOX_SQL).result())[0]
        _box = {"south": r.south, "north": r.north, "west": r.west, "east": r.east}
    return dict(_box)


def _city_rates() -> dict:
    """Dallas's weighted rates, queried once per process."""
    global _city
    if _city is None:
        r = list(_bq().query(CITY_SQL).result())[0]
        _city = {"name": "Dallas", "tracts": r.tracts, "poverty_rate": round(r.poverty_rate, 3),
                 "no_vehicle_rate": round(r.no_vehicle_rate, 3)}
    return dict(_city)


def _describe(area: str, mid_lat: float, mid_lon: float) -> str:
    if area == "all":
        return "the whole area the volunteers drove"
    if area in ("north", "south"):
        return f"the {area}ern half of the area the volunteers drove, {area} of latitude {mid_lat:.4f}"
    return f"the {area}ern half of the area the volunteers drove, {area} of longitude {mid_lon:.4f}"


def _r2(x: float) -> float:
    return round(x, 2) + 0.0   # + 0.0 turns -0.0 into 0.0


def _reasons(attributions) -> list[dict]:
    """All four feature attributions as signed °F amounts, largest first."""
    out = [{"feature": a["feature"], "label": LABELS.get(a["feature"], a["feature"]),
            "amount_f": _r2(a["attribution"])} for a in attributions]
    out.sort(key=lambda a: -abs(a["amount_f"]))
    return out


def _why(reasons: list[dict]) -> str:
    return ", ".join(f"{r['label']} {r['amount_f']:+.2f}°F" for r in reasons)


def _site(row: dict, forecast: Optional[float]) -> dict:
    offset = _r2(row["predicted_offset_f"])
    reasons = _reasons(row["top_feature_attributions"])
    return {
        "geo_id": row["geo_id"],
        "latitude": round(row["latitude"], 4),
        "longitude": round(row["longitude"], 4),
        "predicted_offset_f": offset,
        # The forecast plus the rounded offset, so the two numbers the planner sees add up.
        "expected_high_f": None if forecast is None else round(forecast + offset, 1),
        "reasons": reasons,
        "why": _why(reasons),
        "residents": {
            "total_pop": int(row["total_pop"]),
            "households": int(row["households"]),
            "households_no_vehicle": int(row["no_cars"]),
            "no_vehicle_rate": round(row["no_vehicle_rate"], 3),
            "poverty_rate": round(row["poverty_rate"], 3),
            "median_age": row["median_age"],
        },
    }


def recommend_sites(count: int = 3, forecast_high_f: Optional[float] = None, area: str = "all") -> dict:
    """Rank places in Dallas for permanent cooling centers.

    Runs the BigQuery ML heat model (ML.EXPLAIN_PREDICT) on every census tract center inside
    the area the Heat Watch volunteers drove, keeps the tracts predicted hotter than the city
    average, and orders them by households with no vehicle.

    Args:
        count: How many sites to return, 1 to 10.
        forecast_high_f: The forecast high in °F for the day the planner is asking about.
            Leave it out when no forecast was given.
        area: "all", or the half of the driven area to search: "north", "south", "east" or "west".
    """
    area = (area or "all").strip().lower()
    if area not in AREAS:
        return {"status": "error", "message": f"area must be all, north, south, east or west, not '{area}'"}
    count = max(1, min(int(count), config.MAX_SITES))
    forecast = None if forecast_high_f is None else float(forecast_high_f)
    try:
        box = _driven_area()
        mid_lat, mid_lon = (box["south"] + box["north"]) / 2, (box["west"] + box["east"]) / 2
        search = dict(box)
        if area == "south":
            search["north"] = mid_lat
        elif area == "north":
            search["south"] = mid_lat
        elif area == "west":
            search["east"] = mid_lon
        elif area == "east":
            search["west"] = mid_lon

        rows = [dict(r) for r in _bq().query(SCORE_SQL, job_config=_params(**search)).result()]
        # Gate: predicted hotter than the city average at the precision we report.
        hot = [r for r in rows if round(r["predicted_offset_f"], 2) > 0]
        hot.sort(key=lambda r: (-r["no_cars"], -r["predicted_offset_f"], r["geo_id"]))
        picks = hot[:count]

        result = {
            "status": "ok" if picks else "no_sites",
            "request": {"count": count, "area": area, "forecast_high_f": forecast},
            "search_area": {"name": area, "description": _describe(area, mid_lat, mid_lon),
                            **{k: round(v, 4) for k, v in search.items()}},
            "candidates": {"tracts_scored": len(rows), "predicted_hotter_than_city": len(hot)},
            "ranking_rule": RANKING_RULE,
            "sites": [{"rank": i, **_site(r, forecast)} for i, r in enumerate(picks, 1)],
            "set_aside": None,
            "reach": None,
            "notes": [],
        }
        if not picks:
            return result

        # The hottest tract is the obvious objection in a committee room: show where it ranks.
        hottest = max(rows, key=lambda r: (r["predicted_offset_f"], r["geo_id"]))
        if hottest["geo_id"] not in {p["geo_id"] for p in picks}:
            rank = [r["geo_id"] for r in hot].index(hottest["geo_id"]) + 1
            set_aside = _site(hottest, forecast)
            set_aside["rank_under_rule"] = rank
            set_aside["note"] = (f"Hottest predicted tract in this area, ranked {rank} of {len(hot)} because "
                                 f"{int(hottest['no_cars'])} households there have no vehicle.")
            result["set_aside"] = set_aside

        pop = sum(r["total_pop"] for r in picks)
        households = sum(r["households"] for r in picks)
        no_cars = sum(r["no_cars"] for r in picks)
        result["reach"] = {
            "picks": {"sites": len(picks), "total_pop": int(pop), "households_no_vehicle": int(no_cars),
                      "poverty_rate": round(sum(r["poverty_rate"] * r["total_pop"] for r in picks) / pop, 3),
                      "no_vehicle_rate": round(no_cars / households, 3)},
            "city": _city_rates(),
        }
        if len(picks) < count:
            result["notes"].append(
                f"Only {len(hot)} tracts in {result['search_area']['description']} are predicted hotter "
                f"than the city average, so {len(picks)} sites are listed, not {count}.")
        return result
    except Exception as e:  # noqa: BLE001  the agent reports the failure; it never invents a result
        return {"status": "error", "message": str(e)}


def _km_outside(lat: float, lon: float, box: dict) -> float:
    """Straight-line distance from a point to the nearest edge of the box, in km."""
    dlat = max(box["south"] - lat, 0, lat - box["north"]) * 111.2
    dlon = max(box["west"] - lon, 0, lon - box["east"]) * 111.2 * math.cos(math.radians(lat))
    return math.hypot(dlat, dlon)


def check_point(latitude: float, longitude: float, forecast_high_f: Optional[float] = None) -> dict:
    """Estimate how much hotter or cooler than the city average one location in Dallas runs.

    Runs the BigQuery ML heat model (ML.EXPLAIN_PREDICT) for the point itself. Refuses points
    outside the area the Heat Watch volunteers drove, because the model was trained only there.

    Args:
        latitude: Latitude in decimal degrees, for example 32.806.
        longitude: Longitude in decimal degrees, negative in Dallas, for example -96.753.
        forecast_high_f: The forecast high in °F, if the planner gave one.
    """
    forecast = None if forecast_high_f is None else float(forecast_high_f)
    point = {"latitude": latitude, "longitude": longitude}
    try:
        box = _driven_area()
        area = {k: round(v, 4) for k, v in box.items()}
        # Checked before any model call: outside the box the model would be extrapolating.
        if not (box["south"] <= latitude <= box["north"] and box["west"] <= longitude <= box["east"]):
            km = _km_outside(latitude, longitude, box)
            return {"status": "outside_driven_area", "point": point, "km_outside": round(km, 1),
                    "driven_area": area,
                    "message": (f"This point is {km:.0f} km outside the area where street readings were taken. "
                                "The model was trained only inside that area, so no offset is given.")}

        r = dict(list(_bq().query(POINT_SQL, job_config=_params(lat=latitude, lon=longitude)).result())[0])
        site = _site(r, forecast)
        near, within = r["meters_to_nearest_reading"], r["readings_within_500m"]
        if within == 0:
            basis = (f"No street reading within 500 m (the nearest is {near / 1000:.1f} km away). "
                     "This is the model's estimate, not a measurement.")
        else:
            basis = (f"{within} street readings within 500 m (the nearest is {near:.0f} m away). "
                     "The figure is still the model's estimate.")
        return {"status": "ok", "point": point,
                "predicted_offset_f": site["predicted_offset_f"], "expected_high_f": site["expected_high_f"],
                "reasons": site["reasons"], "why": site["why"],
                "readings_nearby": {"meters_to_nearest_reading": round(near), "readings_within_500m": within,
                                    "basis": basis},
                "nearest_tract": {"geo_id": r["geo_id"], "meters_to_tract_center": round(r["meters_to_tract_center"]),
                                  "residents": site["residents"]},
                "driven_area": area}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)}
