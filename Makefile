.PHONY: install format lint clean all demo ingest summarize render status view

# --- Setup & Maintenance ---
install:
	uv sync

format:
	uv run ruff format .

lint:
	uv run ruff check .

clean:
	rm -rf site_output
	rm -rf archive_dir
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Cleaned up build artifacts."

# --- The "One Button" Commands ---

# 1. Build everything (Ingest -> Summarize -> Render)
# We use the python 'run' command internally as it's faster (single python process)
all:
	uv run python -m mastohuman.cli run $(ARGS)

# 2. Build everything AND serve the site locally
demo: all view

# --- Individual Pipeline Steps ---
# Use these if you only want to re-run a specific part of the process

ingest:
	uv run python -m mastohuman.cli ingest $(ARGS)

summarize:
	uv run python -m mastohuman.cli summarize $(ARGS)

render:
	uv run python -m mastohuman.cli render $(ARGS)

status:
	uv run python -m mastohuman.cli status $(ARGS)

# --- Viewer ---
view:
	@echo "-----------------------------------------------------"
	@echo "Serving site at http://localhost:8000"
	@echo "Press Ctrl+C to stop."
	@echo "-----------------------------------------------------"
	uv run python -m http.server 8000 --directory site_output