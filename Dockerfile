FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HTTP mode (SLACK_MODE=http): gunicorn serves the Flask app directly on
# Render's assigned $PORT, never running slack_app.py's __main__ block.
# Socket Mode (SLACK_MODE=socket, the local-dev default) needs no exposed
# port at all — `docker run` without -p works fine for it.
CMD ["sh", "-c", "if [ \"$SLACK_MODE\" = \"http\" ]; then gunicorn -b 0.0.0.0:${PORT:-3000} slack_app:flask_app; else python slack_app.py; fi"]
