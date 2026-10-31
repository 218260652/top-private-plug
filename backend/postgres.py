"""Small DB-API adapter preserving the existing parameterized Store queries.

Postgres uses a transaction-scoped advisory lock where SQLite used BEGIN
IMMEDIATE. This preserves atomic redemption, ticket consumption and quota
updates across the web process and a separately hosted Linux gateway.
"""
import re
import sqlite3
from contextlib import contextmanager


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        value = self.cursor.fetchone()
        return None if value is None else Row(value)

    def __iter__(self):
        return (Row(row) for row in self.cursor)


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, values=()):
        if sql == 'BEGIN IMMEDIATE':
            sql = 'SELECT pg_advisory_xact_lock(74707001)'
        else:
            sql = sql.replace('?', '%s')
            sql = sql.replace('up=up+excluded.up,down=down+excluded.down',
                              'up=usage.up+excluded.up,down=usage.down+excluded.down')
        values = tuple(int(v) if isinstance(v, bool) else v for v in values)
        return Cursor(self.connection.execute(sql, values))

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)


class Database:
    def __init__(self, url, schema='public'):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', schema):
            raise ValueError('Invalid database schema')
        self.schema = schema
        self.pool = ConnectionPool(url, min_size=0, max_size=4, timeout=20,
                                   kwargs={'row_factory': dict_row, 'connect_timeout': 10},
                                   max_lifetime=300, open=True)

    @contextmanager
    def connect(self):
        import psycopg
        from psycopg_pool import PoolTimeout
        try:
            with self.pool.connection() as connection:
                with connection.transaction():
                    connection.execute('SET LOCAL search_path TO "' + self.schema + '"')
                    yield Connection(connection)
        except (psycopg.Error, PoolTimeout) as error:
            # Pool timeouts should return a safe JSON 503, not an HTML 500.
            sqlstate = error.sqlstate if isinstance(error, psycopg.Error) else None
            raise sqlite3.OperationalError('Persistent database operation failed (SQLSTATE ' + (sqlstate or 'connection') + ')') from None

    def close(self):
        self.pool.close()


def schema_sql(sqlite_schema):
    schema = sqlite_schema.replace('INTEGER', 'BIGINT')
    for table in ['usage', 'audit']:
        schema = schema.replace('CREATE TABLE IF NOT EXISTS ' + table + '(id BIGINT PRIMARY KEY',
                                'CREATE TABLE IF NOT EXISTS ' + table + '(id BIGSERIAL PRIMARY KEY')
    return schema
