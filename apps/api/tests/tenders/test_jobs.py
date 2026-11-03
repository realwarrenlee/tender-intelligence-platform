import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import threading
import subprocess
import sys

import pytest

from test_documents import create, upload

ROOT = Path(__file__).resolve().parents[4]


def jobs():
    assert (ROOT / 'apps/api/app/tenders/jobs.py').exists(), 'T2 job execution is missing'
    from app.tenders import jobs
    return jobs


def enqueue(http,tender,revision=2,key=None):
    return http.post(f"/api/v1/tenders/{tender['id']}/analyses",json={
        'expected_input_revision':revision,'client_request_id':key or str(uuid4())})


def run_job(http,app,job_id):
    # Execute the same business handler the real PgQueuer worker calls.
    return http.portal.call(jobs().run_analysis_job,app.state.pool,app.state.storage,UUID(job_id))


def test_job_pins_manifest_and_replays_after_effect_commit(client):
    module = jobs()
    http,current,app = client
    tender = create(http)
    uploaded = upload(http,tender)
    assert uploaded.status_code == 201
    key = str(uuid4())
    first = enqueue(http,tender,key=key)
    assert first.status_code == 202, first.text
    assert enqueue(http,tender,key=key).json() == first.json()
    job_id = first.json()['id']
    run_job(http,app,job_id)
    result = http.get(f'/api/v1/jobs/{job_id}').json()
    assert result['status'] == 'needs_input'
    assert result['error_code'] == 'PARSING_ONLY'
    assert result['completed_stages'] == ['source_manifest','parsing']
    assert result['output_version_id'] is not None
    assert result['attempt'] == 1
    run_job(http,app,job_id)
    replay = http.get(f'/api/v1/jobs/{job_id}').json()
    assert replay['output_version_id'] == result['output_version_id']
    assert replay['attempt'] == 1
    async def inspect():
        async with app.state.pool.acquire() as connection:
            payload = json.loads(await connection.fetchval('SELECT payload FROM m1_app.artifact_versions WHERE id=$1',UUID(result['output_version_id'])))
            assert payload['complete']
            assert len(payload['documents'][0]['anchors']) == 2
            assert await connection.fetchval('SELECT count(*) FROM m1_queue.pgqueuer WHERE dedupe_key=$1',job_id) == 1
    http.portal.call(inspect)
    assert http.get(f"/api/v1/tenders/{tender['id']}").json()['assessment'] is None


def test_cancel_and_stale_jobs_cannot_publish_current_result(client,monkeypatch):
    module = jobs()
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    cancelled = enqueue(http,tender).json()['id']
    response = http.post(f'/api/v1/jobs/{cancelled}/cancel',json={
        'expected_input_revision':2,'client_request_id':str(uuid4())})
    assert response.status_code == 200, response.text
    run_job(http,app,cancelled)
    assert http.get(f'/api/v1/jobs/{cancelled}').json()['status'] == 'cancelled'
    stale = enqueue(http,tender).json()['id']
    assert upload(http,tender,revision=2).status_code == 201
    run_job(http,app,stale)
    assert http.get(f'/api/v1/jobs/{stale}').json()['status'] == 'non_current'


def test_empty_pack_and_foreign_job_are_rejected(client,actors):
    jobs()
    http,current,_ = client
    tender = create(http)
    response = enqueue(http,tender,revision=1)
    assert response.status_code == 422
    assert response.json()['code'] == 'NO_SOURCES'
    assert upload(http,tender).status_code == 201
    job_id = enqueue(http,tender).json()['id']
    current[0] = actors['other']
    assert http.get(f'/api/v1/jobs/{job_id}').status_code == 404
    assert http.post(f'/api/v1/jobs/{job_id}/cancel',json={
        'expected_input_revision':2,'client_request_id':str(uuid4())}).status_code == 404


def test_failed_parser_is_visible_and_does_not_remove_earlier_output(client,monkeypatch):
    module = jobs()
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    first = enqueue(http,tender).json()['id']
    run_job(http,app,first)
    previous = http.get(f'/api/v1/jobs/{first}').json()['output_version_id']
    async def broken(*args,**kwargs):
        raise TimeoutError('Fictional parser timeout')
    monkeypatch.setattr(module,'parse_isolated',broken)
    failed = enqueue(http,tender).json()['id']
    run_job(http,app,failed)
    result = http.get(f'/api/v1/jobs/{failed}').json()
    assert result['status'] == 'failed'
    assert result['error_code'] == 'PARSER_TIMEOUT'
    assert http.get(f'/api/v1/jobs/{first}').json()['output_version_id'] == previous


