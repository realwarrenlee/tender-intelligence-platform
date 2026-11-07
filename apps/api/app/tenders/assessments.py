import json
from uuid import uuid4

from app.tenders.documents import docx_bytes, parse_isolated
from app.tenders.policy import DomainError


# Browser reads need the public view, not the recursive private analysis context.
ASSESSMENT_VIEW_COLUMNS = """id,tender_id,input_revision,created_by,created_at,
    jsonb_build_object('evidence_revision',coalesce(manifest->'evidence_revision','0'::jsonb)) AS manifest,
    payload - 'context' AS payload"""


async def current_company(connection,workspace_id):
    return await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND kind='company_evidence' ORDER BY created_at DESC,id DESC LIMIT 1",workspace_id)


def company_profile(payload):
    profile=payload.get('profile')
    if not profile or 'content' in profile: return profile
    # Preserve versions saved before Company became one editable document.
    sections=[('Overview','overview'),('Capabilities and registrations','capabilities'),('Track record','track_record'),('Team knowledge','notes')]
    content='# CBM Pte. Ltd.\n\n'+'\n\n'.join('## '+heading+'\n\n'+profile.get(key,'') for heading,key in sections)
    return {'content':content,'sources':profile.get('sources',[])}


def evidence_view(row,revision,include_content=True):
    if row is None: return None
    payload=json.loads(row['payload'])
    return {'id':str(row['id']),'evidence_revision':revision,'created_by':str(row['created_by']),
        'created_at':row['created_at'].isoformat(),
        **{key:payload[key] for key in ('effective_on','expires_on','reason')},
        'filename':payload['document']['filename'],
        'profile':company_profile(payload) if include_content else None,
        'reference_text':'\n\n'.join(anchor['text'] for anchor in payload['parsed']['anchors']) if include_content and not payload.get('profile') else None}


async def get_company(repository,actor):
    async with repository.pool.acquire() as connection,connection.transaction(isolation='repeatable_read'):
        await repository._member(connection,actor)
        revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1',actor.workspace_id)
        rows=await connection.fetch("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND kind='company_evidence' ORDER BY created_at DESC,id DESC LIMIT 20",actor.workspace_id)
        return {'schema_version':'m1.v1','evidence_revision':revision,'current':evidence_view(rows[0],revision) if rows else None,
                'history':[evidence_view(row,revision-index,False) for index,row in enumerate(rows)]}


async def get_company_version(repository,actor,version_id):
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor)
        row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind='company_evidence'",actor.workspace_id,version_id)
        if row is None: raise DomainError(404,'NOT_FOUND','Company version not found.')
        revision=json.loads(row['payload'])['expected_evidence_revision']+1
        return evidence_view(row,revision)


def profile_document(profile):
    from docx import Document
    document=Document()
    for line in profile.content.splitlines():
        if line.strip(): document.add_paragraph(line)
    if profile.sources: document.add_paragraph('Sources')
    for source in profile.sources:
        document.add_paragraph(f'{source.title} | {source.publisher} | Checked {source.checked_on.isoformat()} | {source.url}')
    return docx_bytes(document)


async def accept_company(repository,actor,command,file_info,data,storage):
    if command.expires_on and command.expires_on<command.effective_on:
        raise DomainError(422,'INVALID_EVIDENCE_DATES','Evidence expiry must not precede its effective date.')
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'admin')
        # Include bytes in the request digest without accepting a client-supplied hash.
        identity=command.model_dump(mode='json')
        from app.tenders.models import EvidenceRegistration
        digest=EvidenceRegistration(client_request_id=command.client_request_id,body={**identity,**file_info})
        replay=await repository._claim(connection,actor,'accept_company_evidence',digest)
        if replay is not None: return replay
        revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1 FOR UPDATE',actor.workspace_id)
        if revision!=command.expected_evidence_revision: raise DomainError(409,'STALE_EVIDENCE','Accepted company evidence changed; refresh before accepting.')
        version=uuid4()
        source={**file_info,'id':str(version),'role':'company_evidence',
            'storage_key':f"{actor.workspace_id}/{version}/{file_info['sha256']}"+('.pdf' if file_info['content_type']=='application/pdf' else '.docx')}
        parsed=await parse_isolated(source,data,120)
        if parsed['status']!='complete': raise DomainError(422,'SOURCE_INCOMPLETE','Company evidence must have complete supported source coverage before acceptance.')
        await storage.put(source['storage_key'],data,source['content_type'])
        payload={**command.model_dump(mode='json'),'document':source,'parsed':parsed}
        await connection.execute("INSERT INTO m1_app.artifact_versions(id,workspace_id,kind,manifest,payload,created_by) VALUES($1,$2,'company_evidence',$3::jsonb,$4::jsonb,$5)",version,actor.workspace_id,json.dumps({'sha256':source['sha256']}),json.dumps(payload),actor.user_id)
        await connection.execute('UPDATE m1_app.workspaces SET evidence_revision=evidence_revision+1 WHERE id=$1',actor.workspace_id)
        await connection.execute('UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE workspace_id=$1 AND deleted_at IS NULL',actor.workspace_id)
        result={'schema_version':'m1.v1','id':str(version),'evidence_revision':revision+1}
        return await repository._finish(connection,actor,'accept_company_evidence',digest,result)


def assessment_view(row,current_revision,evidence_revision):
    if row is None: return None
    payload=json.loads(row['payload'])
    manifest=json.loads(row['manifest'])
    return {'id':str(row['id']),'input_revision':row['input_revision'],'created_by':str(row['created_by']),
        'is_current':row['input_revision']==current_revision and manifest.get('evidence_revision',0)==evidence_revision,
        **{key:payload.get(key) for key in ('candidate','requirements','blockers','reconciliation','manual_corrections','run','human_reason')}}


async def get_assessment(repository,actor,version_id):
    async with repository.pool.acquire() as connection,connection.transaction(isolation='repeatable_read'):
        await repository._member(connection,actor)
        row=await connection.fetchrow(f"SELECT {ASSESSMENT_VIEW_COLUMNS} FROM m1_app.artifact_versions WHERE workspace_id=$1 AND id=$2 AND kind='assessment'",actor.workspace_id,version_id)
        if row is None: raise DomainError(404,'NOT_FOUND','Assessment not found.')
        tender=await repository._tender(connection,actor,row['tender_id'])
        evidence_revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1',actor.workspace_id)
        latest=await connection.fetchval("SELECT id FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,row['tender_id'])
        view=assessment_view(row,tender['input_revision'],evidence_revision)
        view['is_current'] &= row['id']==latest
        return {'schema_version':'m1.v1',**view}
