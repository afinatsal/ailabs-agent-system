"""Smoke test dashboard: semua halaman & endpoint API utama bisa diakses."""

from fastapi.testclient import TestClient

from ailabs.config.settings import Settings
from ailabs.db.base import InMemoryStorage
from ailabs.dashboard.app import create_app


def make_client(tmp_path):
    settings = Settings(
        llm_provider="mock",
        supabase_url="",
        supabase_anon_key="",
        reviewer_enabled=True,
        local_workspace_path=str(tmp_path / "ws"),
    )
    app = create_app(settings=settings, storage=InMemoryStorage())
    return TestClient(app)


def test_all_pages_render(tmp_path):
    with make_client(tmp_path) as c:
        for path in ["/", "/agents", "/skills", "/workspace", "/settings", "/logs"]:
            res = c.get(path)
            assert res.status_code == 200, f"{path} -> {res.status_code}"


def test_submit_creates_job_and_detail_renders(tmp_path):
    with make_client(tmp_path) as c:
        res = c.post("/submit", data={"prompt": "Buat ringkasan singkat.", "project": "smoke"}, follow_redirects=False)
        assert res.status_code == 303
        location = res.headers["location"]
        assert location.startswith("/jobs/")

        page = c.get(location)
        assert page.status_code == 200

        job_id = location.split("/")[-1].split("?")[0]
        api = c.get(f"/api/jobs/{job_id}")
        assert api.status_code == 200
        payload = api.json()
        assert payload["job"]["id"] == job_id


def test_dashboard_json_apis(tmp_path):
    with make_client(tmp_path) as c:
        c.post("/submit", data={"prompt": "Misi pertama.", "project": "p"})
        for path in ["/api/agents", "/api/skills", "/api/settings", "/api/health", "/api/workspace"]:
            res = c.get(path)
            assert res.status_code == 200, f"{path} -> {res.status_code}"


def test_health_contains_checks(tmp_path):
    with make_client(tmp_path) as c:
        data = c.get("/api/health").json()
        assert "checks" in data or isinstance(data, list)


def test_clear_all_api(tmp_path):
    with make_client(tmp_path) as c:
        c.post("/submit", data={"prompt": "Misi untuk dihapus.", "project": "p"})
        res = c.post("/api/settings/clear")
        assert res.status_code == 200
        assert c.get("/api/settings").json()["counts"]["jobs"] == 0
