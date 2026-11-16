#!/usr/bin/env bash
# Builds what Shadeline reads on top of the loaded data:
#   tract_features      cleaned census tracts, flagged inside or outside the driven area
#   training_readings   every street reading with its offset and the nearest tract's housing
#   heat_offset_model   the BigQuery ML LINEAR_REG on the offset
# then prints the model's evaluation.
# Run after scripts/load.sh (or the notebook):  bash scripts/build_model.sh
#
# A rerun retrains the model. BigQuery ML draws a new random 20 percent hold-out each time,
# so every offset shifts slightly and the evaluation numbers change with it.
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT to your project id}"
cd "$(dirname "$0")/.."

for f in sql/01_tract_features.sql sql/02_training_readings.sql sql/03_heat_offset_model.sql sql/04_evaluate.sql; do
  echo "Running $f"
  bq --project_id="$GOOGLE_CLOUD_PROJECT" query --use_legacy_sql=false --location=US --format=pretty < "$f"
done
