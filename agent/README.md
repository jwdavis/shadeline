# Shadeline, the agent

An ADK agent for a resilience planner in the City of Dallas Office of Emergency Management.
The planner asks where permanent cooling centers should go; the agent runs the BigQuery ML
heat model, ranks the candidates and writes a Placement Recommendation with a draft memo
for the council committee.

## Tools

| Tool | What it does |
|---|---|
| `recommend_sites` (ours, `siting/tools.py`) | `ML.EXPLAIN_PREDICT` on every tract center in the driven area, then the gate, the ranking, the set-aside tract and who the sites reach |
| `check_point` (ours, `siting/tools.py`) | `ML.EXPLAIN_PREDICT` for one location, or a refusal with the distance if it lies outside the driven area |
| BigQuery managed MCP server (`execute_sql_readonly`, `get_table_info`, `list_table_ids`) | Station history ("how often does Dallas hit 102°F?") and the model's evaluation. Read-only |

## The rules, in code

| Rule | Definition |
|---|---|
| What the model predicts | An offset: °F hotter or cooler than the city average on the campaign afternoon. Never a temperature |
| Temperature on a forecast day | Forecast high plus the offset, rounded to one decimal. No forecast: the offset alone |
| Candidates | Tract centers with residents inside the box the volunteers drove (123), cut to the half the planner asked for |
| Areas | `all`, `north` / `south` (split at the box's middle latitude), `east` / `west` (middle longitude). The box comes from `heat_observations` |
| Gate | Predicted offset, rounded to two decimals, above zero |
| Ranking | Households with no vehicle, most first; ties to the higher offset, then the lower `geo_id` |
| Set aside | The hottest predicted candidate, when it is not a pick, with its rank under the rule |
| Reasons | All four `ML.EXPLAIN_PREDICT` attributions in °F, largest first |
| Who the sites reach | Picks' poverty rate (weighted by population) and share of households with no vehicle, beside the 615 Dallas tracts with residents |
| A single point | Its own coordinates, the nearest tract's housing age and units, and the distance to the nearest street reading |
| Outside the driven area | No prediction: status `outside_driven_area` with the distance in km |
| Count | 1 to 10 sites, default 3 |

## Files

| | |
|---|---|
| `siting/agent.py` | `root_agent`, the model (Gemini 3.8 Flash, global endpoint) and the MCP toolset |
| `siting/tools.py` | `recommend_sites` and `check_point` |
| `siting/prompt.py` | The instruction, including the Placement Recommendation layout |
| `siting/config.py` | Project, dataset, model names and the site limit, from the environment |

## Run it

From the repo root, with the tables loaded and built (`bash scripts/load.sh dallas`, then
`bash scripts/build_model.sh`):

```bash
pip install -r agent/requirements.txt
cp agent/siting/.env.example agent/siting/.env     # then set GOOGLE_CLOUD_PROJECT
adk web agent          # browser UI; pick "siting"
adk run agent/siting   # terminal
```

Credentials come from Application Default Credentials (`gcloud auth application-default login`).

## Check it

```bash
GOOGLE_CLOUD_PROJECT=<project> pytest -v tests/            # both tools against BigQuery
GOOGLE_CLOUD_PROJECT=<project> python scripts/validate.py  # the data checks (needs pandas, db-dtypes)
GOOGLE_CLOUD_PROJECT=<project> python scripts/equity_audit.py
```
