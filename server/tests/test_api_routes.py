"""HTTP-surface tests via FastAPI TestClient (covers app.py + lifespan + routes/admin.py).
No DB/Ollama: run_proactive_tick is patched in the admin route's namespace."""
from fastapi.testclient import TestClient


def test_health():
    from src.app import app
    with TestClient(app) as client:  # context manager runs lifespan (start/stop daemon)
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_admin_tick_endpoint(monkeypatch):
    import src.routes.admin as admin
    from src.app import app

    monkeypatch.setattr(
        admin, "run_proactive_tick",
        lambda student_id, session_id, playground=None: {
            "detected": [], "acted": [{"trigger_type": "wheel_spin", "message": "hi"}],
        },
    )
    with TestClient(app) as client:
        resp = client.post("/admin/tick", json={"student_id": "s", "session_id": "sess"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["acted"][0]["trigger_type"] == "wheel_spin"


def test_admin_tick_requires_fields():
    from src.app import app
    with TestClient(app) as client:
        resp = client.post("/admin/tick", json={"student_id": "s"})  # missing session_id
    assert resp.status_code == 422
