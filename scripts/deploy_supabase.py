"""Back up current research records and install the Pages RPC backend atomically."""
import json
import os
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from pages_common import ROOT, catalog, dataset_key, load_local_env, public_config


def deploy():
    load_local_env()
    public_config()  # Reject any accidentally supplied secret key before deployment.
    dsn = os.environ.get('DATABASE_URL', '')
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not dsn or not password:
        raise ValueError('Set DATABASE_URL and ADMIN_PASSWORD in local .env. Do not commit that file.')
    items = catalog()
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=15) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(73190521)')
            backup = {}
            for table in ('participants', 'answers', 'quiz_assignments', 'allocation_state'):
                cursor.execute('SELECT to_regclass(%s) AS name', ('public.' + table,))
                if cursor.fetchone()['name']:
                    cursor.execute(sql.SQL('SELECT * FROM public.{}').format(sql.Identifier(table)))
                    backup[table] = cursor.fetchall()
            destination = ROOT / '.local' / 'backups'
            destination.mkdir(parents=True, exist_ok=True)
            backup_file = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            backup_file.write_text(json.dumps(backup, ensure_ascii=False, default=str), encoding='utf-8')
            cursor.execute('CREATE SCHEMA IF NOT EXISTS extensions')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions')
            cursor.execute("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto'")
            crypto_schema = cursor.fetchone()['nspname']
            migration = (ROOT / 'supabase/migrations/001_pages_quiz.sql').read_text(encoding='utf-8')
            migration = migration.replace('__CRYPTO_SCHEMA__', sql.Identifier(crypto_schema).as_string(conn))
            cursor.execute(migration)
            cursor.execute('UPDATE quiz_private.catalog SET active=false')
            for entry in items:
                q = entry['question']
                cursor.execute('''INSERT INTO quiz_private.catalog(image_id,subject_id,label,active,asset_path,snapshot)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(image_id) DO UPDATE SET
                    subject_id=excluded.subject_id,label=excluded.label,active=excluded.active,
                    asset_path=excluded.asset_path,snapshot=excluded.snapshot''',
                    (q['image_id'],q['subject_id'],q['correct'],entry['active'],entry['asset_path'],json.dumps(q,ensure_ascii=False)))
            cursor.execute(sql.SQL('''INSERT INTO quiz_private.settings(singleton,dataset_key,admin_hash)
                VALUES (true,%s,{c}.crypt(%s,{c}.gen_salt('bf',10)))
                ON CONFLICT(singleton) DO UPDATE SET dataset_key=excluded.dataset_key,admin_hash=excluded.admin_hash''')
                .format(c=sql.Identifier(crypto_schema)), (dataset_key(items), password))
            cursor.execute('SELECT public.quiz_status() AS status')
            status = cursor.fetchone()['status']
            if not status['ready'] or status['image_count'] != 30 or status['question_count'] != 15:
                raise ValueError('Backend validation failed; rolling back.')
    print('Supabase migration committed; 30 images / 15 pairs. Research data backup:', backup_file)


if __name__ == '__main__':
    deploy()
