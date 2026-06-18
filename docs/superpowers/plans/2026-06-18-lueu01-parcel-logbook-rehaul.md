# LUEU01 Parcel Logbook Rehaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LUEU01's flat `lueu_lines` logbook with a vessel → started-parcel → per-parcel time-interval logbook (quantity + delays + medium), with selection persisted across reload; delete the Conveyor Route (CRM01) and Port System (PSM01) masters.

**Architecture:** Flask blueprint + raw psycopg (`database.get_db/get_cursor`), Tabulator front-end in a single Jinja template. Started parcels come from `ldud_parcel_ops` (`start_dt` set), resolving parcel labels/declared-qty operation-type-aware from `vcn_consigners` (Import) / `vcn_export_cargo_declaration` (Export). New data lives in `lueu_parcel_log`; `lueu_lines` is dropped.

**Tech Stack:** Python 3 / Flask, PostgreSQL via psycopg, Alembic migrations, Tabulator 5 (vanilla JS), Jinja2.

## Global Constraints

- DB access only via `from database import get_db, get_cursor`; open a conn, use `get_cursor(conn)`, `conn.commit()` for writes, `conn.close()` always. Rows are dict-like.
- SQL values always parameterized (`%s`); never f-string user values. Table names interpolated only from a fixed whitelist.
- Permission gate pattern: `get_perms()` (admin → all; else `get_user_permissions(user_id, 'LUEU01')`); writes require `can_add`/`can_edit`, deletes `can_delete`.
- Alembic: new revision `down_revision = 'jnpa18_export_parcel_identity'` (current head). Apply with `alembic upgrade head`.
- No pytest in this repo — verify with `python -c`/heredoc smoke checks, `alembic upgrade head`, and `node --check` on extracted inline JS.
- Repo policy: do NOT commit to `main`. Before the first commit, create a branch `feat/lueu01-parcel-logbook`. Each task ends with a commit on that branch.
- `medium` is one of exactly `'Equipment'` or `'Direct Pipe'`. `equipment_name` is only stored when `medium='Equipment'`.

---

## Task 1: Migration — new table + drop legacy/master tables

**Files:**
- Create: `alembic/versions/jnpa19_lueu_parcel_logbook.py`

**Interfaces:**
- Produces: table `lueu_parcel_log` with columns listed below; drops `lueu_lines`, `conveyor_routes`, `port_systems`.

- [ ] **Step 1: Create the migration file**

```python
"""jnpa phase1 - LUEU01 parcel logbook; drop lueu_lines + route/system masters

Revision ID: jnpa19_lueu_parcel_logbook
Revises: jnpa18_export_parcel_identity
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa19_lueu_parcel_logbook'
down_revision: Union[str, None] = 'jnpa18_export_parcel_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS lueu_parcel_log (
            id SERIAL PRIMARY KEY,
            parcel_op_id INTEGER NOT NULL,
            entry_date TEXT,
            from_time TEXT,
            to_time TEXT,
            quantity NUMERIC,
            quantity_uom TEXT,
            medium TEXT,
            equipment_name TEXT,
            delay_name TEXT,
            shift TEXT,
            operator_name TEXT,
            shift_incharge TEXT,
            berth_name TEXT,
            remarks TEXT,
            created_by TEXT,
            created_date TEXT,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_by TEXT,
            deleted_date TEXT,
            FOREIGN KEY (parcel_op_id) REFERENCES ldud_parcel_ops(id) ON DELETE CASCADE
        );
        DROP TABLE IF EXISTS lueu_lines;
        DROP TABLE IF EXISTS conveyor_routes;
        DROP TABLE IF EXISTS port_systems;
    ''')


def downgrade() -> None:
    # Best-effort recreate (no data restored).
    op.execute('''
        DROP TABLE IF EXISTS lueu_parcel_log;
        CREATE TABLE IF NOT EXISTS conveyor_routes (
            id SERIAL PRIMARY KEY, route_name TEXT, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS port_systems (
            id SERIAL PRIMARY KEY, name TEXT
        );
        CREATE TABLE IF NOT EXISTS lueu_lines (id SERIAL PRIMARY KEY);
    ''')
```

- [ ] **Step 2: Apply and verify schema**

