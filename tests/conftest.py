"""Test-wide setup: fake Slack credentials and an in-memory checkpoint so
importing slack_app.py in tests never touches a real Slack API or writes a
SQLite file to disk.
"""

import os

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test-token")
os.environ.setdefault("SUPPORT_INBOX_CHANNEL_ID", "C_INBOX")
os.environ.setdefault("TEAM_REVIEW_CHANNEL_ID", "C_REVIEW")
os.environ.setdefault("AGENT_CHECKPOINT_PATH", ":memory:")
os.environ.setdefault("SLACK_TOKEN_VERIFICATION", "false")
