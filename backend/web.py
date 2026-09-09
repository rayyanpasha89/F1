"""Optional same-origin React hosting for the Lightsail container deployment."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


def mount_web(app, directory):
    root = Path(directory).resolve()
    if not (root / "index.html").is_file():
        raise RuntimeError("Frontend build is missing")

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(404, "Not found")
        if candidate.is_file():
            return FileResponse(candidate)
        if path.startswith("assets/"):
            raise HTTPException(404, "Asset not found")
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
