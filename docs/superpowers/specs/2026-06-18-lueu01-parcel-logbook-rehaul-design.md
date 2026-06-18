# LUEU01 Parcel Logbook Rehaul — Design

**Date:** 2026-06-18
**Module:** LUEU01 (Load Unload Equipment Utilization)
**Status:** Approved for spec review

## 1. Goal

Replace the flat `lueu_lines` logbook with a **vessel → parcel → logbook** flow.
Operators pick a vessel, see its *started* LDUD parcels, and maintain a per-parcel
time-interval logbook (quantity + delays) where each row records the medium used
(Equipment from VEM01, or Direct Pipe). Selection survives a page reload.

Built on the new parcel system: started parcels come from `ldud_parcel_ops`
(`start_dt` set), introduced in the LDUD01 rehaul (see [[ldud-parcel-migration]]).

## 2. Scope decisions (locked)

- **Storage:** new table `lueu_parcel_log`; **retire `lueu_lines`** (stop writing/reading it in LUEU01).
- **Dashboard:** the LUEU01 dashboard page + `/dashboard` + `/dashboard-data` are **removed**.
- **Parcels shown:** every parcel with `start_dt` set (in-progress **and** completed).
- **Vessels shown:** only VCNs with ≥1 started parcel.
- **Medium:** chosen **per logbook row** — `Equipment` (enables VEM01 equipment dropdown) or `Direct Pipe` (equipment blank/disabled).
- **Row fields kept:** shift (A/B/C), operator, shift-incharge, berth. **Berth defaults to the vessel's `vcn_header.berth_name`**, still editable.
- **Delete:** soft delete (`is_deleted` / `deleted_by` / `deleted_date`).
- **Removals:** drop `route_name`/`system_name`; delete **CRM01** (Conveyor Route Master) + **PSM01** (Port System Master) modules and **DROP** `conveyor_routes` + `port_systems`.
- **Refresh:** persist selected vessel + expanded parcels across reload (localStorage + URL `?vcn=`).

## 3. Deferred / out of scope (will break, by decision)

- **RP01** shift_report, daily_ops, custom_report read `lueu_lines` (+ `route_name`/`system_name`). They are **left broken**, to be rebuilt later against `lueu_parcel_log` — same posture as the LDUD/RP01 deferral. Tracked in [[rp01-finv01-rebuild-pending]].
- `populate_mock_data.py` / `reset_billing.py` still reference `lueu_lines`; dev scripts, not rebuilt now.
- The dead FDCN auto-CN path (`soft_delete_lines` → `create_eu_deletion_cn`) is dropped with `lueu_lines`; billing already does not read `lueu_lines`.

## 4. Data model

### New: `lueu_parcel_log`
```
id              SERIAL PK
parcel_op_id    INTEGER NOT NULL  → ldud_parcel_ops(id) ON DELETE CASCADE
entry_date      TEXT
from_time       TEXT              -- 'HH:MM'
to_time         TEXT
quantity        NUMERIC
quantity_uom    TEXT
medium          TEXT              -- 'Equipment' | 'Direct Pipe'
equipment_name  TEXT              -- set only when medium='Equipment'
delay_name      TEXT
shift           TEXT              -- 'A' | 'B' | 'C'
operator_name   TEXT
shift_incharge  TEXT
berth_name      TEXT              -- defaults to vcn_header.berth_name
remarks         TEXT
created_by      TEXT
created_date    TEXT
is_deleted      BOOLEAN DEFAULT FALSE
deleted_by      TEXT
deleted_date    TEXT
```

### Dropped
- `conveyor_routes`, `port_systems`.

### Retired (kept physically? NO)
- `lueu_lines` is dropped. (RP01 readers break — accepted.)

## 5. Backend (model.py + views.py rewrite)

