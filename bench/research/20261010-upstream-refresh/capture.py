#!/usr/bin/env python3
"""Read-only GitHub refresh; save dated primary evidence without changing runtimes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
REPOS = {
    'parent': ('Niko1221/Strata', 'main'),
    'native-mac': ('liangxiwei/Strata-for-mac', 'metal-mac'),
    'shruxx-mac': ('shruxx/StrataForMac', None),
    'mlx-16gb': ('migueldevops-real/Strata-Apple-Silicon-16GB', None),
    'pinned-mac': ('jinzy0623/Strata-macOS', None),
    'metalfit': ('shruxx/metalfit', None),
    'meld': ('MeldlabsAI/meld-turbo', None),
    'tierpack': ('vamzi/tierpack', None),
    'architect': ('architectds/Strata', 'best'),
    'lighttransport': ('lighttransport/Strata', None),
    'xdcgh': ('xdcgh/Strata', None),
    'llama': ('ggml-org/llama.cpp', None),
}

def fetch(label, endpoint):
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode:
        return label, {'error': result.stderr.strip(), 'endpoint': endpoint}
    return label, json.loads(result.stdout)

def batch(requests):
    data = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, key, endpoint) for key, endpoint in requests.items()]
        for future in as_completed(futures):
            key, value = future.result()
            (ROOT / (key + '.json')).write_text(json.dumps(value, indent=2) + '\n')
            data[key] = value
    return data

def main():
    stamp = datetime.now(timezone.utc).isoformat()
    requests = {name + '-repo': 'repos/' + repo for name, (repo, _) in REPOS.items()}
    requests.update({
        'parent-pulls': 'repos/Niko1221/Strata/pulls?state=all&sort=updated&direction=desc&per_page=100',
        'parent-issues': 'repos/Niko1221/Strata/issues?state=all&sort=updated&direction=desc&per_page=100',
        'parent-branches': 'repos/Niko1221/Strata/branches?per_page=100',
        'forks-newest': 'repos/Niko1221/Strata/forks?sort=newest&per_page=100',
        'forks-oldest': 'repos/Niko1221/Strata/forks?sort=oldest&per_page=100',
        'llama-pulls': 'repos/ggml-org/llama.cpp/pulls?state=all&sort=updated&direction=desc&per_page=100',
        **{'search-' + term: 'search/repositories?q=' + quote('Strata ' + term + ' in:name,description fork:true') + '&sort=updated&per_page=100'
           for term in ('mac', 'metal', 'apple', 'mlx')},
    })
    metadata = batch(requests)
    requests = {}
    for name, (repo, branch) in REPOS.items():
        info = metadata[name + '-repo']
        branch = branch or info.get('default_branch')
        if branch:
            requests[name + '-commits'] = 'repos/' + repo + '/commits?sha=' + quote(branch, safe='') + '&per_page=12'
        if name != 'llama':
            requests[name + '-branches'] = 'repos/' + repo + '/branches?per_page=100'
    evidence = batch(requests)
    summary = {'checked_utc': stamp, 'completed_utc': datetime.now(timezone.utc).isoformat(),
               'method': 'Read-only GitHub REST API via gh; no downloads/builds/models/benchmarks/runtime changes.',
               'heads': {}, 'errors': {}}
    for name, (repo, branch) in REPOS.items():
        commits = evidence.get(name + '-commits', {})
        if isinstance(commits, list) and commits:
            row = commits[0]
            summary['heads'][name] = {'repository': repo, 'branch': branch or metadata[name + '-repo']['default_branch'],
                'sha': row['sha'], 'date': row['commit']['committer']['date'],
                'subject': row['commit']['message'].splitlines()[0], 'url': row['html_url']}
    for key, value in {**metadata, **evidence}.items():
        if isinstance(value, dict) and 'error' in value:
            summary['errors'][key] = value['error']
    (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
