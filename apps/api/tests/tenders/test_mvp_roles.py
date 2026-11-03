import asyncio
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.tenders.models import ActorContext
from app.tenders.policy import DomainError
from app.tenders.repository import Repository

class Membership:
    def __init__(self, roles): self.roles = roles
    async def fetchval(self, *args): return self.roles

@pytest.mark.parametrize('role', ['member', 'admin', 'viewer'])
def test_mvp_access_levels(role):
    assert ActorContext(user_id=uuid4(), workspace_id=uuid4(), roles={role}).roles == {role}

@pytest.mark.parametrize('role', ['bid_owner', 'service_reviewer', 'approver'])
def test_business_responsibilities_are_not_workspace_roles(role):
    with pytest.raises(ValidationError):
        ActorContext(user_id=uuid4(), workspace_id=uuid4(), roles={role})

@pytest.mark.parametrize('roles,required,allowed', [(['admin'],'member',True), (['member'],'member',True), (['viewer'],'member',False), (['member'],'admin',False), (None,'member',False)])
def test_database_membership_controls_access(roles, required, allowed):
    actor=ActorContext(user_id=uuid4(),workspace_id=uuid4(),roles={'admin'})
    call=Repository(None)._member(Membership(roles),actor,required)
    if allowed: asyncio.run(call)
    else:
        with pytest.raises(DomainError): asyncio.run(call)
