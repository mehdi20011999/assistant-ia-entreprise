.PHONY: install test lint eval run docker
install: ; pip install -r requirements-dev.txt
lint:    ; ruff check .
test:    ; pytest -v
eval:    ; python -m eval.run_eval
run:     ; uvicorn app.main:app --reload
docker:  ; docker compose up --build
check: lint test eval
