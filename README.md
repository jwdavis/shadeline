# Shadeline

A siting desk for Dallas cooling centers. Agents for Impact 2026, Challenge 1 (Urban Heat),
"This budget cycle" track.

**Live app:** https://shadeline-641165271014.us-central1.run.app

The challenge brief we built from is in [CHALLENGE.md](CHALLENGE.md).

## Our scenario

> We are the City of Dallas Office of Emergency Management. Next year's budget funds two
> permanent cooling centers with backup power. The council committee is briefed in two
> weeks, and it will ask why these two places and not two others.

| | |
|---|---|
| User | A resilience planner on city staff, writing the committee briefing |
| Track | This budget cycle: permanent sites, answerable to a council |
| City | Dallas. Love Field reached 102°F or more on 98 days from 2019 to 2025: 39 of them in 2023 and 1 in 2021. Permanent sites have to be right in both kinds of year |

## What it does

The planner asks where the centers should go. Shadeline returns a Placement Recommendation:
ranked sites with coordinates, how much hotter each runs than the city average and what
that means on the forecast day, why (each factor with its amount), who lives there, who
the sites reach beside Dallas as a whole, and a draft memo for the committee. It also
checks a single location, refuses a location outside the area where street readings were
taken, and answers how often Dallas gets this hot from seven years of station history.

```
planner's question
   │
   ▼
ADK agent (Gemini 3.8 Flash)
   │  recommend_sites (our tool)
   │      ML.EXPLAIN_PREDICT on every tract center in the driven area ─► BigQuery ML model
   │      gate: predicted hotter than the city ─► rank: households with no vehicle
   │      ─► who the picks reach
   │  check_point (our tool)
   │      inside the driven area? ─► ML.EXPLAIN_PREDICT for the point ─► nearest street reading
   │  station history and model questions ──► BigQuery managed MCP server
   ▼
Placement Recommendation  ──►  planner's page (Cloud Run)
```

## Stack

| Requirement | Ours |
|---|---|
| ADK agent, Python | [agent/siting/agent.py](agent/siting/agent.py) |
| Gemini | Gemini 3.8 Flash, global endpoint |
| BigQuery | Dataset `a4i_climate` |
| BigQuery ML | `heat_offset_model`, a `LINEAR_REG` on the offset. Both tools call `ML.EXPLAIN_PREDICT` on every question |
| Managed MCP server | BigQuery's, read-only tools, for station history ("how often") and model evaluation questions |
| Tools we built | `recommend_sites` and `check_point` in [agent/siting/tools.py](agent/siting/tools.py) |
| Deployed | Cloud Run, one service: the page with the agent inside it ([scripts/deploy.sh](scripts/deploy.sh)) |

## Decisions

| Decision | What we chose | Why |
|---|---|---|
| What the model predicts | The offset: a reading minus the average of the whole campaign afternoon | Every reading was taken in the same hour, so the differences are the city, not the weather. A planner adds the offset to a forecast |
| Features | Latitude, longitude, housing age, housing units | All four exist for a street nobody drove. Heat index and humidity come from the same sensor as the label and exist only where a car went, so they are out |
| Where poverty and vehicle access go | The ranking, not the model | They describe who needs a center, not why a block is hot |
| Which places we score | The 123 tract centers with residents inside the box the volunteers drove | The tract table covers six counties; the model has seen one 21 km by 22 km box. Outside it the model is guessing |
| Ranking | Tracts predicted hotter than the city average, ordered by households with no vehicle | A permanent center is for people who cannot drive to one |
| A point outside the driven area | Refused, with the distance | A number there would look as good as any other and mean nothing |
| A single point | Its own coordinates, the nearest tract's housing | Tracts are center points in this data, with no boundaries |
| How often | Days at or above a threshold at Dallas Love Field, asked as its own question | The station nearest the driven area with every day of 2019 to 2025. One station, so a day is counted once |

## The data

All three tables are the provided data, loaded with `bash scripts/load.sh dallas`. We added
no outside data.

| Table | What it is | What we use it for |
|---|---|---|
| `heat_observations` | 19,491 street readings from one Heat Watch afternoon | Training the model: where it runs hotter |
| `station_daily_temps` | Daily highs at 16 stations, 2019 to 2025 | How often Dallas gets this hot (Love Field only) |
| `tract_demographics` | 618 census tracts | Housing features, and who lives at a site |

