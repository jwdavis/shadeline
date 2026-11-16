"""Settings Shadeline reads, from the environment with defaults for our project."""
import os

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "jwd-heat-challenge")
DATASET = os.environ.get("SHADELINE_DATASET", "a4i_climate")

# Gemini is served from the global endpoint, whatever region Cloud Run runs in.
MODEL = os.environ.get("SHADELINE_MODEL", "gemini-3.8-flash")
MODEL_LOCATION = os.environ.get("SHADELINE_MODEL_LOCATION", "global")

# The BigQuery ML model built by sql/03_heat_offset_model.sql.
BQML_MODEL = os.environ.get("SHADELINE_BQML_MODEL", "heat_offset_model")

# A budget funds a handful of permanent sites; more than ten is not a siting question.
MAX_SITES = int(os.environ.get("SHADELINE_MAX_SITES", "10"))
