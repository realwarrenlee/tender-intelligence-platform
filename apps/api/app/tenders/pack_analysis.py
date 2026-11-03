"""Partition every native source anchor and merge source-bound findings."""
import asyncio
from copy import deepcopy
import hashlib
import json

from app.tenders.policy import DomainError

MAX_PART_CHARS = 600000
MAX_PARTS = 64
MAX_NARRATIVE_CHARS = 100000
MAX_PART_ANCHORS = 2000


def partition_context(context, max_chars=MAX_PART_CHARS, max_parts=MAX_PARTS):
    shared = {k:v for k,v in context['source_anchors'].items()
              if v['source_role'] in ('company_evidence','review_answer')}
    available = max_chars - sum(len(a['text']) for a in shared.values())
    if available < 1:
        raise DomainError(422,'ANALYSIS_EVIDENCE_LIMIT','Shared company/reviewer evidence exceeds the bounded analysis context.')
    chunks, current, size = [], {}, 0
    # Dense prose needs smaller output-bounded parts; catalogues retain larger parts.
    anchors=[(k,a) for k,a in context['source_anchors'].items() if k not in shared]
    schedule=lambda a:(a.get('filename') or '').lower().endswith('.xlsx')
    anchors.sort(key=lambda item:schedule(item[1]))
    previous_class=None
    for key,anchor in anchors:
        source_class='schedule' if schedule(anchor) else 'qualification'
        capacity=available if source_class=='schedule' else min(available,MAX_NARRATIVE_CHARS)
        if current and source_class!=previous_class:
            chunks.append(current)
            current,size={},0
        previous_class=source_class
        text = anchor['text']
        offset = 0
        while offset < len(text):
            if size == capacity or len(current) >= MAX_PART_ANCHORS:
                chunks.append(current)
                current, size = {}, 0
            length = min(len(text)-offset, capacity-size)
            current[key] = {**anchor, 'text':text[offset:offset+length]}
            offset += length
            size += length
            if offset < len(text):
                chunks.append(current)
                current, size = {}, 0
        if len(chunks) >= max_parts and current:
            raise DomainError(422,'ANALYSIS_PART_LIMIT','The complete source text exceeds the bounded analysis part limit; no text was discarded.')
    if current:
        chunks.append(current)
    if not chunks or len(chunks) > max_parts:
        raise DomainError(422,'ANALYSIS_PART_LIMIT','The source text is empty or exceeds the bounded analysis part limit.')
    parts = []
    for index,anchors in enumerate(chunks):
        part = {**context, 'source_anchors':{**shared,**anchors},
                'source_complete':context['source_complete'], 'previous_assessment':None,
                'analysis_part':{'index':index,'total':len(chunks)}}
        parts.append(part)
    return parts


def merge_candidates(candidates, context):
    from app.tenders.analysis import requirement_identity
    result = {'summary':'', 'key_facts':{k:{'value':None,'citations':[]} for k in candidates[0]['key_facts']},
              'requirements':[], 'review_requests':[], 'warnings':[],
              'recommendation':{'decision':'hold','reasons':['Review the source-bound findings and outstanding evidence.'],'condition_refs':[]}}
    identities, conflicted, questions, warnings = {}, set(), set(), set()
    def warn(value):
        key = json.dumps(value,sort_keys=True)
        if key not in warnings:
            result['warnings'].append(value)
            warnings.add(key)
    for candidate in candidates:
        refs = {}
        for req in candidate['requirements']:
            identity = requirement_identity(req)
            if identity not in identities:
                value = deepcopy(req)
                value['local_ref'] = 'R'+str(len(identities)+1)
                identities[identity] = value
                result['requirements'].append(value)
            else:
                value = identities[identity]
                mandatory_conflict=value['mandatory'] != req['mandatory']
                value['mandatory'] = value['mandatory'] or req['mandatory']
                if req['status'] != value['status'] or mandatory_conflict:
                    value.update(status='unconfirmed', missing_information='Conflicting findings across source sections need review.',
                                 explanation='The sections produced different findings for the same cited obligation.')
            refs[req['local_ref']] = value['local_ref']
        for name,fact in candidate['key_facts'].items():
            if fact['value'] is None or name in conflicted:
                continue
            old = result['key_facts'][name]
            if old['value'] is None:
                result['key_facts'][name] = deepcopy(fact)
            elif str(old['value']).strip().casefold() != str(fact['value']).strip().casefold():
                warn({'code':'conflicting_dates' if name in ('closing_at','service_start_on','term_months') else 'missing_fact',
                      'message':'Different source sections give conflicting values for '+name+'. Review the original clauses and amendments.',
                      'citations':(old['citations']+fact['citations'])[:12]})
                result['key_facts'][name] = {'value':None,'citations':[]}
                conflicted.add(name)
        for draft in candidate['review_requests']:
            mapped = list(dict.fromkeys(refs[r] for r in draft['requirement_refs']))
            key = (tuple(sorted(mapped)), ' '.join(draft['question'].split()).casefold())
            if key not in questions:
                result['review_requests'].append({**deepcopy(draft),'draft_ref':'Q'+str(len(questions)+1),'requirement_refs':mapped})
                questions.add(key)
        for warning in candidate['warnings']:
            warn(deepcopy(warning))
    if len(result['requirements']) > 1000 or len(result['review_requests']) > 1000 or len(result['warnings']) > 1000:
        raise DomainError(422,'ASSESSMENT_RESULT_LIMIT','The complete merged findings exceed the review result limit; findings were not discarded.')
    unresolved = [r for r in result['requirements'] if r['mandatory'] and r['kind'] in ('eligibility','delivery') and r['status']!='met']
    result['recommendation']['condition_refs'] = [r['local_ref'] for r in unresolved]
    if any(r['status']=='unmet' for r in unresolved):
        result['recommendation'].update(decision='decline',reasons=['A mandatory qualification has an evidenced failure.'])
    result['summary'] = f"Reviewed {len(result['requirements'])} requirements across {len(candidates)} source sections. " + (
        f"{len(unresolved)} mandatory qualification or delivery checks need attention." if unresolved else 'Review source coverage and the human decision before proceeding.')
    return result


async def analyse_pack(context, model, ledger=None, progress=None):
    from app.tenders.analysis import analyse, validate_candidate
    parts = partition_context(context)
    outputs, runs = [], []
    async def run_part(index):
        part_ledger=ledger.for_part(index+1) if ledger else None
        return await analyse(parts[index],model,part_ledger)
    for offset in range(0,len(parts),2):
        if progress:
            await progress(offset,len(parts))
        pair=await asyncio.gather(*(run_part(i) for i in range(offset,min(offset+2,len(parts)))),return_exceptions=True)
        for result in pair:
            if isinstance(result,BaseException):
                raise result
            outputs.append(result['candidate'])
            runs.append(result['run'])
    candidate = merge_candidates(outputs,context)
    result = validate_candidate(candidate,context)
    if candidate['recommendation']['decision']=='hold' and not result['blockers']:
        candidate['recommendation'].update(decision='pursue',reasons=['The assessed mandatory qualifications are supported by cited evidence.'])
        result = validate_candidate(candidate,context)
    result['run'] = {'parts':len(parts),'calls':sum(r['calls'] for r in runs),
                     'total_tokens':sum(r['total_tokens'] for r in runs),'model':runs[-1]['model'],
                     'part_runs':runs,'input_sha256':hashlib.sha256(json.dumps(context['source_anchors'],sort_keys=True).encode()).hexdigest()}
    if progress:
        await progress(len(parts),len(parts))
    return result
