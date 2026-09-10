"""Optional same-origin React hosting for the Lightsail container deployment."""

from pathlib import Path
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse


_HASHED_ASSET = re.compile(r"-[A-Za-z0-9_-]{8,}\.[^.]+$")


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
            cache_control = (
                "public, max-age=31536000, immutable"
                if path.startswith("assets/") and _HASHED_ASSET.search(candidate.name)
                else "public, max-age=300"
            )
            return FileResponse(candidate, headers={"Cache-Control": cache_control})
        if path.startswith("assets/"):
            raise HTTPException(404, "Asset not found")
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
