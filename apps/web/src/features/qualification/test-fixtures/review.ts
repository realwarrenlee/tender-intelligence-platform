const citation = {
  anchor_id: 'tender-page-1',
  quote: 'Provide two qualified technicians every Saturday.',
}
const fact = (value: string | null) => ({
  value,
  citations: value ? [citation] : [],
})
const requirement = {
  local_ref: 'R1',
  text: 'Provide two qualified technicians every Saturday.',
  kind: 'delivery',
  mandatory: true,
  tender_citations: [citation],
  status: 'unconfirmed',
  company_citations: [],
  explanation: 'The company profile does not confirm Saturday allocation.',
  missing_information: 'Confirm Saturday availability.',
}
const assessment = {
  id: 'assessment-1',
  input_revision: 2,
  created_by: 'owner',
  is_current: true,
  candidate: {
    summary: 'Saturday availability needs confirmation.',
    key_facts: {
      title: fact('Fictional campus maintenance'),
      buyer: fact('Fictional buyer'),
      closing_at: fact('2026-11-20T16:00:00+08:00'),
      service_start_on: fact(null),
      term_months: { value: 12, citations: [citation] },
    },
    requirements: [requirement],
    recommendation: {
      decision: 'hold',
      reasons: ['Staffing is unconfirmed.'],
      condition_refs: ['R1'],
    },
    review_requests: [
      {
        draft_ref: 'Q1',
        requirement_refs: ['R1'],
        suggested_role: 'engineering_lead',
        question: 'Can two qualified technicians attend every Saturday?',
        rationale: 'Availability is unconfirmed.',
      },
    ],
    warnings: [],
  },
  requirements: [{ id: 'a'.repeat(64), requirement, carried_forward: false }],
  blockers: [
    { code: 'QUALIFICATION_UNCONFIRMED', requirement_id: 'a'.repeat(64) },
  ],
  reconciliation: [],
  manual_corrections: [],
  run: null,
  human_reason: null,
}
const initial = {
  schema_version: 'm1.v1',
  id: 'tender-1',
  workspace_id: 'workspace',
  title: 'Fictional campus maintenance',
  source_label: 'manual_upload',
  owner_user_id: 'owner',
  input_revision: 2,
  created_at: '2026-10-24T01:00:00Z',
  source_set_version_id: 'source-set-1',
  documents: [
    {
      id: 'document-1',
      filename: 'tender.pdf',
      sha256: '1'.repeat(64),
      role: 'tender',
      content_type: 'application/pdf',
      byte_size: 100,
      page_count: 1,
      amends_version_id: null,
      created_at: '2026-10-24T01:00:00Z',
    },
  ],
  assessment,
  assessment_status: 'current',
  review_tasks: [],
  decision: null,
  jobs: [],
}
const task = {
  schema_version: 'm1.v1',
  id: 'task-1',
  tender_id: 'tender-1',
  assessment_version_id: 'assessment-1',
  assignee_id: 'reviewer',
  created_by: 'owner',
  draft_ref: 'Q1',
  requirement_ids: ['a'.repeat(64)],
  purpose: 'qualification_review',
  question: 'Can two qualified technicians attend every Saturday?',
  status: 'open',
  revision: 1,
  due_at: '2026-10-26T12:00:00Z',
  created_at: '2026-10-24T01:00:00Z',
  manifest: {},
  is_current: true,
  answer: null,
}

export { initial as tenderFixture, task as taskFixture }
