# Extraction status and remaining gates

## Completed in this repository

- Empty independent repository bootstrapped with a dedicated FastAPI service, local-only
  container binding, resource limits, health endpoint and CI test workflow.
- Source-level inventory: 28 HR tables from the current shared stuff model source.
  SHA-256 in `source-inventory.json` identifies that source. This is not an assertion
  that every local field is already committed or identical to the live schema.
- Read-only consistent HR export, explicit identity/fact projections, checksum and row
  verification; no password hash or customer conversation tables exported.
- SSO client and disabled-by-default stuff provider integration with replay/expiry tests.
- Independent 32-table schema (28 HR tables + 4 identity/fact projections), strict new-database
  importer and foreign-key reconciliation; existing leave engine extracted unchanged.
- Legacy payroll baseline capture and exact per-component/detail reconciliation.

## Remaining implementation (not complete)

1. Obtain dedicated host SSH access and configure DNS `hr.newtonfin.com`. Inventory its
   resources and existing ingress before deploying. Do not deploy to the shared stuff
   host as an unapproved substitute. Update ops topology/monitoring only after actual setup.
2. Compare live schema and deployed code to the inventory. Freeze a reproducible source
   revision including reviewed document/leave changes currently outside clean stuff main.
3. Rehearse the independent schema and importer against the live backup; add versioned
   upgrade migrations, audit-link reconciliation and one-writer per module. `user` export is identity
   projection only; no role grants. Business `team` is a projection, not an HR department.
4. Transfer employee scans, leave proofs, recruitment CVs and all contract PDF variants,
   company signature artwork and referenced media. Verify content hashes and old links.
   No customer proof directories may be copied wholesale. Resolve file references in
   JSON/settings as well as explicit path columns. OTPs require renewed challenges.
5. Extract personnel/document/leave/recruitment routes and templates; replace monolith
   dependencies. Candidate SMS/calls/chat need restricted communication APIs, separate
   from customer conversations. Keep existing template-publish/confirm permissions.
6. Implement versioned stuff payroll-input APIs with assignment history, stage targets,
   recovery totals, legal settlement counts and quality facts; HR owns salary coefficients.
   HR cost-output API replaces stuff ROI's direct payroll imports. Existing generic
   `/api/perf/query` is insufficient and must not become unrestricted HR DB access.
7. Move payroll engine/constants/bonus policies preserving effective dates and old formula
   semantics. No payroll calculation changes bundled into migration. Snapshot frozen
   payslips; corrections append audited revisions. Reconcile at least one complete cycle.
8. Full flow integration, authorization, file access and payroll parity testing; migration
   rehearsal against a private backup, no production writes.
9. Small employee/HR pilot, module-specific write freeze, final delta transfer and verified
   single-writer switch. Old stuff module links redirect only after module acceptance.
10. Rollback must reconcile post-cutover HR writes before reverting stuff writers. Keeping
    an old image alone is insufficient. Snapshot databases/files and retain audit evidence.

## Dependencies requiring attention

`payroll.py` depends on `perf`, account assignments, employee/team business context,
quality entries, complaint settlements and the temporary bonus module. `roi.py` and
`billing.py` use payroll helpers. `/org` mixes identity, HR and business edits. Presence
heartbeats belong to stuff while HR approved attendance is a different record. The
current wage algorithm does not automatically consume leave requests; preserve existing
results before separately approving a policy change.

The export tool intentionally sets `cutover_ready=false`; file hashes and row counts
alone cannot certify payroll parity, cross-system roles or correct employee visibility.
