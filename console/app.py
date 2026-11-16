"""Shadeline: the planner's page and a small API around the siting agent.

The agent (agent/siting) runs in this process with ADK's Runner. Sessions live in memory, so
the service runs as a single instance (see scripts/deploy.sh). Every reply on the page is the
agent's own output for that turn; nothing is cached or stored.

    PYTHONPATH=agent uvicorn console.app:app --port 8080
"""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from siting.agent import root_agent

APP_NAME, USER_ID = "shadeline", "planner"
STATIC = Path(__file__).parent / "static"

sessions = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=sessions)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await runner.close()  # closes the BigQuery MCP connection cleanly


app = FastAPI(title="Shadeline", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Ask(BaseModel):
    message: str
    session_id: str | None = None


def step_for(call) -> dict:
    """One line in "What the assistant ran" for a tool call, before its result is known."""
    args = dict(call.args or {})
    if call.name == "recommend_sites":
        return {"tool": call.name, "label": "Scored tract centers with ML.EXPLAIN_PREDICT and ranked them",
                "detail": json.dumps(args)}
    if call.name == "check_point":
        return {"tool": call.name, "label": "Scored one point with ML.EXPLAIN_PREDICT", "detail": json.dumps(args)}
    if call.name == "execute_sql_readonly":
        sql = args.get("query") or args.get("sql") or json.dumps(args)
        if "station_daily_temps" in sql:
            label = "Station history query (BigQuery MCP)"
        elif "ML.EVALUATE" in sql.upper():
            label = "Model evaluation (BigQuery MCP)"
        else:
            label = "Table query (BigQuery MCP)"
        return {"tool": call.name, "label": label, "detail": sql}
    return {"tool": call.name, "label": f"{call.name} (BigQuery MCP)", "detail": json.dumps(args, indent=1)}


def _deg(x) -> str:
    return f"{x:g}°F"


def recommend_detail(r: dict) -> str | None:
    """What recommend_sites found, in words. None if the result has nothing to say."""
    if r.get("status") == "error":
        return f"Failed: {r.get('message')}"
    c, req = r.get("candidates"), r.get("request") or {}
    if not c:
        return None
    forecast = req.get("forecast_high_f")
    return (f"{c['tracts_scored']} tract centers scored, {c['predicted_hotter_than_city']} predicted hotter "
            f"than the city average, {len(r.get('sites') or [])} sites returned "
            f"(area: {req.get('area')}, forecast: {_deg(forecast) if forecast is not None else 'none'})")


def point_detail(r: dict) -> str | None:
    """What check_point found, in words."""
    if r.get("status") == "error":
        return f"Failed: {r.get('message')}"
    if r.get("status") == "outside_driven_area":
        return f"outside the driven area by {r['km_outside']:.1f} km, no prediction run"
    if r.get("status") == "ok":
        p, near = r["point"], r["readings_nearby"]
        return (f"{p['latitude']:g}, {p['longitude']:g}: {r['predicted_offset_f']:+.2f}°F, "
                f"nearest street reading {near['meters_to_nearest_reading']:,} m")
    return None


DETAIL = {"recommend_sites": recommend_detail, "check_point": point_detail}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# Not /healthz: Cloud Run reserves that path and answers 404 before the request reaches us.
@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


@app.post("/api/ask")
async def ask(body: Ask):
    if not body.message.strip():
        return JSONResponse({"error": "Type a question first."}, status_code=400)
    if body.session_id:
        session = await sessions.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=body.session_id)
        if session is None:  # the service restarted and the conversation is gone
            return JSONResponse({"error": "This conversation has ended. Start a new question."}, status_code=410)
    else:
        session = await sessions.create_session(app_name=APP_NAME, user_id=USER_ID)

    t0 = time.perf_counter()
    steps, by_call_id, reply, errors = [], {}, [], []
    message = types.Content(role="user", parts=[types.Part(text=body.message)])
    try:
        async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
            for part in (event.content.parts if event.content and event.content.parts else []):
                if part.function_call:
                    step = step_for(part.function_call)
                    steps.append(step)
                    by_call_id[part.function_call.id] = step
                elif part.function_response and part.function_response.name in DETAIL:
                    step = by_call_id.get(part.function_response.id)
                    detail = DETAIL[part.function_response.name](part.function_response.response or {})
                    if step and detail:
                        step["detail"] = detail
                elif part.text and not part.thought and event.is_final_response():
                    reply.append(part.text)
            if event.error_code:
                errors.append(f"{event.error_code}: {event.error_message or ''}".strip())
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")

    seconds = round(time.perf_counter() - t0, 1)
    text = "".join(reply).strip()
    if not text:
        error = "; ".join(errors) or "The assistant returned no answer."
        return JSONResponse({"session_id": session.id, "error": error, "steps": steps, "seconds": seconds},
                            status_code=502)
    return {"session_id": session.id, "reply": text, "steps": steps, "seconds": seconds}