Run:
```bash
alembic upgrade head
python -c "
from database import get_db, get_cursor
c=get_db(); cur=get_cursor(c)
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='lueu_parcel_log' ORDER BY ordinal_position\")
print('lueu_parcel_log:', [r['column_name'] for r in cur.fetchall()])
for t in ('lueu_lines','conveyor_routes','port_systems'):
    cur.execute('SELECT to_regclass(%s)', [t]); print(t, '->', cur.fetchone()['to_regclass'])
c.close()"
```
Expected: full column list printed; the three dropped tables each print `None`.

- [ ] **Step 3: Commit**

```bash
git checkout -b feat/lueu01-parcel-logbook
git add alembic/versions/jnpa19_lueu_parcel_logbook.py
git commit -m "feat(lueu01): migration — lueu_parcel_log + drop lueu_lines/route/system

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Backend model — vessels, parcels, logbook CRUD

**Files:**
- Rewrite: `modules/LUEU01/model.py` (replace entire file)

**Interfaces:**
- Consumes: `ldud_parcel_ops(id, ldud_id, parcel_ids, cargo_name, start_dt, end_dt)`, `ldud_header(id, vcn_id)`, `vcn_header(id, vcn_doc_num, vessel_name, berth_name, operation_type)`, `vcn_consigners(id, parcel_no, cargo_name, quantity)`, `vcn_export_cargo_declaration(id, parcel_no, cargo_name, bl_quantity)`.
- Produces:
  - `get_vessels_with_started_parcels() -> list[dict]` keys: `vcn_id, vcn_doc_num, vessel_name, berth_name, parcel_count`
  - `get_started_parcels(vcn_id) -> list[dict]` keys: `parcel_op_id, parcel_no, cargo_name, declared_qty, logged_qty, uom, start_dt, end_dt, status`
  - `get_log(parcel_op_id) -> list[dict]` (raw `lueu_parcel_log` rows, non-deleted)
  - `save_log(data: dict) -> int` (row id)
  - `soft_delete_log(ids: list[int], username: str) -> None`

- [ ] **Step 1: Replace `modules/LUEU01/model.py` with:**

```python
from database import get_db, get_cursor
from datetime import datetime

# parcel_ids on ldud_parcel_ops point at the VCN's parcel source table,
# chosen by the linked VCN's operation_type (whitelisted — safe to interpolate).
def _parse_ids(csv):
    return [int(x) for x in str(csv or '').split(',') if str(x).strip().isdigit()]


def _num(v):
    if v is None or (isinstance(v, str) and v.strip() == ''):
        return None
    return v


