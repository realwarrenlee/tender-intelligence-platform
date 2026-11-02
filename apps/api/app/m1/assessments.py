from copy import deepcopy
import json
from uuid import uuid4

from app.m1.analysis import validate_candidate,requirement_identity
from app.m1.analysis_runtime import utc_now
from app.m1.citations import citation_errors,normalise_quote
from app.m1.documents import parse_isolated
from app.m1.policy import DomainError


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
    import io
    import zipfile
    from docx import Document
    document=Document()
    for line in profile.content.splitlines():
        if line.strip(): document.add_paragraph(line)
    if profile.sources: document.add_paragraph('Sources')
    for source in profile.sources:
        document.add_paragraph(f'{source.title} | {source.publisher} | Checked {source.checked_on.isoformat()} | {source.url}')
    original=io.BytesIO()
    document.save(original)
    # Stable ZIP timestamps preserve request replay across interrupted saves.
    result=io.BytesIO()
    with zipfile.ZipFile(original) as archive,zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as stable:
        for name in sorted(archive.namelist()):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            stable.writestr(entry,archive.read(name))
    return result.getvalue()


async def accept_company(repository,actor,command,file_info,data,storage):
    if command.expires_on and command.expires_on<command.effective_on:
        raise DomainError(422,'INVALID_EVIDENCE_DATES','Evidence expiry must not precede its effective date.')
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'admin')
        # Include bytes in the request digest without accepting a client-supplied hash.
        identity=command.model_dump(mode='json')
        from app.m1.models import EvidenceRegistration
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


