-- Days at or above 102°F at Dallas Love Field (USW00013960), year by year.
-- One station, so a day is counted once.
SELECT
  EXTRACT(YEAR FROM observation_date) AS year,
  COUNT(*) AS days_on_record,
  COUNTIF(max_temp_f >= 100) AS days_100_or_more,
  COUNTIF(max_temp_f >= 102) AS days_102_or_more,
  COUNTIF(max_temp_f >= 105) AS days_105_or_more
FROM `a4i_climate.station_daily_temps`
WHERE station_id = 'USW00013960'
GROUP BY year
ORDER BY year;