def get_vessels_with_started_parcels():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT h.id AS vcn_id, h.vcn_doc_num, h.vessel_name, h.berth_name,
               COUNT(po.id) AS parcel_count
        FROM ldud_parcel_ops po
        JOIN ldud_header l ON l.id = po.ldud_id
        JOIN vcn_header h ON h.id = l.vcn_id
        WHERE po.start_dt IS NOT NULL
        GROUP BY h.id, h.vcn_doc_num, h.vessel_name, h.berth_name
        ORDER BY h.vcn_doc_num DESC
    ''')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_started_parcels(vcn_id):
    conn = get_db()
    cur = get_cursor(conn)
    # operation_type decides which table holds the parcel master rows
    cur.execute('SELECT operation_type FROM vcn_header WHERE id=%s', [vcn_id])
    row = cur.fetchone()
    op = (row or {}).get('operation_type') if row else None
    is_export = op == 'Export'
    tbl = 'vcn_export_cargo_declaration' if is_export else 'vcn_consigners'
    qty_col = 'bl_quantity' if is_export else 'quantity'

    cur.execute('''
        SELECT po.id AS parcel_op_id, po.parcel_ids, po.cargo_name,
               po.start_dt, po.end_dt
        FROM ldud_parcel_ops po
        JOIN ldud_header l ON l.id = po.ldud_id
        WHERE l.vcn_id = %s AND po.start_dt IS NOT NULL
        ORDER BY po.id
    ''', [vcn_id])
    parcels = [dict(r) for r in cur.fetchall()]

    # resolve parcel_no + declared qty from the source table
    all_ids = sorted({pid for p in parcels for pid in _parse_ids(p['parcel_ids'])})
    labels, qty = {}, {}
    if all_ids:
        cur.execute(f'SELECT id, parcel_no, {qty_col} AS q FROM {tbl} WHERE id = ANY(%s)', [all_ids])
        for r in cur.fetchall():
            labels[r['id']] = r['parcel_no'] or f"#{r['id']}"
            try:
                qty[r['id']] = float(str(r['q']).replace(',', '')) if r['q'] is not None else 0.0
            except (ValueError, TypeError):
                qty[r['id']] = 0.0

    # logged qty per parcel (non-deleted)
    pop_ids = [p['parcel_op_id'] for p in parcels]
    logged = {}
    if pop_ids:
        cur.execute('''SELECT parcel_op_id, COALESCE(SUM(quantity),0) AS s
                       FROM lueu_parcel_log
                       WHERE parcel_op_id = ANY(%s) AND is_deleted IS NOT TRUE
                       GROUP BY parcel_op_id''', [pop_ids])
        logged = {r['parcel_op_id']: float(r['s'] or 0) for r in cur.fetchall()}
    conn.close()

    out = []
    for p in parcels:
        ids = _parse_ids(p['parcel_ids'])
        out.append({
            'parcel_op_id': p['parcel_op_id'],
            'parcel_no': ', '.join(labels.get(i, f"#{i}") for i in ids) or '—',
            'cargo_name': p['cargo_name'] or '',
            'declared_qty': round(sum(qty.get(i, 0.0) for i in ids), 3),
            'logged_qty': round(logged.get(p['parcel_op_id'], 0.0), 3),
            'uom': 'MT',
            'start_dt': p['start_dt'],
            'end_dt': p['end_dt'],
            'status': 'Completed' if p['end_dt'] else 'In Progress',
        })
    return out


_LOG_COLS = ['parcel_op_id', 'entry_date', 'from_time', 'to_time', 'quantity',
             'quantity_uom', 'medium', 'equipment_name', 'delay_name', 'shift',
             'operator_name', 'shift_incharge', 'berth_name', 'remarks']


def get_log(parcel_op_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''SELECT * FROM lueu_parcel_log
                   WHERE parcel_op_id=%s AND is_deleted IS NOT TRUE
                   ORDER BY entry_date, from_time, id''', [parcel_op_id])
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_log(data):
    # Direct Pipe carries no equipment
    if data.get('medium') == 'Direct Pipe':
        data['equipment_name'] = None
    data['quantity'] = _num(data.get('quantity'))
    conn = get_db()
    cur = get_cursor(conn)
    if data.get('id'):
        sets = ', '.join(f'{c}=%s' for c in _LOG_COLS)
        cur.execute(f'UPDATE lueu_parcel_log SET {sets} WHERE id=%s',
                    [data.get(c) for c in _LOG_COLS] + [data['id']])
        row_id = data['id']
    else:
        cols = _LOG_COLS + ['created_by', 'created_date']
        vals = [data.get(c) for c in _LOG_COLS] + [data.get('created_by'),
                                                   datetime.now().strftime('%Y-%m-%d')]
        ph = ', '.join(['%s'] * len(cols))
        cur.execute(f'INSERT INTO lueu_parcel_log ({", ".join(cols)}) VALUES ({ph}) RETURNING id', vals)
        row_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    return row_id


def soft_delete_log(ids, username):
    conn = get_db()
    cur = get_cursor(conn)
    today = datetime.now().strftime('%Y-%m-%d')
    for log_id in ids:
        cur.execute('''UPDATE lueu_parcel_log
                       SET is_deleted=TRUE, deleted_by=%s, deleted_date=%s
                       WHERE id=%s AND is_deleted IS NOT TRUE''', [username, today, log_id])
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Smoke-test model round-trip**

Run:
```bash
python - <<'EOF'
from modules.LUEU01 import model as m
vs = m.get_vessels_with_started_parcels()
print('vessels:', len(vs), vs[:1])
if vs:
    ps = m.get_started_parcels(vs[0]['vcn_id'])
    print('parcels:', ps[:1])
    if ps:
        pid = ps[0]['parcel_op_id']
        rid = m.save_log({'parcel_op_id': pid, 'entry_date':'2026-06-18','from_time':'10:00',
                          'to_time':'10:05','quantity':'120','quantity_uom':'MT',
                          'medium':'Direct Pipe','equipment_name':'X','created_by':'tester'})
        row = [r for r in m.get_log(pid) if r['id']==rid][0]
        assert row['equipment_name'] is None, 'Direct Pipe must blank equipment'
        assert float(row['quantity'])==120.0
        m.soft_delete_log([rid],'tester')
        assert all(r['id']!=rid for r in m.get_log(pid)), 'soft delete must hide row'
        print('round-trip OK')
    else: print('no started parcels to test save (DB-dependent)')
else: print('no started-parcel vessels in DB (DB-dependent)')
EOF
```
Expected: prints `round-trip OK` when a started parcel exists; otherwise prints the DB-dependent notice without error. No exception either way.

