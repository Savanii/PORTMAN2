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


_HAS_SEQ_WIDTH = None


def has_seq_width(cur=None):
    """Whether invoice_doc_series carries seq_width yet (migration jnpa72).

    Same tolerance FIN01.lookup_seed applies: the column is read and written
    only where it exists, so INVDS01 keeps working on a database that has not
    been migrated -- it just cannot pad, which is the pre-migration behaviour.
    Cached: the answer cannot change inside a running process.
    """
    global _HAS_SEQ_WIDTH
    if _HAS_SEQ_WIDTH is None:
        conn = None if cur is not None else get_db()
        if conn is not None:
            cur = get_cursor(conn)
        try:
            cur.execute("""SELECT 1 FROM information_schema.columns
                           WHERE table_name='invoice_doc_series' AND column_name='seq_width'""")
            _HAS_SEQ_WIDTH = cur.fetchone() is not None
        except Exception:
            cur.connection.rollback()
            _HAS_SEQ_WIDTH = False
        finally:
            if conn is not None:
                conn.close()
    return _HAS_SEQ_WIDTH


def _cols(table):
    cols = 'id, name, prefix, is_default'
    if TABLES[table]:
        cols += ', start_seq'
        if has_seq_width():
            cols += ', seq_width'
    return cols


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
        seq, width = _start_seq(data.get('start_seq'))
        cols.append('start_seq')
        vals.append(seq)
        if has_seq_width():
            cols.append('seq_width')
            vals.append(width)

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
    """(start number, printed width) from what was typed in Start At.

    The width is how many digits the operator wrote, so "0418" numbers as
    PREFIX/0418 while "418" numbers as PREFIX/418. It is carried separately
    because start_seq is an integer and an integer cannot hold a leading zero
    — which is how 0418 used to come out as 418.

    Blank and 0 both mean no cut-off — a series that starts at 0 is not a
    thing, and treating it as one would make the floor a no-op confusingly.
    """
    if value is None:
        return None, None
    text = str(value).strip()
    if text in ('', '0'):
        return None, None
    try:
        seq = int(text)
    except (TypeError, ValueError):
        raise ValueError('Start At must be a whole number')
    if seq < 1:
        raise ValueError('Start At must be 1 or more')
    # Only a typed leading zero asks for padding; "418" stays unpadded so
    # existing series are unaffected.
    width = len(text) if text.startswith('0') else None
    return seq, width

def delete_data(row_id, table=TABLE):
    table = _table(table)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id=%s', (row_id,))
    conn.commit()
    conn.close()
