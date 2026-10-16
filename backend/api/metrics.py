"""FastAPI router for Prometheus metrics scraping."""

from fastapi import APIRouter, Response

from backend.observability.metrics import get_metrics_content_type, render_metrics

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus exposition format endpoint."""
    return Response(
        content=render_metrics(),
        media_type=get_metrics_content_type(),
    )