async def correct_assessment(repository,actor,tender_id,command):
    async with repository.pool.acquire() as connection,connection.transaction():
        await repository._member(connection,actor,'bid_owner')
        replay=await repository._claim(connection,actor,'correct_assessment:'+str(tender_id),command)
        if replay is not None: return replay
        evidence_revision=await connection.fetchval('SELECT evidence_revision FROM m1_app.workspaces WHERE id=$1 FOR SHARE',actor.workspace_id)
        tender=await repository._tender(connection,actor,tender_id,lock=True)
        row=await connection.fetchrow("SELECT * FROM m1_app.artifact_versions WHERE workspace_id=$1 AND tender_id=$2 AND kind='assessment' ORDER BY input_revision DESC,created_at DESC,id DESC LIMIT 1",actor.workspace_id,tender_id)
        if not row or row['id']!=command.expected_assessment_version_id or not assessment_view(row,tender['input_revision'],evidence_revision)['is_current']:
            raise DomainError(409,'STALE_ASSESSMENT','A current assessment version is required for correction.')
        previous=json.loads(row['payload'])
        candidate=deepcopy(previous['candidate'])
        candidate['recommendation']={'decision':'hold','reasons':['A human corrected this assessment; reassessment is required.'],'condition_refs':[]}
        by_id={r['id']:r for r in previous['requirements']}
        changes=[]
        edited=set()
        for edit in command.edits.requirements:
            if edit.requirement_id in edited or edit.requirement_id not in by_id: raise DomainError(422,'INVALID_CORRECTION','Correction references an unknown or duplicate requirement.')
            edited.add(edit.requirement_id)
            value={**by_id[edit.requirement_id]['requirement'],**edit.model_dump(mode='json',exclude={'requirement_id'})}
            found=False
            for index,requirement in enumerate(candidate['requirements']):
                if requirement_identity(requirement)==edit.requirement_id:
                    candidate['requirements'][index]=value
                    found=True
            if not found: candidate['requirements'].append(value)
            changes.append({'kind':'requirement','id':edit.requirement_id,'value':value})
        if command.edits.key_facts:
            for name in type(command.edits.key_facts).model_fields:
                fact=getattr(command.edits.key_facts,name)
                if fact is None: continue
                value=fact.model_dump(mode='json')
                candidate['key_facts'][name]=value
                changes.append({'kind':'fact','id':name,'value':value})
        prev=deepcopy(previous)
        prev['manual_corrections']=[c for c in prev.get('manual_corrections',[]) if not any(c['kind']==e['kind'] and c['id']==e['id'] for e in changes)]
        resolution_records=[]
        new_ids={requirement_identity(r):r for r in candidate['requirements']}
        pending=prev.get('reconciliation',[])
        for mapping in command.edits.reconciliations:
            prior=by_id.get(mapping.previous_requirement_id)
            targets=[new_ids.get(key) for key in mapping.replacement_requirement_ids]
            outstanding=[c for c in pending if c.get('requirement_id')==mapping.previous_requirement_id and not c.get('resolved')]
            cites=[c.model_dump() for c in mapping.citations]
            if not prior or not outstanding or any(r is None for r in targets) or citation_errors(cites,previous['context']['source_anchors'],{'tender','addendum'}):
                raise DomainError(422,'INVALID_RECONCILIATION','Reconciliation needs an outstanding change, existing replacements and valid tender citations.')
            old=next((c['previous_requirement'] for c in outstanding if c.get('previous_requirement')),prior['requirement'])
            # Require a shared source clause, not merely a quote elsewhere in the pack.
            # New addendum clauses can accompany that original clause; unrelated obligations cannot replace it.
            def overlaps(left,right):
                return left['anchor_id']==right['anchor_id'] and (normalise_quote(left['quote']) in normalise_quote(right['quote']) or normalise_quote(right['quote']) in normalise_quote(left['quote']))
            anchors=previous['context']['source_anchors']
            def related(left,right):
                target=anchors[right['anchor_id']]
                return overlaps(left,right) or (target['source_role']=='addendum' and target.get('amends_version_id')==anchors[left['anchor_id']]['document_version_id'])
            affected=old['tender_citations']+[c for r in targets for c in r['tender_citations']]
            if any(not any(overlaps(c,e) for e in cites) for c in affected) or any(not any(related(a,b) for a in old['tender_citations'] for b in r['tender_citations']) for r in targets):
                raise DomainError(422,'INVALID_RECONCILIATION','Mappings must cite affected original/replacement clauses and retain a shared clause or a registered amendment relationship.')
            if old['mandatory'] and old['kind'] in ('eligibility','delivery') and any(not r['mandatory'] or r['kind'] not in ('eligibility','delivery') for r in targets):
                raise DomainError(422,'INVALID_RECONCILIATION','A mandatory qualification obligation cannot be downgraded through replacement.')
            if old['status'] in ('unconfirmed','unmet') and mapping.previous_requirement_id not in edited and any(r['status']=='met' for r in targets):
                raise DomainError(422,'INVALID_RECONCILIATION','Resolve the original finding explicitly before replacing it with a met finding.')
            resolved_ids={mapping.previous_requirement_id,*mapping.replacement_requirement_ids}
            for change in pending:
                if change.get('requirement_id') in resolved_ids: change['resolved']=True
            prev['requirements']=[r for r in prev['requirements'] if r['id']!=mapping.previous_requirement_id]
            # Seed accepted targets so validation does not recreate additions/changes.
            for key in mapping.replacement_requirement_ids:
                prev['requirements']=[r for r in prev['requirements'] if r['id']!=key]
                prev['requirements'].append({'id':key,'requirement':deepcopy(new_ids[key]),'carried_forward':False})
            resolution_records.append(mapping.model_dump(mode='json'))
        for change in pending:
            if change['kind']=='manual_correction_conflict' and any((edit['kind']=='requirement' and edit['id']==change.get('requirement_id')) or (edit['kind']=='fact' and edit['id']==change.get('fact_id')) for edit in changes):
                change['resolved']=True
        if not changes and not resolution_records: raise DomainError(422,'EMPTY_CORRECTION','Supply a fact, finding or source-backed reconciliation change.')
        context={**previous['context'],'previous_assessment':prev,'as_of':utc_now().isoformat(),'input_revision':tender['input_revision']+1}
        # Human corrections are explicit judgements; the same strict source/schema rules still apply.
        result=validate_candidate(candidate,context,human_correction=True)
        result['manual_corrections']+=changes
        result['human_reason']=command.reason
        result['reconciliation_resolutions']=previous.get('reconciliation_resolutions',[])+resolution_records
        result['run']=previous.get('run')
        revision=await connection.fetchval('UPDATE m1_app.tenders SET input_revision=input_revision+1 WHERE id=$1 RETURNING input_revision',tender_id)
        manifest=json.loads(row['manifest'])
        manifest['correction_of']=str(row['id'])
        inserted=await connection.fetchrow("INSERT INTO m1_app.artifact_versions(workspace_id,tender_id,kind,input_revision,manifest,payload,created_by) VALUES($1,$2,'assessment',$3,$4::jsonb,$5::jsonb,$6) RETURNING *",actor.workspace_id,tender_id,revision,json.dumps(manifest),json.dumps(result),actor.user_id)
        return await repository._finish(connection,actor,'correct_assessment',command,assessment_view(inserted,revision,evidence_revision))
