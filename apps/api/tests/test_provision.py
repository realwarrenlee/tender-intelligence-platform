import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app import provision as module


def test_database_failure_cannot_create_an_auth_orphan(tmp_path,monkeypatch):
    auth=AsyncMock()
    monkeypatch.setattr(module,'create_pool',AsyncMock(side_effect=RuntimeError('Database unavailable')))
    monkeypatch.setattr(module,'create_auth_user',auth)
    with pytest.raises(RuntimeError,match='Database unavailable'):
        asyncio.run(module.provision('fictional@example.invalid',tmp_path/'credentials.json'))
    auth.assert_not_called()


def test_output_failure_happens_before_auth_creation(tmp_path,monkeypatch):
    class Pool:
        async def close(self): pass
    monkeypatch.setattr(module,'create_pool',AsyncMock(return_value=Pool()))
    auth=AsyncMock()
    monkeypatch.setattr(module,'create_auth_user',auth)
    output=tmp_path/'directory'
    output.mkdir()
    with pytest.raises((OSError,ValueError)):
        asyncio.run(module.provision('fictional@example.invalid',output))
    auth.assert_not_called()


def test_post_auth_failure_keeps_credentials_for_only_that_account(tmp_path,monkeypatch):
    from uuid import uuid4
    user=str(uuid4())
    monkeypatch.setattr(module,'sign_in',AsyncMock(side_effect=RuntimeError('No saved account yet')))
    class Pool:
        def acquire(self): raise RuntimeError('Database interrupted after Auth')
        async def close(self): pass
    monkeypatch.setattr(module,'create_pool',AsyncMock(return_value=Pool()))
    monkeypatch.setattr(module,'create_auth_user',AsyncMock(return_value=user))
    output=tmp_path/'credentials.json'
    with pytest.raises(RuntimeError,match='Database interrupted'):
        asyncio.run(module.provision('fictional@example.invalid',output))
    saved=json.loads(output.read_text())
    assert saved['email']=='fictional@example.invalid' and saved['user_id']==user
    assert saved['password'] and saved['workspace_id']
    assert saved['status']=='auth_created'


def test_recovery_record_update_is_atomic_on_write_failure(tmp_path,monkeypatch):
    output=tmp_path/'credentials.json'
    saved={'email':'fictional@example.invalid','password':'local-test-password','status':'prepared'}
    module.save_record(output,saved,exclusive=True)
    monkeypatch.setattr(module.os,'fsync',lambda _: (_ for _ in ()).throw(OSError('Simulated disk failure')))
    with pytest.raises(OSError,match='Simulated disk failure'):
        module.save_record(output,{**saved,'status':'auth_created'})
    assert json.loads(output.read_text())==saved
    assert list(tmp_path.iterdir())==[output]
