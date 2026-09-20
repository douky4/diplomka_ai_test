"""Exercise real DB functions inside a transaction that is always rolled back."""
import os
import uuid
import json
import urllib.request
import psycopg
from pages_common import load_local_env, public_config

def verify():
    load_local_env()
    config = public_config()
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=15) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(73190521)')
                cur.execute('DELETE FROM public.allocation_state')
                ids = [str(uuid.uuid4()), str(uuid.uuid4())]
                assignments = []
                for participant in ids:
                    cur.execute('SET LOCAL ROLE anon')
                    cur.execute('SELECT public.quiz_create(%s,25,%s,%s)', (participant,'jiné','denni'))
                    assert cur.fetchone()[0]['participant_id'] == participant
                    cur.execute('SELECT public.quiz_create(%s,25,%s,%s)', (participant,'jiné','denni'))
                    assert cur.fetchone()[0]['participant_id'] == participant
                    cur.execute('SELECT public.quiz_resume(%s)', (participant,))
                    result = cur.fetchone()[0]
                    assert result['next_index'] == 0 and len(result['images']) == 15
                    assert all(set(i) == {'image_id','src','type'} for i in result['images'])
                    for index, image in enumerate(result['images']):
                        cur.execute('SELECT public.quiz_answer(%s,%s,%s,%s,5,%s)',
                                    (participant,index,image['image_id'],'ai','integration test'))
                        assert cur.fetchone()[0]['success']
                    cur.execute('SELECT public.quiz_resume(%s)', (participant,))
                    assert cur.fetchone()[0]['next_index'] == 15
                    cur.execute('RESET ROLE')
                    cur.execute('SELECT subject_id,snapshot::jsonb->>\'correct\' FROM public.quiz_assignments WHERE participant_id=%s',(participant,))
                    choices = dict(cur.fetchall())
                    assert len(choices) == 15 and sum(v == 'ai' for v in choices.values()) in (7,8)
                    assignments.append(choices)
                assert all(assignments[0][k] != assignments[1][k] for k in assignments[0])
                cur.execute('SET LOCAL ROLE anon')
                cur.execute('SAVEPOINT denied')
                try:
                    cur.execute('SELECT * FROM public.answers')
                    raise AssertionError('Anonymous table read was allowed')
                except psycopg.errors.InsufficientPrivilege:
                    cur.execute('ROLLBACK TO SAVEPOINT denied')
                cur.execute('SELECT public.quiz_admin_login(%s)',('wrong-password-test',))
                assert 'error' in cur.fetchone()[0]
                cur.execute('SELECT public.quiz_admin_login(%s)',(os.environ['ADMIN_PASSWORD'],))
                token = cur.fetchone()[0]['token']
                cur.execute('SELECT public.quiz_admin_data(%s)',(token,))
                report = cur.fetchone()[0]
                assert len(report['images']) >= 30
                cur.execute('SELECT public.quiz_admin_logout(%s)',(token,))
                assert cur.fetchone()[0]['success']
        finally:
            conn.rollback()
    req = urllib.request.Request(config['url']+'/rest/v1/rpc/quiz_status',data=b'{}',
        headers={'apikey':config['key'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        status = json.load(response)
        assert status['ready'] and status['image_count']==30 and status['question_count']==15
    print('PASS: pair allocation, retries, 30 answer writes, resume, table protection, admin login/export/logout, live RPC. Test records rolled back.')

if __name__ == '__main__':
    verify()
