#!/usr/bin/env python3
"""Correct parser-only rejection from immutable complete diagnostic evidence."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from engines import sha256,verify_engine
from model_provenance import assert_unchanged
from validate_offline import require_pass
from capture import parse_native,compare


def main():
    folder=Path(sys.argv[1]).resolve(); require_pass()
    parser=Path(__file__).with_name('capture.py')
    parser_hash=sha256(parser); source_hash=sha256(__file__)
    records=[]
    for mode in ('stock','off'):
        current=folder/mode; path=current/'capture.json'; r=json.loads(path.read_text())
        if mode=='off' and (r['status']!='failed' or r.get('error')!='ValueError: Effective cap, successful helper steps or target verification differs'):
            raise ValueError('Only the known complete parser-only rejection can be recovered')
        if sha256(current/'runner.py')!=r['runner_sha256'] or verify_engine(r['engine']['engine'])!=r['engine']:
            raise ValueError('Frozen runner or native engine provenance differs')
        m=r['memory']
        if len(r['requests'])!=22 or m['guard'] or m['swap_growth_bytes'] or not m['monitor_healthy'] or not m['child_exited']:
            raise ValueError('Incomplete capture or resource gate failure')
        assert_unchanged(r['model_proof'])
        r['original_status']=r['status']; r['original_error']=r.pop('error',None)
        r['reanalysis']=dict(original_record_sha256=sha256(path),native_log_sha256=sha256(current/'native.log'),
            parser_sha256=parser_hash,analyzer_sha256=source_hash,models_rerun=False,
            reason='Raw offered remaining/context budget is separate from configured max3 effective helper width; canonical explicit option order; cancellation and target dispatch proof')
        r['_folder']=current
        try: parse_native(r,(current/'native.log').read_text())
        finally: r.pop('_folder')
        r['status']='passed'; records.append(r)
        (current/'reanalysis.json').write_text(json.dumps(r,indent=2)+'\n')
    pair=compare(*records)
    if pair['status']!='passed': raise ValueError('Stock/off exact parity failed')
    if sha256(parser)!=parser_hash or sha256(__file__)!=source_hash: raise ValueError('Reanalysis source changed')
    require_pass(); (folder/'corrected-analysis.json').write_text(json.dumps(pair,indent=2)+'\n')
    (folder/'corrected-parser.py').write_bytes(parser.read_bytes())
    (folder/'reanalysis-runner.py').write_bytes(Path(__file__).read_bytes())
    print(pair,flush=True)


if __name__=='__main__': main()
