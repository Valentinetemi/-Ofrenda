"""The local API, with the mock storyteller so Ollama is not required."""

from pathlib import Path

from fastapi.testclient import TestClient

from ofrenda.app import create_app
from ofrenda.config import ROOT, Settings

SAMPLE = (
    "my mum is Funke, her dad was Baba Ayo from Ogbomoso, "
    "he had a brother Tunde who moved to Ghana"
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8000,
        data_dir=tmp_path / "data",
        sample_dir=ROOT / "sample",
        ollama_host="http://127.0.0.1:9",
        ollama_model="gemma2:2b",
        mock_llm=True,
        llm_timeout=2,
        segmenter_model=ROOT / "models" / "selfie_segmenter.tflite",
    )


def test_altar_story_suggestions_and_ghost(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["llm"] == "mock"

        page = client.get("/")
        assert page.status_code == 200
        assert "Remember me" in page.text

        tree = client.get("/api/tree").json()
        names = {person["name"] for person in tree["people"]}
        assert "Tunde Adeyemi" in names
        assert tree["narrator_id"] == "seyi"

        motion = client.get("/api/ghost/motion").json()
        assert motion["period_s"] == 3.2
        assert motion["amplitude_px"] == 10

        suggestions = client.get("/api/suggestions").json()["suggestions"]
        assert any(item["person_id"] == "tunde" and "Accra" in item["question"] for item in suggestions)

        told = client.post("/api/stories", json={"text": "Tunde had a wife called Ama from Accra"})
        assert told.status_code == 200, told.text
        body = told.json()
        assert body["message"].startswith("Set on the altar: Ama.")
        assert "Ama" in body["added"]
        assert any(person["name"] == "Ama" for person in body["tree"]["people"])

        again = client.post("/api/stories", json={"text": SAMPLE})
        assert again.status_code == 200
        assert "already on the altar" in again.json()["message"]

        ghost = client.get("/api/people/ireti/ghost.png")
        assert ghost.status_code == 200
        assert ghost.headers["content-type"].startswith("image/png")
        assert ghost.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert ghost.headers["x-segmenter"] in {"mediapipe", "border", "ellipse"}

        created = client.post(
            "/api/people",
            json={"name": "Lola Adeyemi", "origin": "Ibadan", "memories": ["She keeps the songs."]},
        )
        assert created.status_code == 200
        lola = created.json()["id"]
        linked = client.post(
            f"/api/people/{lola}/relationships",
            json={"kind": "parent", "other_id": "bisi"},
        )
        assert linked.status_code == 200
        lola_person = next(person for person in linked.json()["people"] if person["id"] == lola)
        assert "bisi" in lola_person["parent_ids"]