What we found in the tract table and did about it ([sql/01](sql/01_tract_features.sql)):

- ACS writes `-666666666` where it has no value: year built in 7 tracts and median age in
  3. We set those to NULL in `tract_features`.
- `median_income` is NULL in all 618 tracts, so we use the poverty rate.
- Three tracts have no residents. They are never candidates and never in an average.

The loaded tables carry no race or ethnicity column and we added none. Nothing about race
is in the model or the ranking.

## The model

`sql/02` builds the training rows (each reading with its offset and the nearest tract's
housing), `sql/03` trains the model, `sql/04` evaluates it
([output](docs/model-evaluation.txt)).

| | |
|---|---|
| Type | BigQuery ML `LINEAR_REG`, label `offset_f` |
| Rows | 19,491 readings; BigQuery ML holds out a random 20 percent |
| R² | 0.062 |
| Mean absolute error | 0.841°F |

The model explains about 6 percent of the difference between readings, so a predicted
offset is a small nudge: offsets for our candidates run from -0.55 to +0.68°F. Who lives in
a tract moves our ranking far more than the model does.

## Validation

`scripts/validate.py` runs the notebook's section 10 checks on our loaded tables: 20 of 21
passed ([output](docs/validation-output.txt)). The notebook has 22; one compares two counts
that exist only while the notebook's own tract query runs.

| Check that failed | What it found | What we did |
|---|---|---|
| heat: city label present | `city` is NULL in all 19,491 readings loaded by `load.sh` | Nothing filters on `city`. We loaded one city |

Tests for the two tools are in [tests/](tests/test_tools.py): 7 tests, all passing
([output](docs/test-output.txt)).

## Equity audit

`scripts/equity_audit.py` takes the system's top ten sites and compares their tracts with
Dallas ([output](docs/equity-audit-output.txt)).

| | Our 10 sites | Dallas |
|---|---:|---:|
| Poverty rate | 24.9% | 12.6% |
| Households with no vehicle | 25.5% | 5.4% |

The ten tracts hold 31,338 residents and 3,676 households with no vehicle. Our picks sit in
neighborhoods with more need than Dallas as a whole. Dallas here means the 615 loaded
census tracts with residents, weighted by population (households for vehicles).

## How often

[sql/05](sql/05_hot_days_by_year.sql), [output](docs/hot-days-by-year.txt). Days at Dallas
Love Field:

| Year | 100°F or more | 102°F or more | 105°F or more |
|---|---:|---:|---:|
| 2019 | 18 | 10 | 0 |
| 2020 | 12 | 8 | 4 |
| 2021 | 5 | 1 | 0 |
| 2022 | 47 | 26 | 5 |
| 2023 | 49 | 39 | 22 |
| 2024 | 23 | 10 | 3 |
| 2025 | 6 | 4 | 0 |

## Limits

- The street readings are one afternoon. They say where it ran hotter that day, not how
  hot a place gets.
- Volunteers chose the routes. 61 of the 124 tracts in the driven area have no reading.
- The model's reasons can only name its four features. It knows nothing about trees,
  pavement or shade.
- Sites are tract centers. The data has no street addresses and no tract boundaries.
- Households with no vehicle is a count of who lacks a car, not a walking distance.
- It cannot say what a site's offset would become after planting or repaving.

## Not built

- A map.
- The hot-day count inside the recommendation. "How often" is a separate question.
- Costs, a list of candidate buildings, or what a site would displace.
- A minimum distance between sites: two picks can be neighboring tracts.
- Street names, walking routes, transit.

## Run it

```bash
export GOOGLE_CLOUD_PROJECT=<your project>
bash scripts/load.sh dallas           # the three provided tables
bash scripts/build_model.sh           # tract_features, training_readings, the model
pip install -r agent/requirements.txt -r console/requirements.txt
PYTHONPATH=agent uvicorn console.app:app --port 8080     # the planner's page
adk web agent                                            # or the ADK dev UI
```

More on the agent: [agent/README.md](agent/README.md).
