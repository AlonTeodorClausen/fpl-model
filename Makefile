# Always use the project's own virtual environment.
PY := .venv/bin/python

.PHONY: install test test-live app lock prune-caches

install:
	$(PY) -m pip install -r requirements.lock

test:
	$(PY) -m pytest -q

test-live:
	$(PY) -m pytest -q -m live

app:
	$(PY) -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false

lock:
	{ echo "# Exact versions tested with Python 3.14 (pip freeze of .venv)."; \
	  echo "# Install: .venv/bin/python -m pip install -r requirements.lock"; \
	  echo "# Regenerate after changing pyproject.toml: make lock"; \
	  $(PY) -m pip freeze; } > requirements.lock

prune-caches:
	$(PY) scripts/prune_forecast_caches.py
