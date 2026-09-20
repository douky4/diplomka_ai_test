"""Build only public assets. Usage: python scripts/build_pages.py [--preview]."""
import argparse
import json
import shutil
from pathlib import Path

from pages_common import ROOT, catalog, load_local_env, public_config


def build(output, config):
    output = Path(output).resolve()
    if output != ROOT / '_site' and not output.name.startswith('pages-test-'):
        raise ValueError('Unexpected output directory')
    if output.exists():
        # Checked absolute target, wholly owned build directory only.
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in ('index.html', 'style.css', 'script.js', 'quiz-api.js', 'analytics.js', 'admin.html', 'admin.js', 'admin.css'):
        shutil.copyfile(ROOT / name, output / name)
    (output / 'config.js').write_text('window.QUIZ_CONFIG = ' + json.dumps(config) + ';\n', encoding='utf-8')
    (output / '.nojekyll').touch()
    for entry in catalog():
        dest = output / entry['asset_path']
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(entry['source'], dest)
    # Hard boundary: no CSV, prompts, Python code, database backups or .env in the artifact.
    allowed = {'.html', '.js', '.css', '.png', '.jpg', '.jpeg', '.webp'}
    for file in output.rglob('*'):
        if file.is_file() and file.name != '.nojekyll' and file.suffix not in allowed:
            raise ValueError('Unexpected public artifact: ' + file.name)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='Build without live credentials for local verification only')
    args = parser.parse_args()
    load_local_env()
    config = {'backend': 'supabase', 'url': '', 'key': ''} if args.preview else public_config()
    print('Built:', build(ROOT / '_site', config))
