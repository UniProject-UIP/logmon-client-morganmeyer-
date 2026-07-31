.PHONY: install test ejemplo clean

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# El python3 de macOS es 3.9 y alcanza. Se puede forzar otro:
#   make install PYTHON=python3.12
PYTHON ?= $(shell for p in python3 python3.12 python3.11 python3.10 python3.9; do \
	command -v $$p >/dev/null 2>&1 || continue; \
	$$p -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null || continue; \
	echo $$p; break; \
done)

install: ## Entorno y dependencias, incluidas las del ejemplo
	@test -n "$(PYTHON)" || { echo "No encontré un Python >=3.9."; exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[test,ejemplo]"
	@echo "Listo. Probá: make ejemplo"

test: ## Corre los tests
	$(VENV)/bin/pytest -q

ejemplo: ## Levanta la tienda instrumentada en http://localhost:9000
	$(PY) -m uvicorn ejemplo.tienda:app --reload --port 9000

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__ *.egg-info
