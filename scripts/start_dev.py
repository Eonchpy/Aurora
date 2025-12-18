import uvicorn

from aurora_api.config import get_settings


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "aurora_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        factory=False,
    )
