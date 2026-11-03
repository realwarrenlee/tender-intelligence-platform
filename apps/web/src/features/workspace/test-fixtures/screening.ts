import type { Actor, Tender, Task } from '../api'
import type { components } from '../api.generated'
import { tenderFixture } from './review'

export const owner: Actor & { qualification_workflow_enabled: boolean } = {
  user_id: 'owner',
  workspace_id: 'workspace',
  roles: ['member'],
  qualification_workflow_enabled: true,
  preparation_tracking_enabled: false,
}
export const reviewer: Actor = {
  ...owner,
  user_id: 'reviewer',
  roles: ['member'],
}
export const approver: Actor = {
  ...owner,
  user_id: 'approver',
  roles: ['member'],
}
export const members = [
  {
    user_id: 'other-approver',
    display_name: 'Alternate approver',
    roles: ['member'],
  },
  { user_id: 'owner', display_name: 'Bid owner', roles: ['member'] },
  {
    user_id: 'reviewer',
    display_name: 'Operations lead',
    roles: ['member'],
  },
  { user_id: 'approver', display_name: 'Bid approver', roles: ['member'] },
]
export function opportunity(): components['schemas']['OpportunityView'] {
  return {
    schema_version: 'm1.opportunity.v1',
    id: 'suggestion',
    revision: 1,
    source_identity: 'controlled:notice',
    intake_owner_user_id: 'owner',
    state: 'suggested',
    notice_version_id: 'notice-1',
    notice_version: 1,
    tender_id: null,
    budget_id: 'budget',
    budget_status: 'available',
    created_at: '2026-11-01T01:00:00Z',
    last_checked_at: '2026-11-01T01:00:00Z',
    notice: {
      source_identity: 'controlled:notice',
      origin: 'controlled_import',
      source_url: null,
      retrieved_at: '2026-11-01T01:00:00Z',
      title: 'Campus maintenance',
      buyer: 'Campus buyer',
      reference: 'FM-001',
      category: 'Facilities Management',
      closing_at: '2099-01-01T16:00:00+08:00',
      published_at: null,
      evidence_text:
        'Facilities Management tender. Attachments require access.',
      excerpts: {
        notice: 'Facilities Management tender. Attachments require access.',
      },
      coverage: 'notice_only',
      access_gaps: ['ATTACHMENTS_NOT_OBTAINED'],
      raw_sha256: '1'.repeat(64),
      content_sha256: '2'.repeat(64),
    },
    match: { reason: 'Facilities Management category match' },
  }
}
export function reviewCase(): components['schemas']['ReviewCaseView'] {
  return {
    schema_version: 'qualification.v1',
    tender_id: 'tender-1',
    title: 'Campus maintenance',
    owner_user_id: 'owner',
    input_revision: 2,
    evidence_revision: 1,
    screening_version_id: 'screen-1',
    screening_is_current: true,
    state: 'In progress',
    tender_stage: 'assessing',
    next_actor_id: 'owner',
    open_inputs: 0,
    open_approvals: 0,
    recommendation: 'needs_information',
    attention: null,
    closing_at: '2099-01-01T16:00:00+08:00',
    job_status: 'needs_input',
    permitted_actions: ['start_screening', 'confirm_requests'],
    preparation_decision: null,
    screening: {
      id: 'screen-1',
      input_revision: 2,
      is_current: true,
      artifact: {
        schema_version: 'screening.v1',
        title: 'Campus maintenance',
        pins: { source_signature: 'sources', notice_version_id: 'notice-1' },
        closing_at: '2099-01-01T16:00:00+08:00',
        facts: { closing_at: { citations: [] } },
        company_evidence: { accepted_version_id: 'company-1', gaps: [] },
        findings: [
          {
            id: 'registration',
            statement: 'Current FM registration before submission.',
            kind: 'eligibility',
            due_stage: 'submission',
            material_now: true,
            critical: true,
            critical_basis: 'Registration is required before submission.',
            status: 'unconfirmed',
            tender_citations: [
              {
                anchor_id: 'tender-page-1',
                quote: 'Registration is required before submission.',
              },
            ],
            company_citations: [],
            answer_ids: [],
            owner_function: 'compliance',
            request_question: 'Confirm current FM registration.',
          },
        ],
        coverage: {
          complete: true,
          source_complete: true,
          gaps: [],
          deferred: [],
          requires_wider_review: false,
        },
        recommendation: 'needs_information',
        approval_blockers: ['CRITICAL_CONDITION_UNRESOLVED'],
        request_drafts: [
          {
            draft_ref: 'finding:registration',
            purpose: 'screening_input',
            finding_ids: ['registration'],
            question: 'Confirm current FM registration.',
            owner_function: 'compliance',
            suggested_role: 'service_reviewer',
          },
          {
            draft_ref: 'preparation',
            purpose: 'preparation_approval',
            finding_ids: [],
            question: 'Review scope and preparation budget.',
            owner_function: 'bid_team',
            suggested_role: 'approver',
          },
        ],
        work_packages: [
          { owner_function: 'compliance', finding_ids: ['registration'] },
        ],
        wider_review_reason: null,
        attention: null,
        classifications: [],
        usage: {
          budget_id: 'budget',
          actual_cost_usd: '0.03',
          reserved_usd: '0',
          limit_usd: '0.50',
          provider_requests: 2,
        },
      },
    },
  }
}
export function boundedTender(): Tender & { workflow: 'screening' } {
  return {
    ...(structuredClone(tenderFixture) as unknown as Tender),
    workflow: 'screening',
    title: 'Campus maintenance',
    documents: [
      {
        ...structuredClone(tenderFixture.documents[0]),
        role: 'tender',
        filename: 'instructions.docx',
        content_type:
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      },
    ],
    assessment: null,
    assessment_status: 'not_ready',
    review_tasks: [],
    jobs: [],
  }
}
export function scopedTask(purpose = 'screening_input'): Task {
  return {
    schema_version: 'm1.v1',
    id: purpose === 'preparation_approval' ? 'approval-task' : 'input-task',
    tender_id: 'tender-1',
    assessment_version_id: 'screen-1',
    assignee_id: purpose === 'preparation_approval' ? 'approver' : 'reviewer',
    created_by: 'owner',
    purpose,
    draft_ref:
      purpose === 'preparation_approval'
        ? 'preparation'
        : 'finding:registration',
    requirement_ids: purpose === 'preparation_approval' ? [] : ['registration'],
    question:
      purpose === 'preparation_approval'
        ? 'Review scope and preparation budget.'
        : 'Confirm current FM registration.',
    status: 'open',
    revision: 1,
    due_at: '2098-12-30T10:00:00+08:00',
    created_at: '2026-11-01T01:00:00Z',
    manifest: {
      workflow: 'screening.v1',
      source_signature: 'sources',
      evidence_revision: 1,
    },
    is_current: true,
    answer: null,
  }
}
