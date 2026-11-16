#!/usr/bin/env bash
#
# Deploy Shadeline (the planner's page with the agent inside it) to Cloud Run.
#
#     GOOGLE_CLOUD_PROJECT=your-project bash scripts/deploy.sh
#
# Run from the repo root. Cloud Build builds the Dockerfile at the root. The service account
# needs BigQuery data viewer and job user, the MCP tool user role and Vertex AI user.

set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT first}"

# --min-instances 1: one instance stays warm, so the first question of the day has no cold start.
# --max-instances 1: sessions are held in the instance's memory; a second instance would not
#   know a session the first one started, and follow-ups would fail.
gcloud run deploy shadeline \
  --source . \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --region us-central1 \
  --service-account "agent-runner@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --min-instances 1 \
  --max-instances 1 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_LOCATION=global"
