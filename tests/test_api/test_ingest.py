from uuid import uuid4

from fastapi.testclient import TestClient

import aurora_api.main as main
from aurora_api.api import ingest as ingest_api
from aurora_api.services.document import DocumentService
from aurora_api.database import get_session


class StubDoc:
    def __init__(self):
        self.id = uuid4()
        self.namespace = "default"


def test_ingest_stub(monkeypatch):
    async def stub_ingest(self, payload):
        return StubDoc()

    async def override_session():
        class DummySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        yield DummySession()

    monkeypatch.setattr(DocumentService, "ingest", stub_ingest)
    main.app.dependency_overrides[get_session] = override_session

    client = TestClient(main.app)
    resp = client.post(
        "/ingest",
        json={
            "content": "hello",
            "document_type": "document",
            "source": "test",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ingested"
    assert data["namespace"] == "default"
    assert data["embedding_dimension"] == main.settings.embedding_dimension

    main.app.dependency_overrides.clear()
