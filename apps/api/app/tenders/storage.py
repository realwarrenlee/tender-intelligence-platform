"""Server-only private Supabase Storage; immutable, server-generated object paths."""
import asyncio
import hashlib
import re

import httpx

from app.config import get_settings
from app.tenders.policy import DomainError
from app.tenders.documents import MIME_TYPES,MAX_FILE

BUCKET = 'm1-sources-v1'


class SourceStorage:
    def __init__(self,client):
        settings = get_settings()
        self.client = client
        self.base = settings.supabase_url.rstrip('/')+'/storage/v1'
        secret = settings.supabase_secret_key.get_secret_value()
        self.headers = {'apikey':secret,'Authorization':f'Bearer {secret}'}

    async def request(self,method,path,**kwargs):
        try:
            response = await self.client.request(method,self.base+path,headers={**self.headers,**kwargs.pop('headers',{})},timeout=60,**kwargs)
        except httpx.HTTPError:
            raise DomainError(503,'STORAGE_UNAVAILABLE','Source storage is temporarily unavailable.') from None
        return response

    async def ensure_bucket(self):
        response = await self.request('GET',f'/bucket/{BUCKET}')
        if response.status_code == 404 or (response.status_code == 400 and response.json().get('code') == 'NoSuchBucket'):
            response = await self.request('POST','/bucket',json={'id':BUCKET,'name':BUCKET,'public':False,
                'file_size_limit':20*1024*1024,'allowed_mime_types':list(MIME_TYPES.values())})
            if response.status_code not in (200,201):
                raise DomainError(503,'STORAGE_SETUP_FAILED','Could not create the private source bucket.')
            response = await self.request('GET',f'/bucket/{BUCKET}')
        if response.status_code != 200 or response.json().get('public') is not False:
            raise DomainError(503,'STORAGE_SETUP_FAILED','The source bucket must exist and be private.')
        if set(response.json().get('allowed_mime_types') or [])!=set(MIME_TYPES.values()) or response.json().get('file_size_limit')!=MAX_FILE:
            updated=await self.request('PUT',f'/bucket/{BUCKET}',json={'public':False,'file_size_limit':MAX_FILE,'allowed_mime_types':list(MIME_TYPES.values())})
            if updated.status_code not in (200,201):
                raise DomainError(503,'STORAGE_SETUP_FAILED','Could not configure validated source formats.')
            verified=await self.request('GET',f'/bucket/{BUCKET}')
            if verified.status_code!=200 or verified.json().get('public') is not False or set(verified.json().get('allowed_mime_types') or [])!=set(MIME_TYPES.values()):
                raise DomainError(503,'STORAGE_SETUP_FAILED','Private source format configuration was not verified.')

    def object_path(self,key):
        if not re.fullmatch(r'[0-9a-f-]{36}/[0-9a-f-]{36}/(?:preparation/|submission/)?[0-9a-f]{64}\.(pdf|docx|doc|xlsx|pptx)',key):
            raise DomainError(422,'INVALID_STORAGE_KEY','The source storage path is invalid.')
        return f'/object/{BUCKET}/{key}'

    async def put(self,key,data,content_type):
        response = await self.request('POST',self.object_path(key),content=data,
            headers={'Content-Type':content_type,'x-upsert':'false'})
        if response.status_code in (200,201):
            return
        if response.status_code in (400,409) and await self.get(key) == data:
            return
        raise DomainError(503,'STORAGE_UNAVAILABLE','Could not preserve the immutable source.')

    async def get(self,key):
        response = await self.request('GET',self.object_path(key))
        if response.status_code != 200:
            raise DomainError(503,'SOURCE_UNAVAILABLE','The pinned source is temporarily unavailable.')
        data = response.content
        digest = key.rsplit('/',1)[-1].split('.')[0]
        if len(data)>20*1024*1024 or hashlib.sha256(data).hexdigest()!=digest:
            raise DomainError(422,'SOURCE_HASH_MISMATCH','Stored source bytes do not match the pinned hash.')
        return data


async def setup():
    async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
        await SourceStorage(client).ensure_bucket()


if __name__ == '__main__':
    asyncio.run(setup())
    print('Private M1 source bucket verified.')
