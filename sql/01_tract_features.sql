-- Census tracts, cleaned for modeling and ranking.
-- ACS writes -666666666 where it has no value. We turn those into NULL so they
-- cannot reach the model or an average. median_income is NULL in every Dallas
-- tract, so we leave it out and use poverty_rate instead.
-- in_driven_area marks tracts whose center lies inside the box the Heat Watch
-- volunteers drove (the min and max latitude and longitude of the readings).
CREATE OR REPLACE TABLE `a4i_climate.tract_features` AS
WITH box AS (
  SELECT MIN(latitude) AS lat_min, MAX(latitude) AS lat_max,
         MIN(longitude) AS lon_min, MAX(longitude) AS lon_max
  FROM `a4i_climate.heat_observations`
)
SELECT
  t.geo_id,
  t.tract_lat,
  t.tract_lon,
  t.total_pop,
  t.households,
  t.housing_units,
  t.no_cars,
  t.poverty_rate,
  t.no_vehicle_rate,
  NULLIF(t.median_age, -666666666) AS median_age,
  NULLIF(t.median_year_structure_built, -666666666) AS year_built,
  t.tract_lat BETWEEN box.lat_min AND box.lat_max
    AND t.tract_lon BETWEEN box.lon_min AND box.lon_max AS in_driven_area
FROM `a4i_climate.tract_demographics` AS t
CROSS JOIN box;