- [ ] **Step 3: Commit**

```bash
git add modules/LUEU01/model.py
git commit -m "feat(lueu01): model — vessels/started-parcels/logbook on lueu_parcel_log

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Backend views — endpoints rewrite

**Files:**
- Rewrite: `modules/LUEU01/views.py` (replace entire file)

**Interfaces:**
- Consumes: all `model` functions from Task 2.
- Produces routes: `GET /api/module/LUEU01/vessels`, `GET .../parcels/<int:vcn_id>`, `GET .../log/<int:parcel_op_id>`, `POST .../log/save`, `POST .../log/delete`, plus dropdowns `equipment`, `delays`, `uom`, `berths`, `shift-incharge`, `shift-operators`, and the page route `GET /module/LUEU01/`.

- [ ] **Step 1: Replace `modules/LUEU01/views.py` with:**

```python
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from . import model
from database import get_user_permissions, get_db, get_cursor

bp = Blueprint('LUEU01', __name__, template_folder='.')
MODULE_CODE = 'LUEU01'
MODULE_INFO = {'code': 'LUEU01', 'name': 'Load Unload Equipment Utilization'}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_perms():
    if session.get('is_admin'):
        return {'can_read': 1, 'can_add': 1, 'can_edit': 1, 'can_delete': 1}
    return get_user_permissions(session.get('user_id'), MODULE_CODE)


@bp.route('/module/LUEU01/')
@login_required
def view():
    perms = get_perms()
    if not perms.get('can_read'):
        return render_template('no_access.html'), 403
    return render_template('lueu01.html', permissions=perms)


@bp.route('/api/module/LUEU01/vessels')
@login_required
def get_vessels():
    return jsonify(model.get_vessels_with_started_parcels())


@bp.route('/api/module/LUEU01/parcels/<int:vcn_id>')
@login_required
def get_parcels(vcn_id):
    return jsonify(model.get_started_parcels(vcn_id))


@bp.route('/api/module/LUEU01/log/<int:parcel_op_id>')
@login_required
def get_log(parcel_op_id):
    return jsonify(model.get_log(parcel_op_id))


@bp.route('/api/module/LUEU01/log/save', methods=['POST'])
@login_required
def save_log():
    perms = get_perms()
    if not perms.get('can_add') and not perms.get('can_edit'):
        return jsonify({'error': 'No permission'}), 403
    data = request.json or {}
    data['created_by'] = session.get('username')
    return jsonify({'id': model.save_log(data), 'success': True})


@bp.route('/api/module/LUEU01/log/delete', methods=['POST'])
@login_required
def delete_log():
    perms = get_perms()
    if not perms.get('can_delete'):
        return jsonify({'error': 'No permission to delete'}), 403
    ids = (request.json or {}).get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    model.soft_delete_log(ids, session.get('username'))
    return jsonify({'success': True, 'deleted_count': len(ids)})


def _names(sql):
    conn = get_db(); cur = get_cursor(conn)
    cur.execute(sql); rows = cur.fetchall(); conn.close()
    return rows


@bp.route('/api/module/LUEU01/equipment')
@login_required
def get_equipment():
    return jsonify([r['name'] for r in _names('SELECT name FROM equipment ORDER BY name')])


@bp.route('/api/module/LUEU01/delays')
@login_required
def get_delays():
    return jsonify([r['name'] for r in _names('SELECT name FROM port_delay_types ORDER BY name')])


@bp.route('/api/module/LUEU01/uom')
@login_required
def get_uom():
    rows = _names('SELECT name, is_default FROM quantity_uom ORDER BY name')
    return jsonify({'names': [r['name'] for r in rows],
                    'default': next((r['name'] for r in rows if r['is_default']), '')})


