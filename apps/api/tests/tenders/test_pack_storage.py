import asyncio
from uuid import uuid4
import httpx
import pytest
from app.tenders.storage import SourceStorage
from app.tenders.documents import MIME_TYPES
from app.tenders.policy import DomainError


def test_private_object_paths_support_all_validated_formats_and_reject_paths():
    storage=SourceStorage.__new__(SourceStorage)
    stem=f'{uuid4()}/{uuid4()}/'+('a'*64)
    for suffix in MIME_TYPES:
        assert storage.object_path(stem+suffix).endswith(stem+suffix)
    for bad in (stem+'.exe',stem+'.pdf/extra','../'+stem+'.xlsx'):
        with pytest.raises(DomainError):storage.object_path(bad)


def test_existing_private_bucket_gets_format_allowlist_without_becoming_public():
    storage=SourceStorage.__new__(SourceStorage)
    calls=[]
    current={'public':False,'allowed_mime_types':['application/pdf'],'file_size_limit':20*1024*1024}
    async def request(method,path,**kwargs):
        calls.append((method,kwargs))
        if method=='PUT':current.update(kwargs['json'])
        return httpx.Response(200,json=current)
    storage.request=request
    asyncio.run(storage.ensure_bucket())
    assert any(method=='PUT' for method,_ in calls)
    assert set(current['allowed_mime_types'])==set(MIME_TYPES.values())
    assert current['public'] is False
