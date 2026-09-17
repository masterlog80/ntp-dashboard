import os

os.environ["APP_VERSION"] = "test-v1"
os.environ["LOG_LEVEL"] = "CRITICAL"

from app import app

def test_healthz():
    client = app.test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK\\n"
    assert response.content_type.startswith("text/plain")