@bp.route('/api/module/LUEU01/berths')
@login_required
def get_berths():
    return jsonify([r['berth_name'] for r in _names('SELECT berth_name FROM port_berth_master ORDER BY berth_name')])


@bp.route('/api/module/LUEU01/shift-incharge')
@login_required
def get_shift_incharge():
    return jsonify([r['name'] for r in _names(
        "SELECT name FROM port_shift_incharge WHERE name IS NOT NULL AND name != '' ORDER BY name")])


@bp.route('/api/module/LUEU01/shift-operators')
@login_required
def get_shift_operators():
    return jsonify([r['name'] for r in _names(
        "SELECT name FROM port_shift_operators WHERE name IS NOT NULL AND name != '' ORDER BY name")])
```

- [ ] **Step 2: Verify import + route registration**

Run:
```bash
python -c "
import modules.LUEU01.views as v
rules = [str(r) for r in v.bp.deferred_functions] if hasattr(v.bp,'deferred_functions') else []
import modules.LUEU01.model
print('LUEU01 views import OK')"
```
Expected: `LUEU01 views import OK`, no ImportError (confirms no leftover refs to removed `fdcn_model`, `routes`, `systems`, `dashboard`).

- [ ] **Step 3: Commit**

```bash
git add modules/LUEU01/views.py
git commit -m "feat(lueu01): views — vessel/parcel/log endpoints; drop route/system/dashboard/split

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Frontend — vessel/parcel/logbook page with reload-persist

**Files:**
- Rewrite: `modules/LUEU01/lueu01.html` (replace entire file)
- Delete: `modules/LUEU01/lueu01_dashboard.html`

**Interfaces:**
- Consumes: endpoints from Task 3.
- Produces: a single page; persists `{vcn_id, expanded:[parcel_op_id...]}` in `localStorage['lueu_sel']` and `?vcn=` in the URL.

- [ ] **Step 1: Write `modules/LUEU01/lueu01.html`**

Structure (follow VCN01/LDUD01 template conventions — same `{% extends %}`/head/Tabulator CDN as those files; copy the surrounding boilerplate from `modules/LDUD01/ldud01.html` head):

