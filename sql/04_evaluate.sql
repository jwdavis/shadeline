-- How well the model does on the rows BigQuery ML held out.
SELECT
  ROUND(r2_score, 3) AS r2_score,
  ROUND(mean_absolute_error, 3) AS mean_absolute_error_f,
  ROUND(median_absolute_error, 3) AS median_absolute_error_f,
  ROUND(mean_squared_error, 3) AS mean_squared_error
FROM ML.EVALUATE(MODEL `a4i_climate.heat_offset_model`);

-- Which features carry the model, on one scale.
SELECT processed_input AS feature, ROUND(weight, 4) AS standardized_weight
FROM ML.WEIGHTS(MODEL `a4i_climate.heat_offset_model`, STRUCT(TRUE AS standardize))
ORDER BY ABS(weight) DESC;
