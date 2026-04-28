from database import get_db, get_cursor

def get_data(page=1, size=50, filters=None):
    conn = get_db()
    cur = get_cursor(conn)
    try:
        cur.execute('SELECT COUNT(*) FROM terminal_master')
        total = cur.fetchone()['count']
        cur.execute('SELECT * FROM terminal_master ORDER BY terminal_name LIMIT %s OFFSET %s',
                    [size, (page - 1) * size])
        return [dict(r) for r in cur.fetchall()], total
    finally:
        conn.close()

def save(data):
    conn = get_db()
    cur = get_cursor(conn)
    row_id = data.get('id')
    if row_id:
        cur.execute('UPDATE terminal_master SET terminal_name=%s, description=%s, is_active=%s WHERE id=%s',
                    [data['terminal_name'], data.get('description'), data.get('is_active', True), row_id])
    else:
        cur.execute('INSERT INTO terminal_master (terminal_name, description, is_active) VALUES (%s, %s, %s) RETURNING id',
                    [data['terminal_name'], data.get('description'), data.get('is_active', True)])
        row_id = cur.fetchone()['id']
    conn.commit()
    conn.close()
    return row_id

def delete(row_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('DELETE FROM terminal_master WHERE id=%s', (row_id,))
    conn.commit()
    conn.close()

def get_all_active():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('SELECT id, terminal_name FROM terminal_master WHERE is_active=TRUE ORDER BY terminal_name')
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
