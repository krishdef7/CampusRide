#!/usr/bin/env bash
# Reproducible load test: API, Postgres and load generator all run as Linux containers.
#   loadtest/run_in_docker.sh --requests 10000 --rate 300
#   loadtest/run_in_docker.sh --sweep 100 200 400 800 --requests 3000
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d db
docker compose --profile load build -q api loadtest
docker compose --profile load run --rm loadtest --create-db-only
docker compose --profile load up -d --force-recreate api
trap 'docker compose --profile load stop api >/dev/null' EXIT
docker compose --profile load run --rm loadtest "$@"