```html
{% extends "base.html" %}
{% block content %}
<div style="display:flex;gap:12px;height:calc(100vh - 120px);">
  <!-- Pane 1: vessels -->
  <div id="vesselPane" style="width:240px;overflow:auto;border-right:1px solid #e2e8f0;"></div>
  <!-- Pane 2: parcels + logbooks -->
  <div id="parcelPane" style="flex:1;overflow:auto;padding:0 8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;">
      <h3 id="vesselTitle" style="margin:0;">Select a vessel</h3>
      <button id="refreshBtn" onclick="refreshInPlace()">↻ Refresh</button>
    </div>
    <div id="parcelList"></div>
  </div>
</div>

<script>
  const permissions = {{ permissions|tojson }};
  const canEdit = !!(permissions.can_edit || permissions.can_add);
  let masters = {equipment:[], delays:[], uom:{names:[],default:''}, berths:[], incharge:[], operators:[]};
  let selected = {vcn_id:null, expanded:[]};
  let vessels = [];
  const subTables = {};   // parcel_op_id -> Tabulator

  function saveSel() {
    localStorage.setItem('lueu_sel', JSON.stringify(selected));
    const u = new URL(window.location); u.searchParams.set('vcn', selected.vcn_id ?? ''); history.replaceState(null,'',u);
  }
  function loadSel() {
    try { selected = JSON.parse(localStorage.getItem('lueu_sel')) || selected; } catch(e){}
    const q = new URL(window.location).searchParams.get('vcn');
    if (q) selected.vcn_id = parseInt(q);
  }

  async function loadMasters() {
    const [eq,dl,uo,be,inc,ops] = await Promise.all([
      fetch('/api/module/LUEU01/equipment').then(r=>r.json()),
      fetch('/api/module/LUEU01/delays').then(r=>r.json()),
      fetch('/api/module/LUEU01/uom').then(r=>r.json()),
      fetch('/api/module/LUEU01/berths').then(r=>r.json()),
      fetch('/api/module/LUEU01/shift-incharge').then(r=>r.json()),
      fetch('/api/module/LUEU01/shift-operators').then(r=>r.json()),
    ]);
    masters = {equipment:eq, delays:dl, uom:uo, berths:be, incharge:inc, operators:ops};
  }

  async function loadVessels() {
    vessels = await fetch('/api/module/LUEU01/vessels').then(r=>r.json());
    const pane = document.getElementById('vesselPane');
    pane.innerHTML = vessels.map(v =>
      `<div class="vessel-row${v.vcn_id===selected.vcn_id?' active':''}"
            style="padding:8px;cursor:pointer;border-bottom:1px solid #f1f5f9;"
            onclick="selectVessel(${v.vcn_id})">
         <div style="font-weight:600;">${v.vessel_name||'—'}</div>
         <div style="font-size:11px;color:#64748b;">${v.vcn_doc_num} · ${v.parcel_count} parcel(s)</div>
       </div>`).join('') || '<div style="padding:8px;color:#94a3b8;">No vessels with started parcels.</div>';
  }

  function currentVessel() { return vessels.find(v=>v.vcn_id===selected.vcn_id); }

  async function selectVessel(vcnId) {
    selected.vcn_id = vcnId;
    if (!selected.expanded) selected.expanded = [];
    saveSel(); await renderParcels(); loadVessels();
  }

  async function renderParcels() {
    const v = currentVessel();
    document.getElementById('vesselTitle').textContent = v ? `${v.vessel_name} — ${v.vcn_doc_num}` : 'Select a vessel';
    const list = document.getElementById('parcelList');
    if (!selected.vcn_id) { list.innerHTML=''; return; }
    const parcels = await fetch(`/api/module/LUEU01/parcels/${selected.vcn_id}`).then(r=>r.json());
    list.innerHTML = parcels.map(p => {
      const pct = p.declared_qty>0 ? Math.min(100, Math.round(p.logged_qty/p.declared_qty*100)) : 0;
      return `<div class="parcel-card" style="border:1px solid #e2e8f0;border-radius:6px;margin:8px 0;">
        <div style="padding:8px;display:flex;justify-content:space-between;cursor:pointer;" onclick="toggleParcel(${p.parcel_op_id})">
          <div><b>${p.parcel_no}</b> — ${p.cargo_name}
            <span style="font-size:11px;color:${p.status==='Completed'?'#15803d':'#c2410c'};">● ${p.status}</span></div>
          <div style="font-size:12px;">${p.logged_qty} / ${p.declared_qty} ${p.uom} (${pct}%)</div>
        </div>
        <div id="log-wrap-${p.parcel_op_id}" style="display:${selected.expanded.includes(p.parcel_op_id)?'block':'none'};padding:0 8px 8px;">
          ${canEdit?`<button onclick="addLogRow(${p.parcel_op_id}, '${(v&&v.berth_name)||''}')">+ Add</button>
                    <button onclick="saveLog(${p.parcel_op_id})">Save</button>`:''}
          <div id="log-table-${p.parcel_op_id}"></div>
        </div></div>`;
    }).join('') || '<div style="color:#94a3b8;padding:8px;">No started parcels.</div>';
    // init grids for already-expanded parcels (restored after reload)
    for (const pid of selected.expanded) initLogTable(pid);
  }

  function toggleParcel(pid) {
    const i = selected.expanded.indexOf(pid);
    if (i>=0) { selected.expanded.splice(i,1); document.getElementById(`log-wrap-${pid}`).style.display='none'; }
    else { selected.expanded.push(pid); document.getElementById(`log-wrap-${pid}`).style.display='block'; initLogTable(pid); }
    saveSel();
  }

  function logColumns(defaultBerth) {
    const list = vals => ({values: vals, autocomplete:true, allowEmpty:true, listOnEmpty:true});
    return [
      {title:"Date", field:"entry_date", editor:canEdit?"input":false, width:110},
      {title:"From", field:"from_time", editor:canEdit?"input":false, width:80},
      {title:"To", field:"to_time", editor:canEdit?"input":false, width:80},
      {title:"Qty", field:"quantity", editor:canEdit?"number":false, hozAlign:"right", width:90},
      {title:"UOM", field:"quantity_uom", editor:canEdit?"list":false, editorParams:list(masters.uom.names), width:80},
      {title:"Medium", field:"medium", editor:canEdit?"list":false,
        editorParams:{values:['Equipment','Direct Pipe']}, width:120},
      {title:"Equipment", field:"equipment_name", width:130,
        editor:function(cell,onR,ok,cx){ // editable only when medium=Equipment
          if (cell.getRow().getData().medium!=='Equipment'){ cx(); return document.createElement('div'); }
          return Tabulator.prototype.modules.edit.editors.list.call(this,cell,onR,ok,cx,list(masters.equipment));
        },
        formatter:c=>c.getRow().getData().medium==='Equipment'?(c.getValue()||''):'<span style="color:#cbd5e1">—</span>'},
      {title:"Delay", field:"delay_name", editor:canEdit?"list":false, editorParams:list(masters.delays), width:130},
      {title:"Shift", field:"shift", editor:canEdit?"list":false, editorParams:{values:['A','B','C']}, width:70},
      {title:"Operator", field:"operator_name", editor:canEdit?"list":false, editorParams:list(masters.operators), width:120},
      {title:"Incharge", field:"shift_incharge", editor:canEdit?"list":false, editorParams:list(masters.incharge), width:120},
      {title:"Berth", field:"berth_name", editor:canEdit?"list":false, editorParams:list(masters.berths), width:120},
      {title:"Remarks", field:"remarks", editor:canEdit?"input":false, width:150},
      canEdit?{title:"", width:40, formatter:()=> '<button>X</button>', cellClick:(e,c)=>deleteLogRow(c.getRow())}:null
    ].filter(Boolean);
  }

  function initLogTable(pid) {
    if (subTables[pid]) return;
    const v = currentVessel();
    subTables[pid] = new Tabulator(`#log-table-${pid}`, {
      layout:"fitDataFill", height:220,
      ajaxURL:`/api/module/LUEU01/log/${pid}`,
      columns: logColumns((v&&v.berth_name)||'')
    });
  }

  function currentShift() { const h=new Date().getHours(); return h>=6&&h<14?'A':h>=14&&h<22?'B':'C'; }

  function addLogRow(pid, defaultBerth) {
    const t = subTables[pid]; if(!t) return;
    const rows = t.getRows();
    const prevTo = rows.length ? rows[rows.length-1].getData().to_time : '';
    t.addRow({parcel_op_id:pid, entry_date:new Date().toISOString().slice(0,10),
              from_time:prevTo||'', shift:currentShift(), medium:'Direct Pipe',
              quantity_uom:masters.uom.default, berth_name:defaultBerth}, false);
  }

  async function saveLog(pid) {
    const t = subTables[pid]; if(!t) return;
    for (const row of t.getRows()) {
      const d = row.getData();
      const res = await fetch('/api/module/LUEU01/log/save', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({...d, parcel_op_id:pid})});
      const j = await res.json();
      if (j.id && !d.id) row.update({id:j.id});
    }
    renderParcels();  // refresh progress bars
  }

  async function deleteLogRow(row) {
    const d = row.getData();
    if (!d.id) { row.delete(); return; }
    if (!confirm('Delete this row?')) return;
    await fetch('/api/module/LUEU01/log/delete', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids:[d.id]})});
    row.delete();
  }

  async function refreshInPlace() {
    for (const pid of Object.keys(subTables)) { subTables[pid].destroy(); delete subTables[pid]; }
    await renderParcels();
  }

  (async function init(){
    loadSel(); await loadMasters(); await loadVessels();
    if (selected.vcn_id) await renderParcels();
  })();
