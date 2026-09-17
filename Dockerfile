FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Socket Mode needs no exposed port; switch to HTTP mode (see slack_app.py)
# and uncomment below if deploying behind a public webhook URL instead.
# EXPOSE 8000

CMD ["python", "slack_app.py"]
