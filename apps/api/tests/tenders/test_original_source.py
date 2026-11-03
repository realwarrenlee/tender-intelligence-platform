import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4


def test_original_source_checks_access_and_returns_private_bytes():
    from app.tenders.routes import get_original_source

    version = uuid4()
    actor = object()
    repository = SimpleNamespace(get_source=AsyncMock(return_value={
        'storage_key': 'protected-key',
        'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'filename': 'source.docx',
    }))
    storage = SimpleNamespace(get=AsyncMock(return_value=b'original file'))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=repository, storage=storage)))

    response = asyncio.run(get_original_source(version, request, actor))

    repository.get_source.assert_awaited_once_with(actor, version)
    storage.get.assert_awaited_once_with('protected-key')
    assert response.body == b'original file'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