</script>
{% endblock %}
```

- [ ] **Step 2: Delete the dashboard template**

```bash
git rm modules/LUEU01/lueu01_dashboard.html
```

- [ ] **Step 3: Syntax-check the inline JS**

Run:
```bash
python - <<'EOF'
import re,subprocess,os
html=open('modules/LUEU01/lueu01.html',encoding='utf-8').read()
scripts=re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>',html,re.S)
js='\n;\n'.join(scripts); js=re.sub(r'\{\{.*?\}\}','0',js,flags=re.S); js=re.sub(r'\{%.*?%\}','',js,flags=re.S)
open('.tmp.js','w',encoding='utf-8').write(js)
r=subprocess.run(['node','--check','.tmp.js'],capture_output=True,text=True)
print('LUEU01 JS:', 'OK' if r.returncode==0 else 'FAIL\n'+r.stderr[:600]); os.remove('.tmp.js')
EOF
```
Expected: `LUEU01 JS: OK`. If the custom Equipment editor (Step 1) fails `node --check` or Tabulator's internal editor call is unavailable, replace that column's editor with a plain `editor:"list"` over `masters.equipment` and rely on `save_log` blanking equipment when medium≠Equipment (already enforced server-side) — re-run the check.

- [ ] **Step 4: Commit**

```bash
git add modules/LUEU01/lueu01.html
git commit -m "feat(lueu01): vessel/parcel/logbook UI with reload-persisted selection; remove dashboard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Remove CRM01 + PSM01 modules

