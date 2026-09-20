"""Shared Pages configuration; secrets are never written into public assets."""
import base64
import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_local_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def public_config():
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = (os.environ.get('SUPABASE_PUBLISHABLE_KEY') or os.environ.get('SUPABASE_ANON_KEY', '')).strip()
    if not url.startswith('https://') or not key:
        raise ValueError('Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY).')
    if not key.startswith('sb_publishable_'):
        try:
            payload = key.split('.')[1]
            role = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))['role']
        except (IndexError, ValueError, KeyError):
            raise ValueError('Expected a publishable key or anon JWT, never a secret/service_role key.') from None
        if role != 'anon':
            raise ValueError('Only the anon role may be published. Secret/service_role keys are forbidden.')
    return {'backend': 'supabase', 'url': url, 'key': key}


def catalog():
    result = []
    with (ROOT / 'metadata.csv').open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            src = row['file_name'].replace('\\', '/')
            source = ROOT / src
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            question = {
                'image_id': row['image_id'], 'type': 'photo', 'src': src, 'correct': row['label'],
                'technique': row['technique'] or 'unknown', 'difficulty': row['difficulty'] or 'unknown',
                'source_dataset': row['source_dataset'], 'subject_id': row['subject_id'], 'metadata': row,
            }
            result.append({
                'question': question, 'source': source,
                'active': row['is_active'].lower() in ('true', '1', 'yes', 'ano') and row['split'] in ('pilot', 'test'),
                'asset_path': 'media/' + digest + source.suffix.lower(),
            })
    return result


def dataset_key(items):
    # Same representation as Flask, so both hosts share the complementary allocation block.
    questions = [entry['question'] for entry in items if entry['active']]
    return hashlib.sha256(json.dumps(questions, sort_keys=True).encode()).hexdigest()
