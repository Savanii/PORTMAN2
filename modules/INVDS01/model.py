from database import get_db, get_cursor

# Two masters, same shape: invoice series carry a Start At (the cut-off this
# series numbers from), pro-forma series do not — pro-forma numbers are typed
# in at print time, so there is no sequence to seed.
TABLE = 'invoice_doc_series'
PROFORMA_TABLE = 'proforma_doc_series'
TABLES = {TABLE: True, PROFORMA_TABLE: False}   # table -> has start_seq


def _table(table):
    """Guard the table name before it goes into an f-string query."""
    if table not in TABLES:
        raise ValueError(f'Unknown doc series table: {table}')
    return table


def _cols(table):
    return 'id, name, prefix, is_default' + (', start_seq' if TABLES[table] else '')


def get_data(page=1, size=20, table=TABLE):
    table = _table(table)
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    total = cur.fetchone()['count']
    cur.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT %s OFFSET %s', (size, (page-1)*size))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows], total

def get_all(table=TABLE):
    table = _table(table)
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute(f"SELECT {_cols(table)} FROM {table} ORDER BY name ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_data(data, table=TABLE):
    table = _table(table)
    conn = get_db()
    cur = get_cursor(conn)
    row_id = data.get('id')
    name = data.get('name', '')
    prefix = (data.get('prefix', '') or '').upper().strip()
    is_default = bool(data.get('is_default', False))

    if is_default:
        cur.execute(f"UPDATE {table} SET is_default = FALSE WHERE is_default = TRUE")

    cols = ['name', 'prefix', 'is_default']
    vals = [name, prefix, is_default]
    if TABLES[table]:
        cols.append('start_seq')
        vals.append(_start_seq(data.get('start_seq')))

    if row_id:
        sets = ', '.join(f'{c}=%s' for c in cols)
        cur.execute(f"UPDATE {table} SET {sets} WHERE id=%s", vals + [row_id])
    else:
        cur.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id", vals)
        row_id = cur.fetchone()['id']

    conn.commit()
    conn.close()
    return row_id


def _start_seq(value):
    """Start At as a positive int, or None for 'no cut-off on this series'.

    Blank and 0 both mean none — a series that starts at 0 is not a thing, and
    treating it as one would make the floor a no-op in a confusing way."""
    if value in (None, '', 0, '0'):
        return None
    try:
        seq = int(value)
    except (TypeError, ValueError):
        raise ValueError('Start At must be a whole number')
    if seq < 1:
        raise ValueError('Start At must be 1 or more')
    return seq

def delete_data(row_id, table=TABLE):
    table = _table(table)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id=%s', (row_id,))
    conn.commit()
    conn.close()
