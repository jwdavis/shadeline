"""The notebook's section 10 checks, run on the tables loaded by scripts/load.sh.

The notebook has 22 checks. One of them ("tracts: ACS join kept them") compares two counts
that exist only while the notebook's own tract query runs, so it cannot be run on loaded
tables. The other 21 are here, in the notebook's order and wording.

    GOOGLE_CLOUD_PROJECT=<project> python scripts/validate.py
"""
import os

import pandas as pd
from google.cloud import bigquery

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
DS = f"{PROJECT}.a4i_climate"
client = bigquery.Client(project=PROJECT)
CHECKS = []


def check(name, passed, detail=""):
    CHECKS.append((name, bool(passed), str(detail)))


def q1(sql):
    return client.query(sql).to_dataframe().iloc[0]


h = q1(f'''
SELECT COUNT(*) AS n, MIN(temp_f) AS temp_min, MAX(temp_f) AS temp_max,
  MIN(humidity_pct) AS rh_min, MAX(humidity_pct) AS rh_max, MIN(heat_index_f) AS hi_min,
  MIN(observed_at) AS first_obs, COUNTIF(city IS NULL) AS null_city,
  MIN(latitude) AS lat_min, MAX(latitude) AS lat_max, MIN(longitude) AS lon_min, MAX(longitude) AS lon_max,
  COUNTIF(temp_f IS NULL) AS null_temp, COUNTIF(heat_index_f IS NULL) AS null_hi,
  COUNTIF(humidity_pct IS NULL) AS null_rh, COUNTIF(observed_at IS NULL) AS null_time,
  COUNT(DISTINCT FORMAT('%.4f,%.4f', latitude, longitude)) AS distinct_points
FROM `{DS}.heat_observations`''')
check("heat: has rows", h.n > 1000, f"{int(h.n):,} rows")
check("heat: no null temperature", h.null_temp == 0, f"{int(h.null_temp):,} nulls")
check("heat: temp physically sane", 40 <= h.temp_min and h.temp_max <= 140, f"{h.temp_min:.1f}F to {h.temp_max:.1f}F")
check("heat: no sentinel survivors", all(pd.isna(v) or v > -100 for v in (h.temp_min, h.hi_min, h.rh_min)),
      f"mins: temp {h.temp_min}, heat index {h.hi_min}, humidity {h.rh_min}")
check("heat: humidity 0-100 or null", pd.isna(h.rh_min) or (0 <= h.rh_min and h.rh_max <= 100), f"{h.rh_min} to {h.rh_max}")
check("heat: city label present", h.null_city == 0, f"{int(h.null_city):,} null")
check("heat: timestamps plausible", pd.isna(h.first_obs) or h.first_obs.year >= 2017, f"{h.first_obs}")
check("heat: coordinates present", pd.notna(h.lat_min) and abs(h.lat_min) <= 90, f"lat {h.lat_min:.3f}..{h.lat_max:.3f}")
check("heat: spatially spread", h.distinct_points > 500, f"{int(h.distinct_points):,} distinct points")
spread = h.temp_max - h.temp_min
check("heat: intra-city spread > 3F", spread > 3, f"{spread:.1f}F across the city")


def pct(x):
    return 100.0 * x / h.n if h.n else 0


print(f"Optional-column coverage:  heat index {100-pct(h.null_hi):.0f}% | humidity {100-pct(h.null_rh):.0f}% | timestamp {100-pct(h.null_time):.0f}%")

s = q1(f'''
SELECT COUNT(*) AS n, COUNT(DISTINCT station_id) AS stations, MIN(observation_date) AS first_day,
  MAX(observation_date) AS last_day, MIN(max_temp_f) AS temp_min, MAX(max_temp_f) AS temp_max
FROM `{DS}.station_daily_temps`''')
check("stations: has rows", s.n > 0, f"{s.n:,} station-days")
check("stations: at least one station", s.stations >= 1, f"{s.stations} station(s)")
check("stations: temp sane", -60 <= s.temp_min and s.temp_max <= 140, f"{s.temp_min:.0f}F to {s.temp_max:.0f}F")
check("stations: multi-year", (s.last_day - s.first_day).days > 365, f"{s.first_day} to {s.last_day}")

t = q1(f'''
SELECT COUNT(*) AS n, COUNTIF(LENGTH(geo_id) != 11) AS bad_geoid,
  COUNTIF(poverty_rate < 0 OR poverty_rate > 1) AS bad_poverty, COUNTIF(total_pop < 0) AS bad_pop,
  COUNTIF(tract_lat IS NULL OR tract_lon IS NULL) AS null_coords, SUM(total_pop) AS people
FROM `{DS}.tract_demographics`''')
check("tracts: has rows", t.n > 0, f"{int(t.n):,} tracts")
check("tracts: geo_id is 11 digits", t.bad_geoid == 0, f"{int(t.bad_geoid)} malformed")
check("tracts: poverty rate 0-1", t.bad_poverty == 0, f"{int(t.bad_poverty)} out of range")
check("tracts: population sane", t.bad_pop == 0 and t.people > 0, f"{int(t.people):,} people")
check("tracts: coordinates present", t.null_coords == 0, f"{int(t.null_coords)} missing")

# The box and its center come from our own query above, so formatting them in is safe.
nearest = q1(f'''
SELECT MIN(ST_DISTANCE(ST_GEOGPOINT(longitude, latitude),
  ST_GEOGPOINT({(h.lon_min + h.lon_max) / 2}, {(h.lat_min + h.lat_max) / 2}))) / 1000 AS km
FROM (SELECT DISTINCT station_id, latitude, longitude FROM `{DS}.station_daily_temps`)''').km
tracts_in_footprint = q1(f'''
SELECT COUNT(*) AS n FROM `{DS}.tract_demographics`
WHERE tract_lat BETWEEN {h.lat_min} AND {h.lat_max} AND tract_lon BETWEEN {h.lon_min} AND {h.lon_max}''').n
check("cross: station near traverses", pd.notna(nearest) and nearest < 40, f"nearest station {nearest:.0f} km from the traverse centroid")
check("cross: tracts overlap traverses", tracts_in_footprint > 0, f"{tracts_in_footprint} tracts inside the traverse footprint")

width = max(len(name) for name, _, _ in CHECKS)
passed = sum(1 for _, ok, _ in CHECKS if ok)
print("=" * (width + 34))
print(f"{'VALIDATION':<{width}}   RESULT   DETAIL")
print("=" * (width + 34))
for name, ok, detail in CHECKS:
    print(f"{name:<{width}}   {'PASS  ' if ok else 'FAIL >>'}  {detail}")
print("=" * (width + 34))
print(f"{passed} of {len(CHECKS)} checks passed")
