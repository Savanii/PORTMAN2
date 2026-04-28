from database import get_db, get_cursor

def _clean_empty(data):
    for k in list(data.keys()):
        if data[k] == '':
            data[k] = None
    return data

def get_data(page=1, size=20, filters=None):
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('SELECT COUNT(*) FROM expected_vessels')
        total = cur.fetchone()['count']
        cur.execute('SELECT * FROM expected_vessels ORDER BY id DESC LIMIT %s OFFSET %s',
                    [size, (page - 1) * size])
        return [dict(r) for r in cur.fetchall()], total
    finally:
        conn.close()

def save(data, username=None):
    _clean_empty(data)
    conn = get_db()
    cur = get_cursor(conn)
    _computed = {'id', 'vcn_id', 'doc_status', 'created_by', 'created_at'}
    row_id = data.get('id')
    if row_id:
        cols = [k for k in data if k not in _computed]
        cur.execute(
            f"UPDATE expected_vessels SET {', '.join(f'{c}=%s' for c in cols)} WHERE id=%s",
            [data[c] for c in cols] + [row_id]
        )
    else:
        data['created_by'] = username
        cols = [k for k in data if k not in {'id'}]
        cur.execute(
            f"INSERT INTO expected_vessels ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))}) RETURNING id",
            [data[c] for c in cols]
        )
        row_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    return row_id

def delete(row_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('DELETE FROM expected_vessels WHERE id=%s', (row_id,))
    conn.commit()
    conn.close()

def get_by_id(row_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM expected_vessels WHERE id=%s', (row_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def mark_moved_to_vcn(ev_id, vcn_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(
        "UPDATE expected_vessels SET vcn_id=%s, doc_status='Moved to VCN' WHERE id=%s",
        [vcn_id, ev_id]
    )
    conn.commit()
    conn.close()
