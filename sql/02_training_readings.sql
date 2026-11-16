-- One row per street reading, with the label and the features of the nearest tract.
-- Label: offset_f = the reading minus the mean of the whole campaign afternoon.
-- The tract table has center points and no boundaries, so a reading belongs to
-- the tract whose center is nearest.
-- heat_index_f and humidity_pct are left behind on purpose: they come from the
-- same sensor in the same second as temp_f and exist only where a car drove.
CREATE OR REPLACE TABLE `a4i_climate.training_readings` AS
WITH readings AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY latitude, longitude, temp_f) AS reading_id,
    latitude,
    longitude,
    temp_f,
    temp_f - AVG(temp_f) OVER () AS offset_f
  FROM `a4i_climate.heat_observations`
)
SELECT
  r.reading_id,
  r.latitude,
  r.longitude,
  r.temp_f,
  r.offset_f,
  t.geo_id,
  t.year_built,
  t.housing_units
FROM readings AS r
CROSS JOIN `a4i_climate.tract_features` AS t
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY r.reading_id
  ORDER BY ST_DISTANCE(ST_GEOGPOINT(t.tract_lon, t.tract_lat), ST_GEOGPOINT(r.longitude, r.latitude))
) = 1;
