"""uvicorn entry: ``uv run guidance-relevance-web``."""

from __future__ import annotations

import uvicorn
from dotenv import load_dotenv

from .settings import get_settings


def main() -> None:
    load_dotenv()
    settings = get_settings()
    uvicorn.run(
        "guidance_relevance_web.app:create_app",
        host=settings.grf_host,
        port=settings.grf_port,
        factory=True,
    )


if __name__ == "__main__":
    main()
