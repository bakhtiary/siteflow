DATABASE_URL ?= postgresql://siteflow:siteflow@localhost:5432/siteflow
WEBSITE_STORAGE_BACKEND ?= local
WEBSITE_OUTPUT_DIR ?= $(CURDIR)/website-data

.PHONY: db db-down db-logs backend frontend dev

## Start Postgres in the background via docker compose
db:
	docker compose up -d postgres

## Stop and remove the docker compose services
db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

## Run the FastAPI backend locally against dockerized Postgres
backend: db
	cd backend && \
	DATABASE_URL=$(DATABASE_URL) \
	WEBSITE_STORAGE_BACKEND=$(WEBSITE_STORAGE_BACKEND) \
	WEBSITE_OUTPUT_DIR=$(WEBSITE_OUTPUT_DIR) \
	uv run uvicorn vitaweby.__main__:app --reload --host 0.0.0.0 --port 8000

## Run the frontend (Cloudflare Worker) dev server, proxying /api to the local backend
frontend:
	cd frontend && $(MAKE) dev

## Print instructions for running backend + frontend together
dev:
	@echo "Run these in separate terminals:"
	@echo "  make backend"
	@echo "  make frontend"
