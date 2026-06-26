.PHONY: dev backend frontend migrate db-upgrade db-revision lint test

dev:
	@echo "Starting backend and frontend..."
	@make backend & make frontend & wait

backend:
	cd backend && uvicorn main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

db-upgrade:
	cd backend && alembic upgrade head

db-revision:
	cd backend && alembic revision --autogenerate -m "$(msg)"

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint

test:
	cd backend && pytest -v
	cd frontend && npx vitest run

test-backend:
	cd backend && pytest -v

test-frontend:
	cd frontend && npx vitest run
