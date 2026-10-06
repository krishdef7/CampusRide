"""HTTP + WebSocket surface, with the real app and database (lifespan included)."""

import pytest
from fastapi.testclient import TestClient

from campusride.api.app import create_app
from campusride.config import Settings

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_dsn, pool):  # `pool` resets the tables
    app = create_app(Settings(database_url=db_dsn, llm_provider="none", log_json=False), run_background=False)
    with TestClient(app) as c:
        yield c


def test_ride_flow_and_websocket_events(client):
    rider = client.post("/riders", json={"name": "a"}).json()["id"]
    driver = client.post("/drivers", json={"name": "d", "vehicle_type": "auto", "lat": 29.8698, "lon": 77.8948}).json()["id"]
    ride = client.post("/rides", json={"rider_id": rider, "pickup_place_id": "rajendra", "dropoff_place_id": "lhc"}).json()
    assert ride["status"] == "assigned" and ride["driver_id"] == driver and ride["match"]["distance_m"] < 50

    with client.websocket_connect(f"/ws/rides/{ride['id']}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert client.post(f"/drivers/{driver}/rides/{ride['id']}/start").status_code == 200
        # The socket subscribes before reading the snapshot, so it can also receive the
        # "assigned" event the snapshot already reflects. Skip anything that isn't news.
        ev = ws.receive_json()
        while ev.get("status") == snap["ride"]["status"]:
            ev = ws.receive_json()
        assert ev["type"] == "ride_event" and ev["status"] == "in_progress" and "ts" in ev


def test_validation_and_domain_errors(client):
    rider = client.post("/riders", json={"name": "a"}).json()["id"]
    assert client.post("/rides", json={"rider_id": rider, "pickup_place_id": "nowhere", "dropoff_place_id": "lhc"}).status_code == 422
    assert client.post("/rides", json={"rider_id": rider, "pickup_place_id": "lhc", "dropoff_place_id": "lhc"}).status_code == 409
    assert client.post("/rides", json={"rider_id": rider, "pickup_place_id": "sac", "dropoff_place_id": "lhc",
                                       "passengers": 4, "vehicle_type": "auto"}).status_code == 409
    assert client.get("/rides/987654").status_code == 404


def test_agent_disabled_without_llm(client):
    assert client.post("/agent/chat", json={"session_id": "s", "rider_id": 1, "message": "hi"}).status_code == 503


def test_metrics_exposed(client):
    client.get("/healthz")
    body = client.get("/metrics").text
    assert "http_request_duration_seconds" in body and "match_duration_seconds" in body
