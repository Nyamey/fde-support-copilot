FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HTTP mode (SLACK_MODE=http): gunicorn serves the Flask app directly on
# Render's assigned $PORT, never running slack_app.py's __main__ block.
# Socket Mode (SLACK_MODE=socket, the local-dev default) needs no exposed
# port at all: `docker run` without -p works fine for it.
#
# Render's free-tier Web Service has no persistent disk: every cold start
# after the container spins down boots from a fresh image filesystem, so
# kb.duckdb (deliberately gitignored, see knowledge_base/db.py) never
# survives between wakes. Re-ingesting docs/ on every boot if the DB is
# missing keeps the deployment self-contained without committing a
# generated binary. It costs one embedding-API round trip per cold
# start, which is a fair trade for a demo-scale knowledge base.
CMD ["sh", "-c", "test -f \"${DUCKDB_PATH:-./knowledge_base/kb.duckdb}\" || python -m knowledge_base.ingest --source \"${KB_SOURCE_DIR:-./docs}\"; if [ \"$SLACK_MODE\" = \"http\" ]; then gunicorn -b 0.0.0.0:${PORT:-3000} slack_app:flask_app; else python slack_app.py; fi"]
