#!/usr/bin/env python3
"""Publish verified local results into the existing report and decision register."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_memory import assert_no_model_server, snapshot
from engines import sha256
from validate_offline import fingerprint, require_pass
from lab import server_command


def write(path, value): path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    state=json.loads((HERE/'tracking.json').read_text())
    app=json.loads((HERE/'launcher-verification.json').read_text())
    frozen=json.loads((HERE/'frozen.json').read_text())
    counts=json.loads((HERE/'model-verification.json').read_text())
    assert state['status']=='completed' and state['winner']==['reduce']
    assert app['status']=='passed' and not app['swap_growth_bytes']
    assert all(app['ports_closed_after_stop'].values())
    assert len(app['checks'])==16 and all(c['passed'] for c in app['checks'])
    assert app['streaming_check']['passed'] and app['native_memory']['child_exited']
    assert sha256(HERE/'frozen.json')==state['frozen_sha256']
    for name,key in [('plan.json','plan_sha256'),('sequence.py','runner_sha256'),('test_sequence.py','test_sha256')]:
        assert sha256(HERE/name)==frozen[key]
    expected=server_command('flash',8096,4096,ubatch=512,cache_type='f16',spec='draft-mtp',draft=3,
                            draft_placement='mixed',draft_model='mtp_shared_packed_q3',engine='m5-small-stack',
                            draft_threads=8,draft_p_min=0.0)
    assert app['native_command']==expected
    app['native_command_matches_validated_profile']=True
    write(HERE/'launcher-verification.json',app)
    assert_no_model_server();require_pass()
    assert fingerprint()==frozen['source_pins']
    for name,digest in frozen['source_pins'].items(): assert sha256(HERE/'source'/name)==digest
    promotion=json.loads((HERE/'promotion.json').read_text())
    assert sha256(ROOT/'Start Strata.command')==promotion['launcher_sha256']
    assert sha256(ROOT/promotion['rollback_path'])==frozen['original_launcher_sha256']
    promotion.update(status='installed and application verified', application_verification=str((HERE/'launcher-verification.json').relative_to(ROOT)),
                     application_server_left_running=False, generic_cli_source_unchanged=True)
    write(HERE/'promotion.json',promotion)
    lines=['# Sequential W02 validation and P07 rollout','',
           'P07 is installed in the no-argument `Start Strata.command` launcher. Qwen3.8-Flash-Next Q2_0, packed shared Q3 helper, mixed placement, eight helper CPU workers, depth3/confidence0, Tensor API on, F16 KV,4K context,batch512. Explicit launcher arguments retain generic CLI behavior, including the small model.', '',
           'W02 remains a possible throughput tradeoff. The new frozen screen gained0.5835% code and0.7114% prose TPS, but prose had a12.659958ms worst launch-pair first-token delay, above the prospectively declared10ms ceiling. Average delay was4.254ms code/6.207ms prose. No W02 confirmation or combination was launched. Old results and their relative rule remain unchanged.', '',
           'P07 previously passed two independent short-prompt,256-output brackets (+0.6107% code/+0.7921% prose TPS in confirmation). The new long-prompt and32-output safety brackets pass resources, parity, cached policy and all material-regression guards. The new long cohort qualifies generation on both tasks in one bracket; it is not independently confirmed for that cohort. Short32-output code has a positive aggregate gain below its variation gate, so claim safety rather than a confirmed gain there.', '',
           '| Fresh test | Task/input | Output tokens | Baseline TPS | Candidate TPS | TPS gain | Reply quicker | Average first-token delay | Decision |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for item in state['runs']:
        path=ROOT/item['path']/'comparison.json'
        assert sha256(path)==item['comparison_sha256']
        record=json.loads(path.read_text())
        for row in record['launch_summary']:
            if row['cached']:continue
            a,b,d=row['control'],row['candidate'],row['vs_control']
            decision='startup ceiling exceeded' if row['regressions'] else 'safety passed' if item['label']!='w02-fresh-screen' else 'code-only screen qualifies'
            lines.append(f"| {item['label']} | {row['workload']}/{row['input_tokens']} | {item['output_tokens']} | {a['generation_tok_s']:.4f} | {b['generation_tok_s']:.4f} | {d['generation_increase_percent']:+.4f}% | {d['total_time_reduction_percent']:+.4f}% | {1000*(b['ttft_s']-a['ttft_s']):+.3f}ms | {decision} |")
    lines += ['',f"All {counts['launches']} full-model benchmark launches passed {counts['checks']} answer/cache checks and exact parity on {counts['parity']} fresh/warmup/cache output signatures. {counts['fresh']} fresh measured records, {counts['warmups']} fresh warmups, {counts['cached']} cached records. Zero new swap in every launch. No source, model, precision or workload changes during measurement; no pooling historical data or summing percentages.", '',
              'Targeted non-admin model-cache cleanup recovered2.795456GiB before the campaign, with sustained35.514GiB minimum available and zero new swap. It ran once, before all arms. It preserves the model files and does not close T3 or WiFiman. The cold first load is not a throughput gain.', '',
              'The promoted launcher passed16 actual Strata API English answer checks at temperatures0/0.6 plus SSE streaming, exact selected engine/profile/native command, zero new swap and clean shutdown with8095/8096 closed. No model server remains running. `Start Strata - Original Baseline.command` retains the original launcher bytes. All changes are local; nothing committed or pushed.', '',
              'Next W02 work: investigate and change the first-token path before another fresh validation. Keep this failed general-use screen in the ledger. Do not rerun unchanged source to seek a passing bracket or relabel it after changing tolerances.', '',
              '[Frozen protocol](plan.json), [frozen source receipt](frozen.json), [model comparisons and decisions](tracking.json), [model verification](model-verification.json), [actual app verification](launcher-verification.json), [promotion/rollback](promotion.json).']
    report=HERE/'REPORT.md';report.write_text('\n'.join(lines)+'\n')
    relative=str(HERE.relative_to(ROOT));now=datetime.now(timezone.utc).isoformat()
    tracker_path=ROOT/'bench/small-gain-candidates.json';tracker=json.loads(tracker_path.read_text())
    tracker['sequential_followup']=dict(status='completed; P07 installed and app verified', report=relative+'/REPORT.md',
                                      tracking=relative+'/tracking.json', winner=['reduce'],
                                      w02_status='throughput gain; held above fixed startup ceiling', combined_launched=False,
                                      benchmark_launches=12, benchmark_swap_growth_bytes=0,
                                      app_verification=relative+'/launcher-verification.json', promotion=relative+'/promotion.json')
    for item in tracker['candidates']:
        if item['id'] in ('P07','W02'):
            item['sequential_followup']=dict(report=relative+'/REPORT.md',runs=[r for r in state['runs'] if
                        (r['label'].startswith('p07') if item['id']=='P07' else r['label'].startswith('w02'))])
    write(tracker_path,tracker)
    ledger_md=ROOT/'bench/EXPERIMENT-LEDGER.md';marker='## Sequential fixed-latency validation and P07 rollout (2026-10-10)'
    if marker in ledger_md.read_text():raise ValueError('Ledger result already published')
    ledger_md.write_text(ledger_md.read_text()+'\n'+marker+'\n\n'+
        '- Authorization: "Do them sequentially." New absolute W02 startup rule declared before fresh GPU/model runs; original plan/results remain unchanged. Frozen plan: `'+relative+'/plan.json`.\n'+
        '- **W02:** freshABBA code59.7203→60.0688TPS (+0.5835%), prose40.0623→40.3473TPS (+0.7114%). Average startup delays4.254/6.207ms; worst code/prose launch-pair delays6.243/12.660ms. Prose exceeds fixed10ms ceiling. Valid throughput tradeoff, held for general use; no confirmation/stacking. Revisit only after a material first-token-path change with a new frozen protocol.\n'+
        '- **P07:** prior independent short256-output confirmation retained (+0.6107/+0.7921% TPS). New long safety: code45.8500→46.1872 (+0.7356%), prose46.8321→47.1436 (+0.6651%); generation qualifies both, one bracket only. New short32-output safety: code63.9946→64.5608 (+0.8848%, below its variation gate), prose52.4660→52.8550 (+0.7415%). Neither safety cohort has material latency/reply/generation regression; no cached follow-up flags.\n'+
        '- **Resources/verification:** one non-admin read-only model-cache cleanup, +2.7955GiB available; unchanged34GiB admission and zero-swap guards.12 benchmark launches,312 answer/cache checks,192 output signatures, all exact and zero new swap. No native/source/math/model/precision changes;5 load-free protocol checks passed.\n'+
        '- **Promotion:** normal no-argument `Start Strata.command` now selects `m5-small-stack/small-reduce` and the measured helper settings. Actual Strata API16 English checks plus SSE streaming passed, native command matches selected configuration, zero new swap, both ports close. Original bytes retained in `Start Strata - Original Baseline.command`. Generic CLI source/explicit arguments preserved; no server remains running; no commit/push.\n'+
        '- Evidence: ['+relative+'/REPORT.md](results/20261010-small-gains-stack/REPORT.md); raw comparisons, launch receipts, guard histories, frozen source archive, promotion and app proof linked there.\n')
    ledger_path=ROOT/'bench/experiment-ledger.json';ledger=json.loads(ledger_path.read_text())
    detail=dict(status='completed; P07 installed and application verified',report=relative+'/REPORT.md',
                model_verification=relative+'/model-verification.json',application_verification=relative+'/launcher-verification.json',
                plan=relative+'/plan.json',tracking=relative+'/tracking.json',promotion=relative+'/promotion.json',
                benchmark_launches=12,benchmark_answer_cache_checks=312,exact_output_signatures=192,
                zero_new_swap=True,combined_launched=False,source_closure_unchanged=True)
    ledger.update(updated=now, source_sha256=sha256(ledger_md), sequential_validation=detail)
    for item in ledger['entries']:
        if item['id'] in ('P07','W02'):item['sequential_validation']=dict(detail,decision='promoted' if item['id']=='P07' else 'held startup tradeoff; throughput gain retained')
    write(ledger_path,ledger)
    readme=ROOT/'README.md';text=readme.read_text()
    old='Latest pass: [actual draft-cap early stopping and fixed two guesses]'
    text=text.replace(old,'Earlier pass: [actual draft-cap early stopping and fixed two guesses]',1)
    intro='Local, measured experiments for an Apple M5 Pro with 48 GiB unified memory. This workspace keeps Strata\'s existing Mac interface and uses a revision-pinned native llama.cpp Metal server behind it. All inference stays on the Mac.'
    latest='Latest: [P07 is validated and installed in the normal launcher](bench/results/20261010-small-gains-stack/REPORT.md). Its prior independent confirmation adds +0.61% code/+0.79% prose generation over the direct-copy profile. New longer-prompt and32-token answer safety checks pass;12 full-model launches,312 answer/cache checks and192 exact output signatures have zero new swap. The actual Strata API passes16 English answer checks plus streaming and clean shutdown. W02 adds +0.58–0.71% TPS but exceeds the declared10ms startup ceiling on prose, so stacking remains untested. Double-click `Start Strata.command` for P07; `Start Strata - Original Baseline.command` restores the earlier profile. No model server is left running.'
    text=text.replace(intro,intro+'\n\n'+latest,1)
    text=text.replace('.venv/bin/python scripts/run.py flash\n```','"./Start Strata.command"\n```',1)
    text=text.replace('The normal profile uses 4K context, processing batch 512, conversation caching and no MTP.',
        'The normal no-argument launcher uses P07 with the packed shared Q3 helper, depth-three MTP, mixed placement, eight helper CPU workers, Tensor API enabled, F16 KV,4K context, processing batch512 and conversation caching. Explicit arguments retain the generic `scripts/run.py` behavior. The rollback launcher retains the original prediction-off profile.')
    text=text.replace('The normal launcher keeps prediction off. [Exact comparisons]',
        'The current normal-launcher validation is recorded above. [Exact comparisons]')
    text=text.replace('so this is an optional workload choice and the normal launcher retains its original engine/settings.',
        'which is a limitation of those historical comparisons; the current normal-launcher configuration has separate validation above.')
    readme.write_text(text)
    final=dict(status='complete; local promotion verified',source_closure_unchanged=fingerprint()==frozen['source_pins'],
               launcher_sha256=sha256(ROOT/'Start Strata.command'),report_sha256=sha256(report),
               model_verification_sha256=sha256(HERE/'model-verification.json'),
               application_verification_sha256=sha256(HERE/'launcher-verification.json'),
               ledger_sha256=sha256(ledger_path),tracker_sha256=sha256(tracker_path),host=snapshot(),
               no_model_server_remaining=True,committed=False,pushed=False,time_utc=now)
    write(HERE/'final-verification.json',final)
    print('Saved:',report,flush=True)


if __name__=='__main__':main()
