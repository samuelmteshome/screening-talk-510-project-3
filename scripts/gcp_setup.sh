#!/usr/bin/env bash
# One-time Google Cloud setup. Paste into Cloud Shell (console.cloud.google.com, ">_" button):
#   bash <(curl -s https://raw.githubusercontent.com/samuelmteshome/screening-talk-510-project-3/dev/scripts/gcp_setup.sh)
# Safe to run twice. Creates (if missing):
#   project, bucket for data and models, Artifact Registry repo for the Docker image,
#   a deploy service account for GitHub Actions (Workload Identity Federation, no key file),
#   a runtime service account for Cloud Run (read the bucket).
# At the end it prints the GitHub repository variables to set.
set -euo pipefail
REPO="${REPO:-samuelmteshome/screening-talk-510-project-3}"
PROJECT_ID="${PROJECT_ID:-screening-talk-$(date +%y%m)}"
REGION="${REGION:-us-east1}"
BUCKET="${BUCKET:-${PROJECT_ID}-data}"

if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud projects create "$PROJECT_ID" --name="Screening Talk"
fi
gcloud config set project "$PROJECT_ID" >/dev/null
if [ "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')" != "True" ]; then
  ACCOUNT=$(gcloud billing accounts list --filter=open=true --format='value(name)' | head -1)
  [ -n "$ACCOUNT" ] || { echo "No billing account. Start the free trial at console.cloud.google.com/billing first."; exit 1; }
  gcloud billing projects link "$PROJECT_ID" --billing-account="$ACCOUNT"
fi
gcloud services enable run.googleapis.com artifactregistry.googleapis.com storage.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com

gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
gcloud artifacts repositories describe screening-talk --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create screening-talk --repository-format=docker --location="$REGION"

NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
DEPLOY_SA="github-deploy@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_SA="api-runtime@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$DEPLOY_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create github-deploy --display-name="GitHub Actions deploy"
gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create api-runtime --display-name="Cloud Run API"

for role in roles/run.admin roles/artifactregistry.writer roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$DEPLOY_SA" --role="$role" --condition=None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --member="serviceAccount:$DEPLOY_SA" \
  --role=roles/iam.serviceAccountUser >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$RUNTIME_SA" \
  --role=roles/storage.objectViewer >/dev/null

# GitHub Actions signs in as the deploy account, only from this repository.
gcloud iam workload-identity-pools describe github --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers describe github-repo --location=global --workload-identity-pool=github >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc github-repo --location=global --workload-identity-pool=github \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='$REPO'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/github/attribute.repository/$REPO" >/dev/null

cat <<OUT

Done. Set these GitHub repository variables (Settings -> Secrets and variables -> Actions -> Variables):
  GCP_PROJECT_ID   = $PROJECT_ID
  GCP_REGION       = $REGION
  GCS_BUCKET       = $BUCKET
  GCP_WIF_PROVIDER = projects/$NUM/locations/global/workloadIdentityPools/github/providers/github-repo
  GCP_DEPLOY_SA    = $DEPLOY_SA
  GCP_RUNTIME_SA   = $RUNTIME_SA
For local work (make data TOPIC=prostate): gcloud auth application-default login, then export GCS_BUCKET=$BUCKET
To give Alberto access: gcloud projects add-iam-policy-binding $PROJECT_ID --member=user:<his email> --role=roles/editor
OUT
