"""N00b segment-timer parsing, part fits and the segments driver mode, without a model or native process."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from engines import EXPERIMENTS
from metal_environment import configure
import profile_prompt_ops as driver
from prompt_ops import command_buffers, graph_times
from segment_ops import (
    FITTED_PARTS,
    PARTS,
    by_graph,
    chunk_parts,
    control_medians,
    fit,
    fit_parts,
    layer_parts,
    median_parts,
    output_parity,
    overhead,
    request_parts,
    segments,
)

MERGE = 'DSV4_HC_POST'
MIXER_OPS = {'recurrent': 'GATED_DELTA_NET', 'attention': 'FLASH_ATTN_EXT'}
# Milliseconds per part in the synthetic graphs.
PART_MS = {'mixer': 3.0, 'router': 1.0, 'experts': 5.0, 'combine': 0.5, 'output': 2.0}


def line(context, graph, index, cause, first, end, nodes, last_op, ops, start, ms, valid=True):
    row = dict(context=context, graph=graph, cb=index, original_nodes=nodes, gpu_start_s=start,
               gpu_end_s=start + ms / 1000, gpu_ms=ms, valid=valid, completed=True, op_counts=ops,
               segment=dict(index=index, cause=cause, first_node=first, end_node=end, dispatches=2,
                            last_op=last_op, last_name='x'))
    return 'M5_PROFILE ' + json.dumps(row)


def specs(mixers=('recurrent', 'attention')):
    """(cause, last op, op counts, ms) for each segment of a target graph: four per layer, then the output."""
    rows = []
    for layer, mixer in enumerate(mixers):
        rows += [('graph' if layer == 0 else 'hc_post', MERGE, {MIXER_OPS[mixer]: 1, MERGE: 1}, PART_MS['mixer']),
                 ('hc_post', 'MUL_MAT', {'MUL_MAT': 3}, PART_MS['router']),
                 ('experts', 'MUL_MAT_ID', {'MUL_MAT_ID': 3, 'GLU': 2}, PART_MS['experts']),
                 ('after_experts', MERGE, {'ADD': 1, MERGE: 1}, PART_MS['combine'])]
    return rows + [('hc_post', 'MUL_MAT', {'MUL_MAT': 1}, PART_MS['output'])]


def target(graph, start, rows=None, context='t', gap_s=0.0001):
    rows = specs() if rows is None else rows
    nodes = 10 * len(rows)
    lines, at = [], start
    for i, (cause, last_op, ops, ms) in enumerate(rows):
        lines.append(line(context, graph, i, cause, 10 * i, 10 * i + 10, nodes, last_op, ops, at, ms))
        at += ms / 1000 + gap_s
    return lines


def helper(graph, start, ms=0.5):
    return [line('h', graph, 0, 'graph', 0, 5, 5, 'ADD', {'ADD': 1}, start, ms)]


def parsed(lines):
    return by_graph(segments(lines))


class SegmentParsingTests(unittest.TestCase):
    def test_segment_records_cover_each_graph_and_other_lines_are_ignored(self):
        plain = 'M5_PROFILE ' + json.dumps(dict(context='t', graph=9, cb=0, original_nodes=3, gpu_start_s=1.0,
                                                gpu_end_s=1.1, gpu_ms=100.0, valid=True, completed=True,
                                                op_counts={'ADD': 1}))
        rows = segments(['noise', plain, *target(1, 1.0), *helper(1, 1.05)])
        self.assertEqual([(r['context'], r['graph']) for r in rows], [('t', 1)] * 9 + [('h', 1)])
        self.assertEqual((rows[2]['cause'], rows[2]['op_counts']['MUL_MAT_ID'], rows[2]['graph_nodes']),
                         ('experts', 3, 90))
        graphs = by_graph(reversed(rows))
        self.assertEqual([r['index'] for r in graphs[('t', 1)]], list(range(9)))

    def test_untimed_segments_and_gaps_in_node_coverage_are_refused(self):
        untimed = line('t', 1, 0, 'graph', 0, 5, 5, 'VIEW', {'VIEW': 1}, 1.0, 0.0, valid=False)
        with self.assertRaisesRegex(ValueError, 'without GPU time'):
            segments([untimed])
        broken = {
            'gap': [line('t', 1, 0, 'graph', 0, 4, 10, 'ADD', {}, 1.0, 1.0),
                    line('t', 1, 1, 'hc_post', 5, 10, 10, 'ADD', {}, 1.1, 1.0)],
            'short': [line('t', 1, 0, 'graph', 0, 9, 10, 'ADD', {}, 1.0, 1.0)],
            'index': [line('t', 1, 1, 'graph', 0, 10, 10, 'ADD', {}, 1.0, 1.0)],
        }
        for name, lines in broken.items():
            rows = segments(lines)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'do not cover its nodes once'):
                by_graph(rows)


class LayerPartTests(unittest.TestCase):
    def test_target_graphs_split_into_four_parts_per_layer_and_an_output(self):
        graph = parsed(target(1, 1.0))[('t', 1)]
        self.assertEqual(layer_parts(graph), [(0, 'recurrent'), (0, 'router'), (0, 'experts'), (0, 'combine'),
                                              (1, 'attention'), (1, 'router'), (1, 'experts'), (1, 'combine'),
                                              (1, 'output')])
        busy, span, times, dispatches = chunk_parts(graph)
        self.assertAlmostEqual(busy, 2 * (3 + 1 + 5 + 0.5) + 2)
        self.assertAlmostEqual(span, busy + 8 * 0.1, places=6)
        self.assertEqual(times, dict(recurrent=3.0, attention=3.0, router=2.0, experts=10.0, combine=1.0, output=2.0))
        self.assertEqual(dispatches, dict(recurrent=2, attention=2, router=4, experts=4, combine=4, output=2))

    def test_chunks_that_sample_no_token_have_no_output_segment(self):
        graph = parsed(target(1, 1.0, specs()[:-1]))[('t', 1)]
        self.assertEqual(layer_parts(graph)[-1], (1, 'combine'))
        busy, _, times, dispatches = chunk_parts(graph)
        self.assertAlmostEqual(busy, 2 * (3 + 1 + 5 + 0.5))
        self.assertEqual((times['output'], dispatches['output']), (0.0, 0))

    def test_segments_outside_the_layer_pattern_are_refused(self):
        def changed(index, cause=None, last_op=None, ops=None):
            rows = specs()
            old = rows[index]
            rows[index] = (cause or old[0], last_op or old[1], old[2] if ops is None else ops, old[3])
            return rows

        cases = {
            'count': (specs()[:-2], 'four segments per layer'),
            'tiny': (specs()[-1:], 'four segments per layer'),
            'two mixers': (changed(0, ops={'GATED_DELTA_NET': 1, 'FLASH_ATTN_EXT': 1}), 'expected mixer'),
            'mixer merge': (changed(4, last_op='ADD'), 'expected mixer'),
            'router merge': (changed(1, last_op=MERGE), 'expected router'),
            'router cause': (changed(1, cause='experts'), 'expected router'),
            'router experts': (changed(5, ops={'MUL_MAT_ID': 1}), 'expected router'),
            'experts cause': (changed(2, cause='hc_post'), 'expected experts'),
            'two matrices': (changed(6, ops={'MUL_MAT_ID': 2}), 'expected experts'),
            'combine': (changed(3, cause='hc_post'), 'expected combine'),
            'output merge': (changed(8, last_op=MERGE), 'expected output'),
            'output experts': (changed(8, ops={'MUL_MAT_ID': 3}), 'expected output'),
        }
        for name, (rows, message) in cases.items():
            graph = parsed(target(1, 1.0, rows))[('t', 1)]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                layer_parts(graph)


class RequestPartTests(unittest.TestCase):
    def lines(self):
        """Warm-up decode graph, then a 48-token prompt read as 44 and 4 tokens, each followed by a helper graph."""
        return [*target(1, 0.5), *target(2, 1.0), *helper(1, 1.03), *target(3, 1.1), *helper(2, 1.13)]

    def test_each_prompt_chunk_gets_its_parts_position_and_helper_time(self):
        lines = self.lines()
        rows = request_parts(graph_times(command_buffers(lines)), parsed(lines), (0.9, 2.0), 48, (512, 512))
        self.assertEqual([(r['tokens'], r['position'], r['helper_ms']) for r in rows], [(44, 0, 0.5), (4, 44, 0.5)])
        self.assertAlmostEqual(rows[0]['busy_ms'], 21.0)
        self.assertEqual(rows[1]['parts_ms']['experts'], 10.0)
        medians = median_parts([*rows, rows[0]])
        self.assertEqual(list(medians), ['4@44', '44@0'])
        self.assertEqual((medians['44@0']['samples'], medians['44@0']['parts_ms']['output']), (2, 2.0))

    def test_prompt_graphs_without_segment_timing_are_refused(self):
        lines = self.lines()
        split = parsed(lines)
        del split[('t', 3)]
        with self.assertRaisesRegex(ValueError, 'no segment timing'):
            request_parts(graph_times(command_buffers(lines)), split, (0.9, 2.0), 48, (512, 512))


class FitTests(unittest.TestCase):
    POINTS = [(300, 0), (512, 0), (512, 512), (1532, 796), (44, 0), (4, 44)]

    @staticmethod
    def model(tokens, position):
        return 171 + 1.02 * tokens + 0.21 * tokens * (position + tokens / 2) / 1000

    def test_fit_recovers_per_chunk_token_and_position_terms_above_the_small_chunk_limit(self):
        result = fit([(t, p, self.model(t, p)) for t, p in self.POINTS])
        self.assertAlmostEqual(result['per_chunk_ms'], 171, places=6)
        self.assertAlmostEqual(result['per_token_ms'], 1.02, places=8)
        self.assertAlmostEqual(result['per_token_per_1000_context_ms'], 0.21, places=8)
        self.assertEqual(result['samples'], 4)
        self.assertLess(result['max_residual_pct'], 1e-9)

    def test_fits_need_three_separable_positive_points(self):
        cases = {
            'too few': ([(300, 0, 1.0), (512, 0, 2.0), (44, 0, 1.0)], 'Too few'),
            'inseparable': ([(512, 0, 1.0), (512, 0, 2.0), (512, 0, 3.0)], 'do not separate'),
            'no time': ([(300, 0, 1.0), (512, 0, 0.0), (512, 512, 3.0)], 'no GPU time'),
        }
        for name, (points, message) in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                fit(points)

    def test_busy_time_and_every_part_but_the_output_get_a_fit(self):
        medians = {
            f'{t}@{p}': dict(tokens=t, position=p, busy_ms=self.model(t, p),
                             parts_ms={part: (i + 1) * self.model(t, p) for i, part in enumerate(PARTS)})
            for t, p in self.POINTS
        }
        fits = fit_parts(medians)
        self.assertEqual(list(fits), ['busy', *FITTED_PARTS])
        self.assertNotIn('output', FITTED_PARTS)
        self.assertAlmostEqual(fits['experts']['per_chunk_ms'], 4 * 171, places=5)


class ComparisonTests(unittest.TestCase):
    def test_controls_overhead_and_parity(self):
        chunks = [[dict(tokens=44, gpu_ms=200.0), dict(tokens=4, gpu_ms=40.0)],
                  [dict(tokens=44, gpu_ms=210.0), dict(tokens=4, gpu_ms=42.0)]]
        control = control_medians(chunks)
        self.assertEqual(control['44@0'], dict(tokens=44, position=0, samples=2, gpu_ms=205.0))
        self.assertEqual(control['4@44']['gpu_ms'], 41.0)
        segmented = {'44@0': dict(busy_ms=215.25), '512@0': dict(busy_ms=1.0)}
        self.assertEqual(list(overhead(segmented, control)), ['44@0'])
        self.assertAlmostEqual(overhead(segmented, control)['44@0'], 5.0, places=9)
        token = {'content': 'a', 'probabilities': [{'id': 1, 'logprob': -0.5}]}
        same = output_parity([('a', token), ('a', dict(token)), ('b', token)])
        self.assertEqual(same, dict(cases=2, requests=3, identical=True, differing_cases=[]))
        moved = output_parity([('a', token), ('a', dict(token, content='b'))])
        self.assertEqual((moved['identical'], moved['differing_cases']), (False, ['a']))


class SegmentDriverTests(unittest.TestCase):
    # The target and the helper context each report their batch sizes.
    RECEIPT = ['llama_context: n_batch = 512', 'llama_context: n_ubatch = 512'] * 2

    def test_segment_pairs_alternate_and_use_the_isolated_engine(self):
        self.assertEqual(driver.launch_plan('segments', ['512', '1536']),
                         [('segments', '512'), ('control', '512'), ('control', '1536'), ('segments', '1536')])
        self.assertEqual(driver.launch_plan('timing', ['512']), [('timing', '512')])
        with patch.object(driver, 'kept_server', return_value=['server', '--verbosity', '4']) as server:
            driver.launch_command(1, '512', 'control')
            driver.launch_command(1, '512', 'timing')
        self.assertEqual([call.args[3] for call in server.call_args_list], ['m5-segments', driver.ENGINE])
        env, settings = driver.launch_env('segments')
        self.assertEqual((env['GGML_M5_LAB_SEGMENTS'], env['GGML_M5_LAB_PROFILE']), ('1', '1'))
        self.assertEqual(settings['diagnostic_env'], driver.SEGMENT_ENV)
        env, settings = driver.launch_env('control')
        self.assertNotIn('GGML_M5_LAB_SEGMENTS', env)
        self.assertEqual(settings['diagnostic_env'], {})

    def test_segment_modes_record_the_sampled_token_probabilities(self):
        response = dict(timings=dict(prompt_n=2, prompt_ms=3.0, prompt_per_second=9.0), content='a',
                        completion_probabilities=[{'id': 7}])
        case = dict(name='short-prose', kind='prose', content='x')
        with patch.object(driver, 'request', return_value=response) as call:
            row = driver.measure('http://x', case, [1, 2], 0, 'segments')
            plain = driver.measure('http://x', case, [1, 2], 0)
        self.assertEqual(call.call_args_list[0].args[2]['n_probs'], driver.PROBABILITIES)
        self.assertNotIn('n_probs', call.call_args_list[1].args[2])
        self.assertEqual(row['output'], {'content': 'a', 'probabilities': [{'id': 7}]})
        self.assertNotIn('output', plain)

    def analyze(self, mode, marker):
        lines = [*self.RECEIPT, *([driver.SEGMENT_MARKER] if marker else []), *RequestPartTests.lines(None)]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'native.log').write_text('\n'.join(lines))
            request = dict(repeat=0, begin_monotonic_s=0.9, end_monotonic_s=2.0, prompt_tokens=48)
            result = dict(mode=mode, profile='512', requests=[request])
            driver.analyze(Path(tmp), result)
        return result

    def test_analysis_checks_the_timer_setting_and_keeps_chunk_totals(self):
        result = self.analyze('segments', True)
        self.assertEqual(list(result['segments']['medians']), ['4@44', '44@0'])
        self.assertEqual(result['requests'][0]['parts'][1]['position'], 44)
        self.assertAlmostEqual(result['timing']['all_requests']['44']['gpu_ms'], 21.0)
        control = self.analyze('control', False)
        self.assertNotIn('segments', control)
        self.assertEqual(control['timing']['all_requests']['4']['helper_ms'], 0.5)
        for mode, marker in (('segments', False), ('control', True)):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'did not reach the engine'):
                self.analyze(mode, marker)

    def test_comparison_fits_parts_against_same_engine_controls(self):
        def parts(tokens, position):
            ms = FitTests.model(tokens, position)
            return dict(tokens=tokens, position=position, busy_ms=ms * 1.02, span_ms=ms * 1.03, helper_ms=1.0,
                        parts_ms=dict.fromkeys(PARTS, ms / 6), dispatches=dict.fromkeys(PARTS, 1))

        token = {'content': 'a', 'probabilities': []}
        points = [(300, 0), (512, 0), (512, 512)]
        segmented = dict(mode='segments', requests=[dict(name='a', output=token, parts=[parts(*p) for p in points])])
        chunks = [dict(tokens=t, gpu_ms=FitTests.model(t, p)) for t, p in [(300, 0), (512, 300), (512, 812)]]
        controls = dict(mode='control', requests=[dict(name='a', output=token, gpu=dict(chunks=chunks))])
        analysis = driver.compare([segmented, controls])
        self.assertAlmostEqual(analysis['fits']['busy']['per_chunk_ms'], 171 * 1.02, places=5)
        self.assertAlmostEqual(analysis['control_fit']['per_token_ms'], 1.02, places=8)
        self.assertAlmostEqual(analysis['segment_overhead_pct']['300@0'], 2.0, places=8)
        self.assertEqual(list(analysis['segment_overhead_pct']), ['300@0'])
        self.assertTrue(analysis['parity']['identical'])

    def test_main_runs_segment_pairs_and_writes_the_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'bench').mkdir()
            output = folder / 'out'
            with patch.object(driver, 'ROOT', folder), patch.object(driver, 'assert_no_model_server'), \
                    patch.object(driver, 'require_pass'), patch.object(driver, 'closure', return_value={}), \
                    patch.object(driver, 'verify_models', return_value={}), \
                    patch.object(driver, 'launch', side_effect=lambda f, m, p, z: dict(status='passed', mode=m)) \
                    as launch, patch.object(driver, 'compare', return_value={'parity': 'ok'}) as compare, \
                    redirect_stdout(io.StringIO()) as printed:
                driver.main(['--mode', 'segments', '--profile', '512', '--output', str(output), '--run'])
            self.assertEqual([call.args[0].name for call in launch.call_args_list],
                             ['launch-1-segments-512', 'launch-2-control-512'])
            self.assertEqual([r['mode'] for r in compare.call_args.args[0]], ['segments', 'control'])
            self.assertEqual(json.loads((output / 'summary.json').read_text())['analysis'], {'parity': 'ok'})
            self.assertIn('segments-512/control-512; m5-segments engine', printed.getvalue())


class SegmentEngineTests(unittest.TestCase):
    def test_engine_is_registered_beside_the_kept_engine_with_the_same_settings(self):
        self.assertEqual(EXPERIMENTS['m5-segments'], 'm5_segments_experiment.json')
        control, _ = configure({}, 'm5-small-stack', 'on', 'small-reduce', profile=True)
        candidate, _ = configure({'GGML_M5_LAB_SEGMENTS': '1'}, 'm5-segments', 'on', 'small-reduce', profile=True)
        self.assertEqual(candidate, control)
        for tuning in ('compact-cols', 'route-map', 'encoders0'):
            with self.subTest(tuning=tuning), self.assertRaises(ValueError):
                configure({}, 'm5-segments', 'on', tuning)

    def test_manifest_binds_the_patch_and_every_kept_stack_component(self):
        manifest = json.loads((ROOT / 'config/m5_segments_experiment.json').read_text())
        patch_hash = hashlib.sha256((ROOT / manifest['patch']).read_bytes()).hexdigest()
        self.assertEqual((manifest['patch_sha256'], manifest['source_diff_sha256']), (patch_hash, patch_hash))
        kept = json.loads((ROOT / 'config/m5_small_stack_experiment.json').read_text())
        self.assertEqual(manifest['modified_files'], kept['modified_files'])
        self.assertEqual(manifest['features'], [*kept['features'], 'm5-segments'])
        self.assertIn({'patch': kept['patch'], 'sha256': kept['patch_sha256']}, manifest['components'])
        for component in manifest['components']:
            self.assertEqual(hashlib.sha256((ROOT / component['patch']).read_bytes()).hexdigest(), component['sha256'])


if __name__ == '__main__':
    unittest.main()
