from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.tenders.models import ActorContext
from app.tenders.policy import DomainError

bearer = HTTPBearer(auto_error=False)


async def get_actor(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise DomainError(401,"UNAUTHENTICATED","A verified sign-in session is required.")
    settings = get_settings()
    try:
        response = await request.app.state.auth_client.get(
            settings.supabase_url.rstrip("/") + "/auth/v1/user",
            headers={"apikey":settings.supabase_secret_key.get_secret_value(),
                     "Authorization":"Bearer " + credentials.credentials},
        )
    except httpx.RequestError:
        raise DomainError(503,"AUTH_UNAVAILABLE","The sign-in service is temporarily unavailable.") from None
    if response.status_code != 200:
        if response.status_code in {400,401,403}:
            raise DomainError(401,"UNAUTHENTICATED","The sign-in session is invalid or expired.")
        raise DomainError(503,"AUTH_UNAVAILABLE","The sign-in service is temporarily unavailable.")
    try:
        user_id = UUID(response.json()["id"])
    except (ValueError,KeyError,TypeError):
        raise DomainError(503,"AUTH_UNAVAILABLE","The sign-in service returned an invalid response.") from None
    async with request.app.state.pool.acquire() as connection:
        rows = await connection.fetch("SELECT workspace_id,roles FROM m1_app.memberships WHERE user_id=$1 LIMIT 2",user_id)
    if len(rows) != 1:
        raise DomainError(403,"WORKSPACE_REQUIRED","Exactly one authorised workspace membership is required for this release.")
    return ActorContext(user_id=user_id,workspace_id=rows[0]["workspace_id"],roles=set(rows[0]["roles"]))
