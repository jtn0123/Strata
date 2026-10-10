#!/usr/bin/env python3
"""Summarize captured scheduler plans, never treat rebuild dumps as execution counts."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

PREFIX = re.compile(r'\d+\.\d{2}\.\d{3}\.\d{3} [DIWE] ')
NODE = re.compile(r'^node #\s*(\d+) \((.{10})\): (.{20}) \((.{5})\) \[(.{5}) (.{8})\] use=(\d+),c=([01]):(.*)$')
SPLIT = re.compile(r'^## SPLIT #(\d+): (\S+) # (\d+) inputs(.*)$')
INPUT = re.compile(r'\[(.+?) \(\s*([^()]*)\)\]')


def analyze(folder):
    capture = json.loads((folder/'capture.json').read_text())
    if capture['status'] != 'passed': raise ValueError('Capture did not pass')
    raw = (folder/'native.log').read_bytes()
    requests = []
    for request in capture['requests']:
        begin, end = request['log_begin'], request['log_end']
        if not capture['startup_log_end'] <= begin < end <= len(raw): raise ValueError('Request byte range invalid')
        text = raw[begin:end].decode()
        # The asynchronous app logger can interleave a complete SSE debug notice
        # between chunks of one GGML line. Delete that known notice, reconnecting
        # only its trailing newlines; raw evidence is retained unchanged.
        text = re.sub(r'\d+\.\d{2}\.\d{3}\.\d{3} [DIWE] srv\s+operator\(\): http: streamed chunk: data: [^\n]*\n+', '', text)
        text = PREFIX.sub('', text)
        # An unrelated parser's direct stderr notice can precede a scheduler node
        # without a newline. Recover only the precise native node marker.
        text = re.sub(r'(?<!\n)(?=node #\s*\d+ \()', '\n', text)
        blocks = re.split(r'(?=^## SPLIT #0:)', text, flags=re.M)[1:]
        plans = []
        for block in blocks:
            nodes, splits = [], []
            for line in block.splitlines():
                if line.startswith('## SPLIT #'):
                    m = SPLIT.fullmatch(line)
                    if not m: raise ValueError('Unknown split format')
                    index, backend, count, inputs = m.groups()
                    fields = [dict(name=name.strip(), displayed_size=size.strip()) for name,size in INPUT.findall(inputs)]
                    if len(fields) != int(count): raise ValueError('Split input inventory incomplete')
                    splits.append(dict(index=int(index), backend=backend, inputs=fields, count=int(count)))
                if line.startswith('node #'):
                    m = NODE.fullmatch(line)
                    if not m: raise ValueError('Unknown node format')
                    index,op,name,size,backend,cause,use,active,sources = m.groups()
                    nodes.append(dict(index=int(index), op=op.strip(), name=name.strip(), displayed_size=size.strip(),
                                      backend=backend.strip(), active=bool(int(active)), sources=sources))
            if [s['index'] for s in splits] != list(range(len(splits))) or not nodes: raise ValueError('Incomplete graph plan')
            target = [n for n in nodes if n['name']=='model.input_embed' and n['active']]
            helper = [n for n in nodes if n['name']=='mtp_tok_embd-48' and n['active']]
            if bool(target) == bool(helper): raise ValueError('Graph role ambiguous')
            role = 'target' if target else 'helper'
            cpu_active = [n for n in nodes if n['backend']=='CPU' and n['active']]
            inactive = Counter((n['backend'],n['op']) for n in nodes if not n['active'])
            embedding = (target or helper)[0]
            if role == 'target' and not any(n['op']=='GET_ROWS' and n['active'] and 'per_layer_token_embd' in n['sources'] for n in nodes):
                raise ValueError('Target PLE gather missing')
            plans.append(dict(role=role, embedding_displayed_size=embedding['displayed_size'],
                split_backends=[s['backend'] for s in splits], split_inputs=[s['count'] for s in splits],
                splits=splits, cpu_active_ops=dict(Counter(n['op'] for n in cpu_active)),
                inactive_ops={f'{backend}:{op}':count for (backend,op),count in sorted(inactive.items())},
                first_nodes=nodes[:8]))
        if not any(p['role']=='target' for p in plans) or not any(p['role']=='helper' for p in plans):
            raise ValueError('Request lacks target/helper rebuilt plans')
        requests.append(dict(workload=request['workload'], plans=plans, plan_dumps=len(plans)))
    return dict(engine=capture['engine']['engine'], capture_sha256=hashlib.sha256((folder/'capture.json').read_bytes()).hexdigest(),
                log_sha256=hashlib.sha256(raw).hexdigest(), requests=requests)


def main():
    folder = Path(sys.argv[1])
    records = [analyze(folder/name) for name in ('m5-copy','m5-embedding')]
    parity = json.loads((folder/'parity.json').read_text())
    if parity['status'] != 'passed': raise ValueError('Output comparison absent')
    rows = []
    for a,b in zip(records[0]['requests'],records[1]['requests']):
        if a['workload'] != b['workload']: raise ValueError('Workloads differ')
        for role in ('target','helper'):
            groups = []
            for request in (a,b):
                selected = [p for p in request['plans'] if p['role']==role]
                groups.append({size:[p for p in selected if p['embedding_displayed_size']==size]
                               for size in sorted({p['embedding_displayed_size'] for p in selected})})
            if groups[0].keys() != groups[1].keys(): raise ValueError('Compared shape-label coverage differs')
            for size in groups[0]:
                profiles = []
                for group in groups:
                    plans=group[size]
                    signatures = {(tuple(p['split_backends']),tuple(p['split_inputs']),tuple(sorted(p['cpu_active_ops'].items()))) for p in plans}
                    if len(signatures)!=1: raise ValueError('Plan signature varies at compared shape label')
                    p=plans[0]
                    profiles.append(dict(split_backends=p['split_backends'],split_inputs=p['split_inputs'],
                        cpu_active_ops=p['cpu_active_ops'], inactive_ops=p['inactive_ops'],
                        plan_dump_count=len(plans), representative_inputs=[s['inputs'] for s in p['splits']]))
                rows.append(dict(workload=a['workload'],role=role,embedding_displayed_size=size,
                                 control=profiles[0],candidate=profiles[1]))
    target=[r for r in rows if r['role']=='target'];helper=[r for r in rows if r['role']=='helper']
    if not all(r['control']['split_backends']==r['candidate']['split_backends']==['CPU','MTL0']
        and r['control']['split_inputs']==[0,27] and r['candidate']['split_inputs']==[0,30]
        and r['control']['cpu_active_ops']==r['candidate']['cpu_active_ops']=={'GET_ROWS':2} for r in target):
        raise ValueError('Target plan conclusion is not uniform')
    if not all(r['control']['split_backends']==r['candidate']['split_backends']==['CPU','MTL0','CPU','MTL0']
        and r['control']['split_inputs']==r['candidate']['split_inputs']==[0,14,2,2]
        and r['control']['cpu_active_ops']==r['candidate']['cpu_active_ops'] for r in helper):
        raise ValueError('Helper plan changed')
    result=dict(schema=1,status='passed',decision='park-no-removed-handoffs-more-planned-inputs',parity=parity,
        shape_matched_comparisons=len(rows),target_comparisons=len(target),helper_comparisons=len(helper),
        comparisons=rows, captures=records, analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations='Scheduler debug2 dumps plans only when rebuilt/reallocated, not every execution. Startup reserve plans excluded using UTF8-safe request byte ranges. Size strings and node names are truncated; no exact transferred bytes or hidden-state/logit equality measured. No speed result can be derived from these logged timings.')
    (folder/'topology.json').write_text(json.dumps(result,indent=2)+'\n')
    (folder/'analyzer.py').write_bytes(Path(__file__).read_bytes())
    print({k:v for k,v in result.items() if k not in ('captures','comparisons')})


if __name__=='__main__': main()
