"""Configure Pages using existing Git credentials; never print credentials."""
import json
import subprocess
import urllib.request
import urllib.error
from pages_common import load_local_env, public_config

REPO = 'douky4/diplomka_ai_test'

def api(path, method='GET', data=None):
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, check=True)
    credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        data=json.dumps(data).encode() if data is not None else None, method=method,
        headers={'Authorization':'Bearer '+credentials['password'], 'Accept':'application/vnd.github+json',
                 'Content-Type':'application/json', 'User-Agent':'quiz-pages-deployment'})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None

def configure():
    load_local_env()
    config = public_config()
    for name, value in [('SUPABASE_URL', config['url']), ('SUPABASE_PUBLISHABLE_KEY', config['key'])]:
        try:
            api('/actions/variables/'+name, 'PATCH', {'name':name, 'value':value})
        except urllib.error.HTTPError as error:
            if error.code != 404: raise
            api('/actions/variables', 'POST', {'name':name, 'value':value})
    try:
        api('/pages', 'GET')
    except urllib.error.HTTPError as error:
        if error.code != 404: raise
        api('/pages', 'POST', {'build_type':'workflow'})
    else:
        api('/pages', 'PUT', {'build_type':'workflow'})
    print('GitHub Pages configured; public Supabase variables saved.')

if __name__ == '__main__':
    configure()
