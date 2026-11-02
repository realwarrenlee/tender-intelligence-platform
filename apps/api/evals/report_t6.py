"""Grade completed fictional UI outputs; never included in a model context."""
import json
import shutil

from app.config import ROOT


def citations(value):
    if isinstance(value,dict):
        if set(value)=={'anchor_id','quote'}: yield value
        for child in value.values(): yield from citations(child)
    elif isinstance(value,list):
        for child in value: yield from citations(child)


def report():
    state=json.loads((ROOT/'evals/runs/local/t6-ui-state.json').read_text())
    key=json.loads((ROOT/'evals/answer-keys/D1-qualification.json').read_text())
    by_label={s['label']:s['view'] for s in state['stages']}
    stages=[]
    for name,label in [('initial','t6-initial'),('answered','t6-answered-final'),('amended','t6-amended')]:
        view=by_label[label]
        assessment=view['assessment']
        expected=next(s for s in key['stages'] if s['name']==name)
        candidate=assessment['candidate']
        current=[r['requirement'] for r in assessment['requirements'] if not r['carried_forward']]
        staff=next(r for r in current if 'technicians' in r['text'])
        matched={}
        for field,value in key['initial_facts'].items():
            if field=='briefing_at': continue
            expected_value=expected['closing_at'] if field=='closing_at' else value
            matched[field]=candidate['key_facts'][field]['value']==expected_value
        cites=list(citations(candidate))
        stages.append({'stage':name,'assessment_version_id':assessment['id'],'input_revision':view['input_revision'],
            'current_at_capture':assessment['is_current'],'recommendation':candidate['recommendation']['decision'],
            'expected_recommendation':expected['recommendation'],'recommendation_matches':candidate['recommendation']['decision']==expected['recommendation'],
            'staffing_status':staff['status'],'staffing_status_matches':staff['status']==expected['r4_status'],
            'key_fact_matches':matched,'candidate_requirements':len(candidate['requirements']),
            'server_validated_citation_occurrences':len(cites),'unique_server_validated_citations':len({(c['anchor_id'],c['quote']) for c in cites}),
            'blockers':assessment['blockers'],'run':assessment['run']})
    unreadable=by_label['t6-unreadable']
    ledger=json.loads((ROOT/'evals/runs/m1-t6-live-ledger.json').read_text())
    unreadable_jobs=[j for j in ledger['jobs'] if j['tender_id']==unreadable['id']]
    assert unreadable_jobs and all(not j['provider_calls'] for j in unreadable_jobs)
    summary={'fixture':'D1-qualification','date':'2026-10-24','execution':'Real password-form Auth, visible UI writes, production HTTP/queue/parser/model/DB/Storage; read-only session snapshots.',
        'answer_key_was_model_input':False,'actual_clock':'24 October 2026 Asia/Singapore; fixture event identity/timestamps are not trusted.',
        'stages':stages,'recommendation_matches':sum(s['recommendation_matches'] for s in stages),
        'staffing_status_matches':sum(s['staffing_status_matches'] for s in stages),
        'key_fact_matches':sum(sum(s['key_fact_matches'].values()) for s in stages),
        'provider_requests':sum(len(j['provider_calls']) for j in ledger['jobs']),
        'reported_tokens':sum(c['usage'].get('total_tokens',0) for j in ledger['jobs'] for c in j['provider_calls']),
        'confirmed_review_tasks':len(by_label['t6-human-decision']['review_tasks']),
        'typed_answers':sum(t['answer'] is not None for t in by_label['t6-human-decision']['review_tasks']),
        'human_hold_was_current':by_label['t6-human-decision']['decision']['is_current'],
        'hold_non_current_immediately_after_upload':not by_label['t6-amendment-stale']['decision']['is_current'],
        'accepted_human_mappings':1,'rejected_missing_citation_attempts':1,
        'unreadable':{'status':unreadable['jobs'][0]['status'],'error':unreadable['jobs'][0]['error_code'],'assessment':unreadable['assessment'],'provider_requests':0},
        'anonymous_status':state['anonymous_status'],'foreign_read_statuses':state['access'],
        'development_sign_in_verified':state['development_sign_in_verified'],
        'extracted_page_view_verified':state['extracted_page_view_verified'],
        'historical_export_non_current':state['historical_export_non_current'],
        'fictional_accounts_and_workspaces_cleaned':True,
        'semantic_review':{'assessment_method':'Manual inspection of this recorded capture; not an automated semantic accuracy score.','key_requirement_groups_covered_each_stage':'6/6 (R5 split across method statement and mobilisation plan)',
            'initial_qualification_positives_supported':'3/3 eligibility findings; no Saturday-capacity inference from headcount',
            'additional_delivery_gaps':'planned maintenance, reactive fault response and service reporting retained; staffing answer does not prove these',
            'correction_effort':'One staffing amendment mapping accepted with all original/replacement quotes; one incomplete citation submission rejected. No finding forced to met or pursue.',
            'remaining':'Original answered pursue expectation remains a mismatch. D2/D3 and held-out/customer gates not run.'}}
    (ROOT/'evals/runs/m1-t6-live.json').write_text(json.dumps(summary,indent=2)+'\n')
    images=ROOT/'evals/runs/m1-t6'
    images.mkdir(exist_ok=True)
    for name in ('t6-source-final.png','t6-history-final.png','t6-human-decision.png','t6-amendment-stale.png','t6-unreadable.png'):
        shutil.copyfile(ROOT/'output/playwright'/name,images/name)
    print(json.dumps({k:summary[k] for k in ('provider_requests','reported_tokens','recommendation_matches','staffing_status_matches','key_fact_matches')}))


if __name__=='__main__':
    report()
