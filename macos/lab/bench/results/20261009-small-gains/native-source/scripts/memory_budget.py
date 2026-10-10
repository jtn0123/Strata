#!/usr/bin/env python3
"""Explain saved weight/allocation budgets without loading a model or advising pages."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from lab import ROOT

MIB=1024**2


def allocations(text):
    role="target"; entries={}; lazy=[]
    cache_counts={}
    loads=0
    for line in text.splitlines():
        if 'load_tensors: loading model tensors' in line:
            loads+=1; role='target' if loads==1 else 'helper'
        match=re.search(r'(\S+)\s+(model|KV|RS|compute|output) buffer size\s*=\s*([0-9.]+)\s*MiB',line)
        if not match: continue
        backend,kind,size=match.groups()
        value=round(float(size)*MIB)
        if role=='target' and kind=='model' and backend=='CPU_Mapped' and value>20*1024**3:
            lazy.append({'role':role,'backend':backend,'bytes':value,'kind':'lazy-table-file-mapping'});continue
        key=(role,backend,kind)
        entry={'role':role,'backend':backend,'kind':kind,'bytes':value}
        if kind=='KV':
            # Attention and the pooled-key indexer own distinct caches, but
            # both log the same backend/kind. Draft caches are separate too.
            index=cache_counts.get(key,0)
            cache_counts[key]=index+1
            entry['allocation_index']=index
            key=(*key,index)
        entries[key]=entry
    values=list(entries.values())
    private=[e for e in values if e['kind']!='model']
    return {'entries':values,'lazy_file_mappings':lazy,'known_private_buffer_bytes':sum(e['bytes'] for e in private),
            'missing_roles':[r for r in ('target','helper') if not any(e['role']==r for e in values)],
            'limits':'Each startup KV buffer is a separate cache allocation; other reservations keep the last log per role/backend/kind. File mappings are not physical RAM. Model ranges can overlap; do not sum them or treat this as peak footprint. Rounded MiB logs omit other allocations.'}


def report(inventory, registry, log=None):
    tensors=[t for shard in inventory['shards'] for t in shard['tensors']]
    lazy=[t for t in tensors if 'per_layer_token_embd' in t['name']]
    resident=[t for t in tensors if t not in lazy]
    helper=registry['mtp_shared_packed_q3']['files']
    known=allocations(log) if log is not None else None
    result={'schema':1,'models_loaded':False,'gpu_tests_run':False,'header_inventory_only':True,
            'target_unique_tensor_bytes':sum(t['size_bytes'] for t in resident),
            'lazy_lookup_file_bytes':sum(t['size_bytes'] for t in lazy),
            'helper_file_bytes':sum(f['size_bytes'] for f in helper),
            'observed_allocations':known,'admission_decision':'not-an-admission-controller',
            'policy':{'minimum_available_before_full_model_bytes':34*1024**3,'new_swap_required_bytes':0,
                'cache_precision':'f16','context_trial':[4096,8192]},
            'unmeasured':['resident lazy-table pages','Metal/driver allocations','8K QSA/scratch growth','app/OS/background footprint'],
            'limits':'Target weights and helper weights share the Mac RAM budget. The SSD table is separately mapped and touched pages still use RAM. An 8K fit is unproved until actual allocations, headroom, quality and zero-swap checks pass.'}
    if known:
        result['known_helper_repack_bytes']=sum(e['bytes'] for e in known['entries'] if e['role']=='helper' and e['backend']=='CPU_REPACK')
        result['conservative_component_sum_bytes']=result['target_unique_tensor_bytes']+result['helper_file_bytes']+result['known_helper_repack_bytes']+known['known_private_buffer_bytes']
        result['component_sum_limits']='Accounting estimate, not measured physical RAM or a lower bound. Includes the helper file plus repacked buffers; mappings/residency can overlap or be nonresident.'
    return result


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--log',type=Path);ap.add_argument('--save',type=Path)
    args=ap.parse_args(argv)
    path=ROOT/'bench/results/flash-gguf-inventory.json'
    registry=json.loads((ROOT/'config/models.json').read_text())
    result=report(json.loads(path.read_text()),registry,args.log.read_text() if args.log else None)
    result['inventory_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    result['historical_log']=str(args.log) if args.log else None
    if args.save:
        args.save.parent.mkdir(parents=True,exist_ok=True)
        args.save.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(f"Header weights: {result['target_unique_tensor_bytes']/1024**3:.2f} GiB; helper file: {result['helper_file_bytes']/1024**3:.2f} GiB; lazy lookup: {result['lazy_lookup_file_bytes']/1024**3:.2f} GiB on disk.")
    print('Saved allocations explain components; actual 8K fit and peak memory remain untested.')


if __name__=='__main__':main()
