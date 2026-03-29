#!/usr/bin/env bash
# Deploy the races-api service to Cloud Run.
#
# Usage:
#   ./scripts/deploy_races_api.sh              # build + push + deploy
#   ./scripts/deploy_races_api.sh --no-build   # deploy existing image only

set -euo pipefail

PROJECT_ID="smartervote"
REGION="us-central1"
ENVIRONMENT="dev"
SERVICE="races-api-${ENVIRONMENT}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/smartervote-${ENVIRONMENT}/races-api:latest"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

NO_BUILD=false
for arg in "$@"; do
  [[ "$arg" == "--no-build" ]] && NO_BUILD=true
done

if [ "$NO_BUILD" = false ]; then
  echo "==> Building Docker image..."
  docker build -f "${REPO_ROOT}/services/races-api/Dockerfile" \
    -t "${IMAGE}" \
    "${REPO_ROOT}"

  echo "==> Pushing image to Artifact Registry..."
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
  docker push "${IMAGE}"
fi

echo "==> Deploying ${SERVICE} to Cloud Run..."
gcloud run services update "${SERVICE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --image "${IMAGE}"

echo ""
echo "Done. Service URL:"
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format "value(status.url)"
