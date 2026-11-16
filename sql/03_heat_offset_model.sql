-- The model: a linear regression on the offset, not on the temperature.
-- Features are things we know for a street nobody drove: where it is, how old
-- the housing around it is, and how much housing there is. Poverty and vehicle
-- access stay out of the model; they are used to rank sites, not to predict heat.
-- BigQuery ML holds out a random 20 percent of the rows for ML.EVALUATE.
CREATE OR REPLACE MODEL `a4i_climate.heat_offset_model`
OPTIONS (
  model_type = 'LINEAR_REG',
  input_label_cols = ['offset_f'],
  enable_global_explain = TRUE
) AS
SELECT
  offset_f,
  latitude,
  longitude,
  year_built,
  housing_units
FROM `a4i_climate.training_readings`;