Model functions:
- `get_vessels_with_started_parcels()` → `[{vcn_id, vcn_doc_num, vessel_name, berth_name, parcel_count}]`. Source: `ldud_parcel_ops` (start_dt NOT NULL) JOIN `ldud_header` JOIN `vcn_header`, distinct by VCN.
- `get_started_parcels(vcn_id)` → per parcel: `{parcel_op_id, parcel_no, cargo_name, declared_qty, logged_qty, uom, start_dt, end_dt, status}`. `parcel_no`/declared qty resolved operation-type-aware from `vcn_consigners` / `vcn_export_cargo_declaration` via the parcel ids (reuse the LDUD `_parcel_table_for_ldud` pattern). `logged_qty` = SUM of non-deleted `lueu_parcel_log.quantity` for that parcel.
- `get_log(parcel_op_id)` → non-deleted rows ordered by entry_date, from_time.
- `save_log(data)` → insert/update one row.
- `soft_delete_log(ids, username)`.

Endpoints (`/api/module/LUEU01/...`):
- `GET vessels` · `GET parcels/<vcn_id>` · `GET log/<parcel_op_id>` · `POST log/save` · `POST log/delete`
- Dropdown endpoints kept: `equipment` (VEM01), `delays` (port_delay_types), `uom`, `berths`, `shift-incharge`, `shift-operators`.
- **Removed endpoints:** `routes`, `systems`, `vcn-options`, `split`, `bl-progress` (replaced by per-parcel progress), `dashboard*`.
- Permission gating unchanged (`get_perms`).

## 6. Frontend (lueu01.html rewrite)

Single page, three panes:
1. **Vessel list** (left) — vessels with started parcels; click selects.
2. **Parcel list** (under selected vessel) — each parcel row: parcel no, cargo, status badge, `logged / declared uom` progress bar. Click expands.
3. **Logbook grid** (per expanded parcel, Tabulator) — columns: Date, From, To, Quantity, UOM, Medium (list: Equipment/Direct Pipe), Equipment (list VEM01; editable only when Medium=Equipment), Delay (list), Shift (A/B/C), Operator, Shift-Incharge, Berth (defaults to vessel berth), Remarks, delete. New-row helper chains `from_time` = previous row's `to_time` and defaults entry_date/shift to now.

**Refresh-persist:** on vessel select, write `vcn` to URL + `localStorage('lueu_sel')` with `{vcn_id, expanded:[parcel_op_id...]}`. On load, read it back, re-select vessel, re-expand parcels, refetch. A manual Refresh button re-pulls current selection without collapsing.

## 7. Removal steps (CRM01 / PSM01)

- `app.py`: remove blueprint imports + `register_blueprint` for `crm01`, `psm01`.
- `templates/base.html`: remove menu links.
- Module permission rows: leave (harmless) or clean via existing admin; not required.
- Delete `modules/CRM01/`, `modules/PSM01/` package dirs.
- Migration drops `conveyor_routes`, `port_systems`.

## 8. Migration plan (one alembic revision, head = jnpa18)

`jnpa19_lueu_parcel_logbook`:
- `CREATE TABLE lueu_parcel_log (...)`.
- `DROP TABLE lueu_lines`, `conveyor_routes`, `port_systems`.
- Downgrade: recreate dropped tables (best-effort, no data) + drop `lueu_parcel_log`.

## 9. Testing / verification

- Migration applies; modules import.
- `get_vessels_with_started_parcels` / `get_started_parcels` run against live DB without referencing dropped tables.
- Save → fetch → soft-delete round-trip on `lueu_parcel_log`.
- Medium=Direct Pipe stores blank equipment; Medium=Equipment requires equipment.
- `lueu01.html` passes `node --check`.
- App boots with CRM01/PSM01 unregistered (no import errors).

## 10. Phases (for the implementation plan)

1. Migration (new table + drops).
2. Backend model + views rewrite.
3. Frontend rewrite (nav + logbook + refresh-persist).
4. Remove CRM01/PSM01 (app.py, base.html, dirs).
5. Verification pass.
