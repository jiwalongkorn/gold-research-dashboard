#!/usr/bin/env python3
import json, re, shutil, subprocess
from pathlib import Path

ROOT = Path('/root/gold-research')
NORM = ROOT / 'raw-data/normalized/browser-snapshots'

def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)

status = json.loads((NORM / 'latest-status.json').read_text())
quality_path = NORM / 'data-quality.json'
if quality_path.exists():
    quality = json.loads(quality_path.read_text())
    if quality.get('quality') != 'pass' or quality.get('snapshot_id') != status.get('snapshot_id'):
        raise SystemExit('publish skipped: data quality is not pass for latest snapshot')
if status.get('status') != 'fresh' or not status.get('snapshot_id'):
    raise SystemExit('publish skipped: latest collector status is not fresh')
snap = status['snapshot_id']
src = NORM / snap
if not src.is_dir():
    raise SystemExit(f'publish failed: snapshot not found: {snap}')

# Rebuild derived artifacts from the same successful snapshot.
run('.venv/bin/python3', 'scripts/build_snapshot_index.py')
run('.venv/bin/python3', 'scripts/build_multiseries_summary.py')

for target in (ROOT / 'public-data', ROOT / 'dashboard/public-data'):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copytree(src, target / snap)
    shutil.copy2(NORM / 'latest-status.json', target / 'latest-status.json')
    if quality_path.exists(): shutil.copy2(quality_path, target / 'data-quality.json')

manifest = json.loads((ROOT / 'dashboard/series-manifest.json').read_text())
for item in manifest.get('series', []):
    item['path'] = f'./public-data/{snap}/{item["id"]}'
(ROOT / 'series-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
manifest_dashboard = json.loads(json.dumps(manifest))
for item in manifest_dashboard.get('series', []):
    item['path'] = f'./public-data/{snap}/{item["id"]}'
(ROOT / 'dashboard/series-manifest.json').write_text(json.dumps(manifest_dashboard, indent=2) + '\n')

index = json.loads((ROOT / 'dashboard/snapshot-index.json').read_text())
latest = next(x for x in index['snapshots'] if x['id'] == snap)
public_index = {'schema_version': index['schema_version'], 'generated_at_utc': index['generated_at_utc'], 'snapshots': [{**latest, 'path': f'./public-data/{snap}'}]}
(ROOT / 'snapshot-index.json').write_text(json.dumps(public_index, indent=2) + '\n')
(ROOT / 'dashboard/snapshot-index.json').write_text(json.dumps(public_index, indent=2) + '\n')
(ROOT / 'multiseries-summary.json').write_text((ROOT / 'dashboard/multiseries-summary.json').read_text())

# Root Pages entrypoints use root-relative public data; dashboard copies use dashboard-relative paths.
for name in ('index.html', 'comparison.html'):
    src_html = ROOT / 'dashboard' / name
    root_html = src_html.read_text()
    (ROOT / name).write_text(root_html.replace('../public-data/', './public-data/').replace('../raw-data/normalized/browser-snapshots/latest-status.json', './public-data/latest-status.json'))

# Never publish runtime identifiers or credential-like material.
scan = '\n'.join(p.read_text(errors='ignore') for p in [ROOT/'index.html', ROOT/'comparison.html', ROOT/'series-manifest.json', ROOT/'snapshot-index.json', ROOT/'multiseries-summary.json'])
if re.search(r'qsid\s*=|qsid%3d|password\s*[:=]|api[_-]?key\s*[:=]|BEGIN (RSA|OPENSSH) PRIVATE KEY', scan, re.I):
    raise SystemExit('publish blocked: sensitive pattern found in public artifacts')

# Block before staging so a failed scan cannot enter a commit.
scan = '\n'.join(p.read_text(errors='ignore') for p in [ROOT/'index.html', ROOT/'comparison.html', ROOT/'series-manifest.json', ROOT/'snapshot-index.json', ROOT/'multiseries-summary.json'])
if re.search(r'qsid\s*=|qsid%3d|password\s*[:=]|api[_-]?key\s*[:=]|BEGIN (RSA|OPENSSH) PRIVATE KEY', scan, re.I):
    raise SystemExit('publish blocked: sensitive pattern found in public artifacts')

run('.venv/bin/python3', 'scripts/build_historical_summary.py')
run('.venv/bin/python3', 'scripts/build_snapshot_compare.py')
run('.venv/bin/python3', 'scripts/build_strike_compare.py')
run('.venv/bin/python3', 'scripts/build_data_quality_history.py')
run('.venv/bin/python3', 'scripts/build_distribution_summary.py')
run('.venv/bin/python3', 'scripts/research_replay_scaffold.py')
run('.venv/bin/python3', 'scripts/research_replay.py')
shutil.copy2(ROOT / 'reports/research-replay.json', ROOT / 'dashboard/research-replay.json')
for name in ('historical-summary.json','snapshot-compare.json','strike-compare.json','data-quality-history.json','distribution-summary.json'):
    shutil.copy2(ROOT / 'dashboard' / name, ROOT / name)

# Publish only curated Pages artifacts. Git credentials stay in the VPS credential helper.
run('git', 'add', 'index.html', 'research.html', 'comparison.html', 'series-manifest.json', 'snapshot-index.json', 'multiseries-summary.json', 'public-data', 'dashboard/index.html', 'dashboard/comparison.html', 'dashboard/series-manifest.json', 'dashboard/snapshot-index.json', 'dashboard/multiseries-summary.json', 'dashboard/historical-summary.json', 'historical-summary.json', 'dashboard/snapshot-compare.json', 'snapshot-compare.json', 'dashboard/strike-compare.json', 'strike-compare.json', 'dashboard/data-quality-history.json', 'data-quality-history.json', 'dashboard/distribution-summary.json', 'distribution-summary.json', 'reports/research-hypothesis-template.json', 'dashboard/research-replay.json', 'reports/research-replay.json', 'dashboard/public-data')
changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode != 0
if changed:
    run('git', 'commit', '-m', f'Publish snapshot {snap}')
    run('git', 'push', 'origin', 'main')

# Never publish runtime identifiers or credential-like material.
scan = '\n'.join(p.read_text(errors='ignore') for p in [ROOT/'index.html', ROOT/'comparison.html', ROOT/'series-manifest.json', ROOT/'snapshot-index.json', ROOT/'multiseries-summary.json'])
if re.search(r'qsid\s*=|qsid%3d|password\s*[:=]|api[_-]?key\s*[:=]|BEGIN (RSA|OPENSSH) PRIVATE KEY', scan, re.I):
    raise SystemExit('publish blocked: sensitive pattern found in public artifacts')
print(json.dumps({'status': 'ready', 'snapshot_id': snap}))
