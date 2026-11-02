class DomainError(Exception):
    def __init__(self, status_code, code, message):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def assert_current_input(expected_revision, actual_revision):
    if expected_revision != actual_revision:
        raise DomainError(409, "STALE_INPUT", "The tender inputs changed; refresh before continuing.")


def qualification_blockers(assessment,as_of):
    from datetime import date,datetime
    from zoneinfo import ZoneInfo
    candidate=assessment['candidate']
    context=assessment['context']
    blockers=[]
    def add(code,requirement_id=None):
        entry={'code':code,'requirement_id':requirement_id}
        if entry not in blockers: blockers.append(entry)
    closing=candidate['key_facts']['closing_at']['value']
    if not closing: add('CLOSING_UNKNOWN')
    elif datetime.fromisoformat(closing)<=as_of: add('CLOSING_PASSED')
    if not context.get('source_complete',False): add('SOURCE_INCOMPLETE')
    today=as_of.astimezone(ZoneInfo(context['closing_timezone'])).date()
    required_on=datetime.fromisoformat(closing).astimezone(ZoneInfo(context['closing_timezone'])).date() if closing else today
    for record in assessment['requirements']:
        req=record['requirement']
        if req['mandatory'] and req['kind'] in ('eligibility','delivery'):
            if req['status']!='met': add('QUALIFICATION_'+req['status'].upper(),record['id'])
            for citation in req['company_citations']:
                anchor=context['source_anchors'].get(citation['anchor_id'])
                dates=context.get('evidence_dates',{}).get(anchor['document_version_id'],{}) if anchor else {}
                if dates.get('expires_on') and date.fromisoformat(dates['expires_on'])<required_on: add('EVIDENCE_EXPIRED',record['id'])
                if dates.get('effective_on') and date.fromisoformat(dates['effective_on'])>today: add('EVIDENCE_NOT_EFFECTIVE',record['id'])
    for warning in candidate['warnings']:
        if warning['code'] in ('conflicting_dates','incomplete_source','unsupported_input'): add(warning['code'].upper())
    for change in assessment['reconciliation']:
        if not change.get('resolved'): add('RECONCILIATION_REQUIRED',change.get('requirement_id'))
    return blockers
