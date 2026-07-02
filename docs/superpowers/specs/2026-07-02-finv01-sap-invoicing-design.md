# FINV01 Invoicing + SAP Integration — Design

**Date:** 2026-07-02
**Status:** Approved (design), pending spec review
**Program:** Finance/AR overhaul, combined sub-project #5+#6 (folded per user).
Depends on #1–#4 (services, ledger/billed-lock, billables engine, bill generation),
all on main. Final finance piece: turn bills into invoices and post them to SAP.

## Problem

Bills exist (#4) but there is no invoicing. FINV01 (local copy is stale/broken)
must be rebuilt from the reference PORTMAN repo: create an invoice from selected
bills, number it from a doc series, list invoices, and print it (services on the
front page, supporting docs — cargo-handling details + bill breakdown — on the
back). Invoices post to SAP via the same interface the reference uses.

## Inventory (local vs reference)

**Already present locally (keep / reconcile lightly — the SAP payload is fixed by
the remote and does not change):**
- `sap_builder.py` (builds SAP JSON payloads), `sap_client.py` (OAuth2 + REST post/IRN)
- `modules/SAPCFG` (SAP config: `get_active_config`), `modules/FSAP01` (SAP monitor, already registered in app.py)
- tables: `invoice_header`, `invoice_lines`, `invoice_bill_mapping`, `invoice_doc_series`, `invoice_sap_staging`, `sap_api_config`
- `requests` 2.34.1 installed

**Missing (add, copy-adapt from reference):**
- `sap_queue.py` — background async SAP posting + retry; `sap_inbound.py` — token-auth webhook SAP calls back with IRN/status
- their tables (sap queue + integration log + inbound tokens — exact DDL from the reference)
- **FINV01 module** — views + templates (invoice create/list/doc-series/print)
- registration of the inbound webhook route in `app.py`

**Reference source:** GitHub `shubhamshnd/PORTMAN` — `modules/FINV01`, `sap_queue.py`,
`sap_inbound.py` (fetch via the GitHub API base64 method; copies staged in `/tmp/ref/`).

## Constraints (from brainstorming)

- **The SAP payload/interface does not change** — do not rewrite `sap_builder`/`sap_client`
  logic; reconcile only if a genuine drift is found. Payloads must match the remote exactly.
- **Include the inbound webhook** (`sap_inbound`).
- **Drop MBC everywhere** (reference FINV01 has ~31 MBC refs).
- Invoices are created from **bills** (`invoice_bill_mapping`); bills may span vessels
  (#4 `bill_vessels`) — the print groups supporting docs by vessel.
- Live SAP posting is **not testable here** (no SAP creds/endpoint); unit-test payload
  building, queue claim/retry, inbound token verification, and invoice create/print.

## Design (task areas — the plan splits these into bite-sized tasks)

### A. Reconcile SAP core (light)
Diff local `sap_builder.py` / `sap_client.py` / `modules/SAPCFG` / `modules/FSAP01`
against the reference. Apply changes ONLY where they genuinely differ and the
difference is not MBC. Expected outcome: little or no change (interface is fixed).
Record any real drift found.

### B. Async posting + inbound webhook
- Add `sap_queue.py` (copy-adapt): `enqueue`, `trigger` (daemon thread), `process_sap_queue`,
  `_claim`/`_attempt`/`_mark_sent`/`_mark_failed`, `manual_send`. Uses `sap_client`.
- Add `sap_inbound.py` (copy-adapt): token table + `generate/revoke/reactivate/list_tokens`,
  `_verify_token`, `_apply_record` (writes IRN/status back onto the invoice), `sap_callback_view`.
- Migration for the missing tables (sap queue, integration log, inbound tokens) — exact
  columns copied from the reference's table creation / usage.
- Register the inbound route (`sap_callback_view`) in `app.py`.

### C. FINV01 rebuild (copy reference, strip MBC)
- `modules/FINV01/views.py` + templates (`finv01_invoices.html`, `finv01_generate_invoice.html`,
  `finv01_invoice_print.html`, `finv01_doc_series.html`), copied from the reference and adapted
  to local schema/imports, MBC removed.
- Invoice create from selected bills → `invoice_header` + `invoice_lines` + `invoice_bill_mapping`,
  doc-series numbering (`invoice_doc_series`), customer snapshot, GST/TDS carried from bill lines.
- Print: front = service lines (`_build_display_lines`); back = supporting docs
  (`_get_cargo_handling_details`, bill breakdown, vessel grouping via `bill_vessels`).
- Ensure FINV01 is registered in `app.py` (rebuild the registration if the stale one is removed).

### D. Wire FINV01 → SAP
- On invoice create, `_enqueue_invoice_post` → `sap_queue.enqueue(...)` with the payload from
  `sap_builder.build_invoice_payload`.
- Port the SAP-facing endpoints: `retry-sap`, `fetch-irn`, `cancel-sap`,
  `create-cancellation-cn`, `export-sap-json`, `sap-queue/manual-send`, GSTR1 export —
  wired to `sap_queue`/`sap_client`/`sap_builder`. MBC removed.

## Testing

- `sap_builder.build_invoice_payload` — unit test: a sample invoice header+lines yields the
  expected payload shape (items, totals, GL map, nature-of-transaction). No network.
- `sap_queue` — enqueue then `_claim` marks a row in-progress; a failed attempt increments
  retry / marks failed after the cap (mock `sap_client.post_invoice_to_sap`).
- `sap_inbound._verify_token` — valid/invalid/revoked token; `_apply_record` writes IRN onto
  a throwaway invoice.
- FINV01 invoice create — from a throwaway bill: `invoice_header` + `invoice_lines` +
  `invoice_bill_mapping` created, numbered, GST/TDS carried; print renders without error.
- Live SAP OAuth/post/IRN round-trip: **manual, in your environment** (documented, not automated).

## Out of scope

MBC (excluded); changes to the SAP payload contract; any new SAP business logic beyond the
reference; editing the bill-generation flow (#4).
