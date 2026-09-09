from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web import mount_web


def test_spa_deep_links_assets_and_api_boundaries(tmp_path):
    (tmp_path / "index.html").write_text("<html>F1 app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text('console.log("F1")')
    app = FastAPI()
    mount_web(app, tmp_path)
    with TestClient(app) as client:
        assert client.get("/races/1128").text == "<html>F1 app</html>"
        assert "javascript" in client.get("/assets/app.js").headers["content-type"]
        assert client.get("/api/unknown").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/..%2Foutside").status_code == 404
        assert client.get("/").headers["cache-control"] == "no-cache"
