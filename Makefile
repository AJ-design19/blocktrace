.PHONY: install train test seed run-api run-web up
install:
	cd backend && pip install -r requirements.txt -r requirements-ml.txt -r requirements-dev.txt
	cd frontend && npm ci
	cd contracts && npm ci
train:
	cd backend && python -m ml.train
test:
	cd backend && python -m pytest -q
	cd contracts && npx hardhat test
seed:
	cd backend && python -m app.seed
run-api:
	cd backend && uvicorn app.main:app --reload --port 8000
run-web:
	cd frontend && npm run dev
up:
	docker compose up --build
