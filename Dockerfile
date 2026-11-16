# Shadeline: the planner's page with the siting agent running inside it.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY agent/requirements.txt agent-requirements.txt
COPY console/requirements.txt console-requirements.txt
RUN pip install -r agent-requirements.txt -r console-requirements.txt
COPY agent/ agent/
COPY console/ console/
ENV PYTHONPATH=/app/agent
# One worker: sessions are held in this process's memory.
CMD exec uvicorn console.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
