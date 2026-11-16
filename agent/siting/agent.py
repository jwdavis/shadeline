"""Shadeline: one ADK agent with two kinds of tool.

- recommend_sites and check_point, our tools: the BigQuery ML heat model through
  ML.EXPLAIN_PREDICT, then the gate, the ranking and who the sites reach.
- BigQuery's managed MCP server, read-only, for station history and model evaluation.
"""
import google.auth
import google.auth.transport.requests
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

from . import config
from .prompt import INSTRUCTION
from .tools import check_point, recommend_sites

_creds = None


def _bigquery_auth(_ctx) -> dict[str, str]:
    """A fresh bearer token from Application Default Credentials for every MCP request."""
    global _creds
    if _creds is None:
        _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
    if not _creds.valid:
        _creds.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {_creds.token}", "x-goog-user-project": config.PROJECT}


bigquery_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(url="https://bigquery.googleapis.com/mcp", timeout=30.0),
    header_provider=_bigquery_auth,
    tool_filter=["execute_sql_readonly", "get_table_info", "list_table_ids"],   # read-only on purpose
)

model = Gemini(
    model=config.MODEL,
    # The global endpoint, explicitly, whatever region the environment sets for everything else.
    client_kwargs={"vertexai": True, "project": config.PROJECT, "location": config.MODEL_LOCATION},
    # A busy endpoint answers 429 or 5xx now and then: retry with exponential backoff.
    retry_options=types.HttpRetryOptions(attempts=4, initial_delay=1.0, max_delay=8.0, exp_base=2.0,
                                         http_status_codes=[429, 500, 502, 503, 504]),
)

root_agent = LlmAgent(
    name="shadeline",
    model=model,
    description="Recommends and defends sites for permanent cooling centers in Dallas.",
    instruction=INSTRUCTION,
    tools=[recommend_sites, check_point, bigquery_mcp],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
    ),
)