@pytest.mark.parametrize('change',['cancel','amend','duplicate'])
def test_late_parser_result_is_fenced(client,monkeypatch,change):
    module = jobs()
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    job_id = enqueue(http,tender).json()['id']
    entered,release = threading.Event(),threading.Event()
    calls = []
    async def controlled(source,*args):
        number = len(calls)+1
        calls.append(number)
        if number == 1:
            entered.set()
            await asyncio.to_thread(release.wait,20)
        return {'document_version_id':source['id'],'source_role':'tender','sha256':source['sha256'],
            'status':'complete','error_code':None,'locations':[{'page':1,'status':'complete'},{'page':2,'status':'complete'}],
            'anchors':[{'page':1,'text':f'Fictional attempt {number}'}]}
    monkeypatch.setattr(module,'parse_isolated',controlled)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_job,http,app,job_id)
        try:
            assert entered.wait(10)
            if change == 'cancel':
                assert http.post(f'/api/v1/jobs/{job_id}/cancel',json={'expected_input_revision':2,'client_request_id':str(uuid4())}).status_code == 200
            elif change == 'amend':
                assert upload(http,tender,revision=2).status_code == 201
            else:
                run_job(http,app,job_id)
        finally:
            release.set()
        future.result(timeout=20)
    result = http.get(f'/api/v1/jobs/{job_id}').json()
    if change == 'cancel':
        assert result['status'] == 'cancelled'
        assert result['output_version_id'] is None
    elif change == 'amend':
        assert result['status'] == 'non_current'
    else:
        async def inspect():
            async with app.state.pool.acquire() as connection:
                assert await connection.fetchval("SELECT count(*) FROM m1_app.artifact_versions WHERE tender_id=$1 AND kind='parsed_sources'",UUID(tender['id'])) == 1
                payload = json.loads(await connection.fetchval('SELECT payload FROM m1_app.artifact_versions WHERE id=$1',UUID(result['output_version_id'])))
                assert payload['documents'][0]['anchors'][0]['text'] == 'Fictional attempt 2'
        http.portal.call(inspect)


def test_worker_adapter_retries_database_disconnect_then_marks_failed(client,monkeypatch):
    module = jobs()
    assert hasattr(module,'execute_queued_job'), 'Queue adapter does not recover business-database disconnects'
    from types import SimpleNamespace
    import asyncpg
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    job_id = enqueue(http,tender).json()['id']
    async def disconnected(*args):
        raise asyncpg.ConnectionDoesNotExistError('Fictional connection drop')
    monkeypatch.setattr(module,'run_analysis_job',disconnected)
    for attempt in (0,1):
        with pytest.raises(module.RetryRequested):
            http.portal.call(module.execute_queued_job,app.state.pool,app.state.storage,
                SimpleNamespace(payload=json.dumps({'job_id':job_id}).encode(),attempts=attempt))
    http.portal.call(module.execute_queued_job,app.state.pool,app.state.storage,
        SimpleNamespace(payload=json.dumps({'job_id':job_id}).encode(),attempts=2))
    result = http.get(f'/api/v1/jobs/{job_id}').json()
    assert result['status'] == 'failed'
    assert result['error_code'] == 'DATABASE_UNAVAILABLE'


def test_final_status_write_failure_keeps_dispatch_recoverable():
    module = jobs()
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    class UnavailablePool:
        @asynccontextmanager
        async def acquire(self):
            raise ConnectionError('Fictional business-pool outage')
            yield
    queued = SimpleNamespace(payload=json.dumps({'job_id':str(uuid4())}).encode(),attempts=2)
    with pytest.raises(module.RetryRequested):
        asyncio.run(module.execute_queued_job(UnavailablePool(),None,queued))


