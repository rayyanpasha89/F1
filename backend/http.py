"""Shared HTTP delivery policy for the API and same-origin web application."""

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.gzip import GZipMiddleware


_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
_NO_STORE_PREFIXES = ("/api/chat", "/api/health")


def install_http_policy(app: FastAPI) -> None:
    """Install compression, server request IDs, security headers, and cache policy."""

    app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.middleware("http")
    async def delivery_policy(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        request.state.started_at = perf_counter()
        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        path = request.url.path
        sensitive = any(path == prefix or path.startswith(f"{prefix}/") for prefix in _NO_STORE_PREFIXES)
        if request.method != "GET" or response.status_code >= 400 or sensitive:
            response.headers["Cache-Control"] = "no-store"
        elif "cache-control" not in response.headers:
            response.headers["Cache-Control"] = (
                "public, max-age=300" if path.startswith("/api/") else "no-cache"
            )
        return response