**Files:**
- Modify: `app.py` (remove `crm01`/`psm01` imports + `register_blueprint`)
- Modify: `templates/base.html` (remove CRM01/PSM01 menu links)
- Delete: `modules/CRM01/`, `modules/PSM01/`

**Interfaces:**
- Produces: app boots with no CRM01/PSM01 blueprints or menu entries.

- [ ] **Step 1: Find the exact lines**

Run:
```bash
grep -n "crm01\|CRM01\|psm01\|PSM01" app.py
grep -n "CRM01\|PSM01" templates/base.html
```
Expected: the import lines (`from modules.CRM01 import bp as crm01_bp ...`, same for psm01), their `register_blueprint(...)` lines, and menu `<a>`/`<li>` entries in base.html.

- [ ] **Step 2: Remove those lines**

Edit `app.py`: delete the two import lines (`crm01_bp`/`crm01_info`, `psm01_bp`/`psm01_info`) and their `app.register_blueprint(crm01_bp)` / `app.register_blueprint(psm01_bp)` lines (and any `crm01_info`/`psm01_info` usage in a module-list/menu registry — remove those entries too).
Edit `templates/base.html`: delete the CRM01 and PSM01 navigation entries.

- [ ] **Step 3: Delete the module packages**

```bash
git rm -r modules/CRM01 modules/PSM01
```

- [ ] **Step 4: Verify the app imports with no dangling refs**

Run:
```bash
python -c "import app; print('app import OK')"
grep -rn "CRM01\|PSM01\|crm01\|psm01" app.py templates/base.html || echo "(no residual refs)"
```
Expected: `app import OK`; the grep prints `(no residual refs)`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: remove CRM01 (Conveyor Route) and PSM01 (Port System) masters

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Migration + boot + JS**

Run:
```bash
alembic upgrade head 2>&1 | tail -2
python -c "import app; print('boot OK')"
python -c "from modules.LUEU01 import model as m; print('vessels:', len(m.get_vessels_with_started_parcels()))"
python - <<'EOF'
import re,subprocess,os
html=open('modules/LUEU01/lueu01.html',encoding='utf-8').read()
scripts=re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>',html,re.S)
js='\n;\n'.join(scripts); js=re.sub(r'\{\{.*?\}\}','0',js,flags=re.S); js=re.sub(r'\{%.*?%\}','',js,flags=re.S)
open('.tmp.js','w',encoding='utf-8').write(js)
print('JS:', 'OK' if subprocess.run(['node','--check','.tmp.js']).returncode==0 else 'FAIL'); os.remove('.tmp.js')
EOF
```
Expected: migration at head `jnpa19_lueu_parcel_logbook`, `boot OK`, vessel count prints, `JS: OK`.

- [ ] **Step 2: Confirm dropped objects are gone and no module reads them**

Run:
```bash
grep -rn "conveyor_routes\|port_systems\|lueu_lines" modules/LUEU01 && echo "FOUND (should be none in LUEU01)" || echo "LUEU01 clean"
```
Expected: `LUEU01 clean`.

- [ ] **Step 3: Update the deferred-work memory**

Append to the existing rebuild-pending note that RP01 shift/daily/custom reports now also break on the dropped `lueu_lines` (see [[rp01-finv01-rebuild-pending]]), so a future session knows it's intentional.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(lueu01): verification pass + deferred-work note

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **RP01 will break** (shift_report, daily_ops, custom_report query `lueu_lines` + route/system). This is intentional and deferred — do not try to fix RP01 in this plan.
- The custom Equipment-cell editor in Task 4 is the one fragile spot; the fallback (plain list editor + server-side blanking) is acceptable and already wired.
- If `app.py` registers modules through a list/registry (not just `register_blueprint`), remove the CRM01/PSM01 entries there too (Task 5 Step 2).
```