def test_finalization_recovery_does_not_restart_parsing(client,monkeypatch):
    module = jobs()
    from types import SimpleNamespace
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    job_id = enqueue(http,tender).json()['id']
    calls = []
    async def exhausted(*args):
        calls.append(1)
        raise ConnectionError('Fictional disconnect')
    monkeypatch.setattr(module,'run_analysis_job',exhausted)
    http.portal.call(module.execute_queued_job,app.state.pool,app.state.storage,
        SimpleNamespace(payload=json.dumps({'job_id':job_id}).encode(),attempts=3))
    assert calls == []
    assert http.get(f'/api/v1/jobs/{job_id}').json()['status'] == 'failed'


def test_failed_docx_rerun_preserves_readable_paragraph_view(client,monkeypatch):
    module = jobs()
    from docx import Document
    import io
    from app.tenders.documents import DOCX_MIME
    from app.tenders.policy import DomainError
    http,_,app = client
    tender = create(http)
    doc = Document()
    doc.add_paragraph('Fictional enduring requirement')
    stream = io.BytesIO()
    doc.save(stream)
    response = upload(http,tender,files=[('source.docx',stream.getvalue(),DOCX_MIME)])
    assert response.status_code == 201
    version = response.json()['document_version_ids'][0]
    first = enqueue(http,tender).json()['id']
    run_job(http,app,first)
    before = http.get(f'/api/v1/sources/{version}').json()
    assert before['anchors'][0]['text'] == 'Fictional enduring requirement'
    async def crashed(*args,**kwargs):
        raise DomainError(422,'PARSER_PROCESS_FAILED','Fictional parser crash')
    monkeypatch.setattr(module,'parse_isolated',crashed)
    rerun = enqueue(http,tender).json()['id']
    run_job(http,app,rerun)
    assert http.get(f'/api/v1/jobs/{rerun}').json()['error_code'] == 'SOURCE_INCOMPLETE'
    assert http.get(f'/api/v1/sources/{version}').json()['anchors'] == before['anchors']


def test_real_worker_crash_after_commit_recovers_without_duplicate_output(client):
    jobs()
    artifacts = ROOT/'evals/runs/local'
    artifacts.mkdir(parents=True, exist_ok=True)
    http,_,app = client
    tender = create(http)
    assert upload(http,tender).status_code == 201
    job_id = enqueue(http,tender).json()['id']
    entrypoint = 'm1_recovery_test_'+uuid4().hex[:10]
    async def isolate():
        async with app.state.pool.acquire() as connection:
            await connection.execute('UPDATE m1_queue.pgqueuer SET entrypoint=$2 WHERE dedupe_key=$1',job_id,entrypoint)
    http.portal.call(isolate)
    script = Path(__file__).with_name('worker_process.py')
    def child(mode):
        import os
        environment = {**os.environ,'PYTHONPATH':str(ROOT/'apps/api')}
        process = subprocess.run([sys.executable,str(script),entrypoint,mode],cwd=ROOT/'apps/api',env=environment,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=150,
            creationflags=0x08000000 if sys.platform=='win32' else 0)
        (artifacts/f't2-worker-{mode}.txt').write_bytes(process.stderr)
        return process.returncode
    assert child('crash') == 23
    before = http.get(f'/api/v1/jobs/{job_id}').json()
    assert before['output_version_id'] is not None
    assert child('recover') == 0
    after = http.get(f'/api/v1/jobs/{job_id}').json()
    assert after['output_version_id'] == before['output_version_id']
    assert after['attempt'] == 1
    async def inspect():
        async with app.state.pool.acquire() as connection:
            count = await connection.fetchval("SELECT count(*) FROM m1_app.artifact_versions WHERE tender_id=$1 AND kind='parsed_sources'",UUID(tender['id']))
            remaining = await connection.fetchval('SELECT count(*) FROM m1_queue.pgqueuer WHERE dedupe_key=$1',job_id)
            assert count == 1
            assert remaining == 0
            report = {'crashed_worker_exit':23,'replacement_worker_exit':0,'parsed_outputs':count,
                      'business_attempts':after['attempt'],'remaining_queue_jobs':remaining,
                      'status':after['status'],'error_code':after['error_code'],
                      'scope':'Real PDF parser, Storage, PostgreSQL and PgQueuer; crash after output commit before queue acknowledgement. Test uses isolated entrypoint and 2-second heartbeat.'}
            (artifacts/'t2-recovery-latest.json').write_text(json.dumps(report,indent=2)+'\n')
    http.portal.call(inspect)
