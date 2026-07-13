from database import get_db, get_cursor

TABLE = 'port_master'

def get_all():
    """Ports with their codes for dropdowns (search by code or name)."""
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(f"SELECT name, port_code, is_default_discharge FROM {TABLE} WHERE name IS NOT NULL AND name != '' ORDER BY name ASC")
    rows = [{'name': r['name'], 'port_code': r['port_code'] or '',
             'is_default_discharge': bool(r['is_default_discharge'])} for r in cur.fetchall()]
    conn.close()
    return rows

def get_data(page=1, size=20):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(f'SELECT COUNT(*) FROM {TABLE}')
    total = cur.fetchone()['count']
    cur.execute(f'SELECT * FROM {TABLE} ORDER BY id DESC LIMIT %s OFFSET %s', (size, (page-1)*size))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows, total

def save_data(data):
    conn = get_db()
    cur = get_cursor(conn)
    name = data.get('name', '')
    port_code = data.get('port_code') or None
    is_def = bool(data.get('is_default_discharge'))

    # only one default discharge port — clear every row first (the partial unique
    # index rejects a second TRUE within the same statement otherwise)
    if is_def:
        cur.execute(f"UPDATE {TABLE} SET is_default_discharge=FALSE")

    if data.get('id'):
        cur.execute(f"UPDATE {TABLE} SET name=%s, port_code=%s, is_default_discharge=%s WHERE id=%s",
                    [name, port_code, is_def, data['id']])
        row_id = data['id']
    else:
        cur.execute(f"INSERT INTO {TABLE} (name, port_code, is_default_discharge) VALUES (%s, %s, %s) RETURNING id",
                    [name, port_code, is_def])
        row_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    return row_id

def bulk_insert(rows):
    # ponytail: CSV upload never sets is_default_discharge — that stays a single-row radio in the grid
    conn = get_db()
    cur = get_cursor(conn)
    inserted = 0
    for row in rows:
        if not row.get('name'):
            continue
        cur.execute(f"INSERT INTO {TABLE} (name, port_code, is_default_discharge) VALUES (%s, %s, FALSE)",
                    [row['name'], row.get('port_code') or None])
        inserted += 1
    conn.commit()
    conn.close()
    return inserted

def delete_data(row_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(f'DELETE FROM {TABLE} WHERE id=%s', (row_id,))
    conn.commit()
    conn.close()
