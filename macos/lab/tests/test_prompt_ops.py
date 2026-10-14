"""N00 log parsing and the prompt-operation driver's plan, without a model or native process."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import profile_prompt_ops as driver
from prompt_ops import (
    chunk_sizes,
    command_buffers,
    dispatch_graphs,
    fusion_counts,
    graph_times,
    inventory,
    label_graphs,
    median_by_size,
    request_graphs,
    summarize,
    target_context,
)

P = '0.00.248.292 D ggml_metal_op_encode_impl: '
NOOP = f'{P}node[    5] - VIEW         (noop)'


def node(index, op, name, concurrent=False):
    return f"{P}node[{index:5d}] - {op:<12} {name:<12} {'(concurrent)' if concurrent else ''}"


def tensor(role, kind, shape, name='t'):
    dims = ', '.join(f'{d:5d}' for d in shape)
    return f'{P}{role} - {kind:>4} [{dims}] [    4,     8,    16,    16], 1, {name}'


def fuse(count):
    return f'{P}              fuse {count} ops'


def graph(tokens, layers=2, op='MUL_MAT'):
    """Node 0 unencoded, node 1 a norm fused with node 2, node 3 unencoded, node 5 a noop, then one ADD per layer."""
    lines = [node(1, 'RMS_NORM', 'norm-0', True), tensor('src0', 'f32', [2560, 4, tokens, 1]),
             tensor('node', 'f32', [2560, 4, tokens, 1], 'norm-0'), fuse(2)]
    lines += [node(4, op, 'attn_q-0'), tensor('src0', 'q2_0', [2560, 4096, 1, 1]),
              tensor('src1', 'f32', [2560, tokens, 1, 1]), tensor('node', 'f32', [4096, tokens, 1, 1], 'attn_q-0'), NOOP]
    for layer in range(1, layers):
        lines += [node(5 + layer, 'ADD', f'ffn_out-{layer}', True), tensor('src0', 'f32', [2560, tokens, 1, 1]),
                  tensor('node', 'f32', [2560, tokens, 1, 1], f'ffn_out-{layer}')]
    return lines


def profile(context, graph_id, cb, start, ms, nodes=100, **extra):
    row = dict(context=context, graph=graph_id, cb=cb, original_nodes=nodes, gpu_start_s=start,
               gpu_end_s=start + ms / 1000, gpu_ms=ms, valid=True, completed=True, op_counts={'MUL_MAT': 1})
    row.update(extra)
    return 'M5_PROFILE ' + json.dumps(row)


class DispatchInventoryTests(unittest.TestCase):
    def test_graphs_split_where_node_indexes_restart_and_fusion_comes_from_dispatch_lines(self):
        graphs = dispatch_graphs(['noise', *graph(512), 'other line', *graph(512), *graph(298)])
        self.assertEqual(len(graphs), 3)
        first = graphs[0]
        self.assertEqual((first['noops'], first['unencoded']), (1, 2))
        dispatches = first['dispatches']
        self.assertEqual([d['op'] for d in dispatches], ['RMS_NORM', 'MUL_MAT', 'ADD'])
        self.assertEqual([d['fused'] for d in dispatches], [1, 0, 0])
        self.assertEqual([d['concurrent'] for d in dispatches], [True, False, True])
        self.assertEqual(dispatches[1]['name'], 'attn_q-0')
        self.assertEqual(dispatches[1]['sources'][0], {'type': 'q2_0', 'shape': [2560, 4096, 1, 1]})
        self.assertEqual(dispatches[1]['output'], {'type': 'f32', 'shape': [4096, 512, 1, 1]})
        summary = summarize(first)
        self.assertEqual((summary['layers'], summary['dispatches'], summary['barriers']), (2, 3, 1))
        self.assertEqual((summary['fused_nodes'], summary['fused_by_leader_op'], summary['unencoded_nodes']),
                         (1, {'RMS_NORM': 1}, 2))
        self.assertIn('MUL_MAT q2_0[2560, 4096, 1, 1] f32[2560, 512, 1, 1] -> f32[4096, 512, 1, 1]',
                      summary['by_shape'])

    def test_targets_carry_the_schedule_and_helpers_share_their_batch(self):
        graphs = dispatch_graphs([*graph(2), *graph(2, 1), *graph(512), *graph(512, 1), *graph(512, 1, 'MUL'),
                                  *graph(298), *graph(512)])
        labels = label_graphs(graphs, [2, 512, 298, 512])
        self.assertEqual([(label['role'][0], label['chunk'], label['tokens']) for label in labels],
                         [('t', 0, 2), ('h', 0, 2), ('t', 1, 512), ('h', 1, 512), ('h', 1, 512), ('t', 2, 298),
                          ('t', 3, 512)])
        entries = inventory(graphs, labels)
        self.assertEqual([(e['role'], e['tokens'], e['layers'], e['chunks']) for e in entries],
                         [('target', 2, 2, [0]), ('helper', 2, 1, [0]), ('target', 512, 2, [1, 3]),
                          ('helper', 512, 1, [1]), ('helper', 512, 1, [1]), ('target', 298, 2, [2])])
        self.assertEqual(label_graphs([], []), [])

    def test_schedules_that_do_not_match_the_log_are_refused(self):
        graphs = dispatch_graphs([*graph(2), *graph(2, 1), *graph(512), *graph(298)])
        cases = [(graphs, [2, 512], 'Expected 2 target graphs, found 3'),
                 ([], [2], 'Expected 1 target graphs, found 0'),
                 (graphs[1:], [2, 512, 298], 'Expected 3 target graphs, found 2'),
                 (graphs[1:], [512, 298], 'Helper graph before the first target graph'),
                 (graphs, [2, 511, 298], 'Graph 2 does not read 511 rows'),
                 (dispatch_graphs([NOOP]), [2], 'Graph 0 does not read 2 rows')]
        for subset, schedule, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                label_graphs(subset, schedule)

    def test_orphan_lines_and_graphs_without_shapes(self):
        cases = [([NOOP, tensor('src0', 'f32', [1, 1, 1, 1])], 'Tensor line without an encoded dispatch'),
                 ([NOOP, fuse(2)], 'Fusion line without an encoded dispatch'),
                 ([node(0, 'ADD', 'x'), fuse(3), node(2, 'ADD', 'y')], 'Fused nodes exceed the node-index gap')]
        for lines, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                dispatch_graphs(lines)
        unnamed = dispatch_graphs([node(0, 'ADD', '')])[0]['dispatches'][0]
        self.assertEqual((unnamed['op'], unnamed['name'], unnamed['concurrent']), ('ADD', '', False))
        lone = dispatch_graphs([node(0, 'ADD', 'x'), tensor('node', 'f32', [1, 1, 1, 1])])
        self.assertEqual(summarize(lone[0])['by_shape'], {'ADD  -> f32[1, 1, 1, 1]': 1})
        bare = dispatch_graphs([node(0, 'ADD', 'x')])
        self.assertEqual(list(summarize(bare[0])['by_shape']), ['ADD  -> -'])

    def test_fusion_statistics_are_kept_as_printed(self):
        lines = ['0.00.729 D ggml_metal_free: fusion stats:', '0.00.729 D ggml_metal_free: - RMS_NORM+MUL: 525',
                 '0.00.729 D ggml_metal_free: - RMS_NORM+MUL+ADD: 10', 'unrelated: - X: 1']
        self.assertEqual(fusion_counts(lines), {'RMS_NORM+MUL': 525, 'RMS_NORM+MUL+ADD': 10})


class CommandBufferTests(unittest.TestCase):
    def test_buffers_group_into_graphs_and_untimed_metadata_buffers_are_dropped(self):
        untimed = profile('a', 9, 0, 0, 0, valid=False, gpu_end_s=0, op_counts={'VIEW': 2})
        lines = [profile('a', 1, 0, 10.0, 2.0, 50), profile('a', 1, 1, 10.002, 3.0, 400), untimed,
                 profile('b', 1, 0, 10.0045, 1.0, 20), 'M5_PROFILE_OTHER']
        graphs = graph_times(command_buffers(lines))
        self.assertEqual([(g['context'], g['graph'], g['buffers_ms'], g['original_nodes']) for g in graphs],
                         [('a', 1, [2.0, 3.0], 400), ('b', 1, [1.0], 20)])
        self.assertAlmostEqual(graphs[0]['gpu_ms'], 5.0)
        self.assertAlmostEqual(graphs[0]['end_s'], 10.005)
        self.assertEqual(target_context(graphs), 'a')

    def test_invalid_or_untimed_computational_buffers_are_refused(self):
        bad = [profile('a', 1, 0, 0, 0, valid=False, gpu_end_s=0),
               profile('a', 1, 0, 10.0, 2.0, completed=False), profile('a', 1, 0, 10.0, 2.0, gpu_ms=5.0),
               profile('a', 1, 0, 10.0, 2.0, gpu_end_s=9.0), profile('a', 1, 0, 10.0, 2.0, gpu_ms=float('inf'))]
        for line in bad:
            with self.subTest(line=line[:80]), self.assertRaises(ValueError):
                command_buffers([line])
        with self.assertRaisesRegex(ValueError, 'No timed GPU graphs'):
            target_context([])

    def test_prompt_batches_break_where_the_server_takes_state_checkpoints(self):
        self.assertEqual(chunk_sizes(2332, 512, 512), [512, 512, 512, 284, 508, 4])
        self.assertEqual(chunk_sizes(2332, 1536, 1536), [796, 1532, 4])
        self.assertEqual(chunk_sizes(2000, 1024, 512), [1024, 460, 512, 4])
        self.assertEqual(chunk_sizes(516, 512, 512), [4, 508, 4])
        self.assertEqual((chunk_sizes(48, 512, 512), chunk_sizes(3, 512, 512)), ([44, 4], [3]))

    def test_request_windows_hold_one_target_graph_per_chunk_and_their_helpers(self):
        lines = [profile('t', 1, 0, 1.0, 20, 900), profile('h', 1, 0, 1.05, 2, 90), profile('t', 2, 0, 1.1, 100, 900),
                 profile('h', 2, 0, 1.25, 5, 90), profile('t', 3, 0, 1.3, 10, 900), profile('h', 3, 0, 1.35, 1, 90),
                 profile('t', 4, 0, 5.0, 99, 900)]
        graphs = graph_times(command_buffers(lines))
        chunks = request_graphs(graphs, 0.9, 2.0, 600, 512, 512)['chunks']
        self.assertEqual([(c['tokens'], c['gpu_ms'], c['helper_ms']) for c in chunks],
                         [(88, 20, 2), (508, 100, 5), (4, 10, 1)])
        self.assertAlmostEqual(chunks[1]['ms_per_token'], 100 / 508)
        with self.assertRaisesRegex(ValueError, 'Expected 3 target prompt graphs, found 4'):
            request_graphs(graphs, 0.9, 6.0, 600, 512, 512)
        early = graph_times(command_buffers([profile('h', 9, 0, 0.95, 1, 90), *lines]))
        with self.assertRaisesRegex(ValueError, 'Helper GPU graph before the first prompt graph'):
            request_graphs(early, 0.9, 2.0, 600, 512, 512)
        medians = median_by_size([*chunks, dict(tokens=508, gpu_ms=110, helper_ms=7)])
        self.assertEqual(medians['508'], {'samples': 2, 'gpu_ms': 105, 'ms_per_token': 105 / 508, 'helper_ms': 6})


class DriverPlanTests(unittest.TestCase):
    def test_inventory_launch_adds_only_debug_logging(self):
        with patch.object(driver, 'kept_server', return_value=['server', '--verbosity', '4', '-b', '1536']):
            self.assertEqual(driver.launch_command(1, '1536', 'inventory'), ['server', '--verbosity', '5', '-b', '1536'])
            self.assertEqual(driver.launch_command(1, '512', 'timing'), ['server', '--verbosity', '4', '-b', '1536'])
        env, settings = driver.launch_env('inventory')
        self.assertEqual((env['GGML_METAL_GRAPH_DEBUG'], env['GGML_M5_LAB_PROFILE']), ('2', '1'))
        self.assertEqual(settings['diagnostic_env'], driver.INVENTORY_ENV)
        env, settings = driver.launch_env('timing')
        self.assertNotIn('GGML_METAL_GRAPH_DEBUG', env)
        self.assertEqual((settings['diagnostic_env'], env['GGML_M5_LAB_PROFILE']), ({}, '1'))

    def test_plan_without_run_loads_nothing(self):
        output = io.StringIO()
        with patch.object(driver, 'assert_no_model_server') as guard, redirect_stdout(output):
            driver.main(['--mode', 'timing', '--profile', '512', '--profile', '1536', '--output', '/nonexistent'])
        guard.assert_not_called()
        self.assertIn('timing launches 512/1536', output.getvalue())

    def test_measure_requires_the_whole_fresh_prompt(self):
        timings = dict(prompt_n=3, prompt_ms=30.0, prompt_per_second=100.0)
        case = dict(name='short-prose', kind='prose', content='x')
        with patch.object(driver, 'request', return_value=dict(timings=timings)) as call:
            row = driver.measure('http://x', case, [1, 2, 3], 0)
        payload = call.call_args.args[2]
        self.assertEqual((payload['n_predict'], payload['cache_prompt']), (1, False))
        self.assertEqual((row['prompt_tokens'], row['prompt_ms']), (3, 30.0))
        with patch.object(driver, 'request', return_value=dict(timings=dict(timings, prompt_n=2))):
            with self.assertRaisesRegex(ValueError, 'whole fresh prompt'):
                driver.measure('http://x', case, [1, 2, 3], 0)

    def test_analysis_writes_inventory_or_chunk_timings(self):
        receipt = ['llama_context: n_batch = 512', 'llama_context: n_ubatch = 512'] * 2
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            log = [*receipt, *graph(2), *graph(2, 1), *graph(44), *graph(4), '0.1 D ggml_metal_free: - MUL_MAT+ADD: 2']
            (folder / 'native.log').write_text('\n'.join(log))
            result = dict(mode='inventory', profile='512', requests=[dict(prompt_tokens=48)])
            driver.analyze(folder, result)
            self.assertEqual(result['fusion'],
                             {'launch_patterns': {'MUL_MAT+ADD': 2}, 'fused_nodes': 4, 'unencoded_nodes': 8})
            entries = json.loads((folder / 'inventory.json').read_text())
            self.assertEqual([(e['role'], e['tokens'], e['chunks']) for e in entries],
                             [('target', 2, [0]), ('helper', 2, [0]), ('target', 44, [1]), ('target', 4, [2])])
            lines = [profile('t', 1, 0, 1.0, 20, 900), profile('t', 2, 0, 1.1, 100, 900),
                     profile('t', 3, 0, 1.3, 10, 900), profile('t', 4, 0, 3.0, 22, 900),
                     profile('t', 5, 0, 3.1, 90, 900), profile('t', 6, 0, 3.3, 12, 900)]
            (folder / 'native.log').write_text('\n'.join([*receipt, *lines]))
            requests = [dict(repeat=0, begin_monotonic_s=0.9, end_monotonic_s=2.0, prompt_tokens=600),
                        dict(repeat=1, begin_monotonic_s=2.9, end_monotonic_s=4.0, prompt_tokens=600)]
            result = dict(mode='timing', profile='512', requests=requests)
            driver.analyze(folder, result)
            self.assertEqual(result['timing']['all_requests']['508']['gpu_ms'], 95)
            self.assertEqual(result['timing']['repeats_after_first']['88'],
                             {'samples': 1, 'gpu_ms': 22, 'ms_per_token': 22 / 88, 'helper_ms': 0})
            self.assertEqual(result['actual_chunks'], {'n_batch': [512, 512], 'n_ubatch': [512, 512]})


class DriverLaunchTests(unittest.TestCase):
    """The owned launch path with every native, network and memory call replaced."""

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.frozen = dict(closure={}, models={})

    def test_requests_repeat_each_case_and_stay_inside_the_context(self):
        cases = [dict(name='a', kind='prose', content='x'), dict(name='b', kind='prose', content='y')]
        rows = iter(dict(prompt_tok_s=100.0, n=n) for n in range(10))
        result = dict(mode='timing', profile='512', requests=[])
        with patch.object(driver, 'cases', return_value=cases), \
                patch.object(driver, 'prompt_tokens', return_value=[1, 2]), \
                patch.object(driver, 'measure', side_effect=lambda *a: next(rows)) as measure, \
                redirect_stdout(io.StringIO()):
            driver.run_requests(self.folder, result, 'http://x')
        self.assertEqual([call.args[3] for call in measure.call_args_list], [0, 1, 2, 0, 1, 2])
        self.assertEqual(len(json.loads((self.folder / 'result.json').read_text())['requests']), 6)
        for tokens in ([], [1] * 4096):
            with self.subTest(tokens=len(tokens)), patch.object(driver, 'cases', return_value=cases), \
                    patch.object(driver, 'prompt_tokens', return_value=tokens):
                with self.assertRaisesRegex(ValueError, '4K context'):
                    driver.run_requests(self.folder, result, 'http://x')

    def test_run_launch_publishes_the_owned_server_and_monitor(self):
        owned = driver.OwnedServer()
        result = dict(mode='inventory', profile='1536', requests=[], models_loaded=False)
        process, monitor = object(), unittest.mock.Mock()
        guards = dict(assert_no_model_server=None, check_frozen=None, wait_for_headroom={'s': 1},
                      preflight={'quiet': True}, power={'on_ac': True}, free_port=4321,
                      admit_model={'required': 34}, wait_ready=2.5)
        with ExitStack() as stack:
            for name, value in guards.items():
                stack.enter_context(patch.object(driver, name, return_value=value))
            stack.enter_context(patch.object(driver, 'kept_server', return_value=['server', '--verbosity', '4']))
            popen = stack.enter_context(patch.object(driver.subprocess, 'Popen', return_value=process))
            stack.enter_context(patch.object(driver, 'app_monitor', return_value=monitor))
            requests = stack.enter_context(patch.object(driver, 'run_requests'))
            driver.run_launch(self.folder, result, owned, self.frozen)
        self.assertEqual(popen.call_args.args[0], ['server', '--verbosity', '5'])
        self.assertEqual(popen.call_args.kwargs['env']['GGML_METAL_FUSION_DEBUG'], '1')
        self.assertIs(owned.process, process)
        self.assertIs(owned.monitor, monitor)
        monitor.thread.start.assert_called_once_with()
        requests.assert_called_once_with(self.folder, result, 'http://127.0.0.1:4321')
        self.assertEqual((result['models_loaded'], result['ready_s'], result['settings']['diagnostic_env']),
                         (True, 2.5, driver.INVENTORY_ENV))

    def finish(self, status, clean=True, analyze_error=None):
        owned = driver.OwnedServer(process=None, monitor=unittest.mock.Mock())
        owned.monitor.finish.return_value = {'clean': clean}
        result = dict(status=status, mode='timing', profile='512', requests=[])
        with patch.object(driver, 'assert_no_model_server'), patch.object(driver, 'check_frozen'), \
                patch.object(driver, 'clean_memory', side_effect=lambda memory: memory['clean']), \
                patch.object(driver, 'analyze', side_effect=analyze_error) as analyze:
            driver.finish_launch(self.folder, result, owned, self.frozen)
        return result, analyze

    def test_finish_accepts_only_clean_completed_launches(self):
        result, analyze = self.finish('completed')
        self.assertEqual((result['status'], result['memory']), ('passed', {'clean': True}))
        analyze.assert_called_once()
        result, analyze = self.finish('completed', clean=False)
        self.assertEqual((result['status'], result['error']), ('failed', 'RuntimeError: RAM/swap/cleanup gate failed'))
        analyze.assert_not_called()
        result, _ = self.finish('completed', analyze_error=ValueError('Expected 5 target prompt graphs, found 4'))
        self.assertEqual(result['status'], 'failed')
        result, analyze = self.finish('failed')
        self.assertEqual(result['status'], 'failed')
        analyze.assert_not_called()
        self.assertEqual(json.loads((self.folder / 'result.json').read_text())['status'], 'failed')

    def test_launch_reports_failures_after_cleanup(self):
        def finish(folder, result, owned, frozen):
            result['status'] = 'passed' if result['status'] == 'completed' else result['status']

        with patch.object(driver, 'run_launch'), patch.object(driver, 'finish_launch', side_effect=finish):
            self.assertEqual(driver.launch(self.folder / 'ok', 'timing', '512', self.frozen)['status'], 'passed')
        with patch.object(driver, 'run_launch', side_effect=RuntimeError('pressure')), \
                patch.object(driver, 'finish_launch', side_effect=finish) as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'RuntimeError: pressure'):
                driver.launch(self.folder / 'bad', 'timing', '512', self.frozen)
        cleanup.assert_called_once()

    def test_main_runs_each_profile_under_the_lab_lock(self):
        (self.folder / 'bench').mkdir()
        output = self.folder / 'out'
        with patch.object(driver, 'ROOT', self.folder), patch.object(driver, 'assert_no_model_server'), \
                patch.object(driver, 'require_pass'), patch.object(driver, 'closure', return_value={'c': 1}), \
                patch.object(driver, 'verify_models', return_value={'m': 1}), \
                patch.object(driver, 'launch', return_value=dict(status='passed')) as launch, \
                redirect_stdout(io.StringIO()):
            driver.main(['--mode', 'timing', '--profile', '512', '--profile', '1536', '--output', str(output), '--run'])
        self.assertEqual([call.args[1:3] for call in launch.call_args_list], [('timing', '512'), ('timing', '1536')])
        self.assertEqual(launch.call_args_list[1].args[0].name, 'launch-2-timing-1536')
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual((summary['launches'], summary['frozen']), (['passed', 'passed'], {'closure': {'c': 1}, 'models': {'m': 1}}))


if __name__ == '__main__':
    unittest.main()
