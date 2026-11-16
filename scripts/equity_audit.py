"""Who do our sites reach? Takes the system's top ten sites and compares their census tracts
with Dallas as a whole.

    GOOGLE_CLOUD_PROJECT=<project> python scripts/equity_audit.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from siting.tools import recommend_sites  # noqa: E402

r = recommend_sites(10)
if r["status"] != "ok":
    sys.exit(f"recommend_sites returned {r['status']}: {r.get('message', '')}")

print(f"{'rank':>4}  {'tract':<11}  {'latitude':>8}  {'longitude':>9}  {'offset':>7}  "
      f"{'no vehicle':>10}  {'no-veh rate':>11}  {'poverty':>7}")
for s in r["sites"]:
    res = s["residents"]
    print(f"{s['rank']:>4}  {s['geo_id']:<11}  {s['latitude']:>8.4f}  {s['longitude']:>9.4f}  "
          f"{s['predicted_offset_f']:>+6.2f}F  {res['households_no_vehicle']:>10,}  "
          f"{res['no_vehicle_rate']:>11.1%}  {res['poverty_rate']:>7.1%}")

picks, city = r["reach"]["picks"], r["reach"]["city"]
print()
print(f"{'':<28}{'our 10 sites':>14}{'Dallas':>10}")
print(f"{'poverty rate':<28}{picks['poverty_rate']:>14.1%}{city['poverty_rate']:>10.1%}")
print(f"{'households with no vehicle':<28}{picks['no_vehicle_rate']:>14.1%}{city['no_vehicle_rate']:>10.1%}")
print()
print(f"{'residents in our tracts':<28}{picks['total_pop']:>14,}")
print(f"{'households with no vehicle':<28}{picks['households_no_vehicle']:>14,}")
print()
print(f"Dallas = the {city['tracts']} loaded census tracts with residents, weighted by population "
      "(households for vehicles).")
