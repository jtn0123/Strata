"""Offline acceptance gates; no native engine, GPU or model invocation."""
import copy
from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_m5_compact as probe


class CompactEvidenceGates(unittest.TestCase):
    def fixture(self, layout='plain', rows=512):
        expected = dict(rows=rows, route='uniform', id_stride_bytes=2048, layout=layout,
                        precision='all-f16' if layout == 'precision-f16' else 'default', terminal_only=True, round=0)
        projections = []
        eligible = ([False]*3 if layout in ('unsupported-shape', 'precision-f16') or not 32 <= rows <= 512
                    else [False, False, True] if layout in ('unsupported-k', 'activation-f16') else [True]*3)
        k = 2496 if layout == 'unsupported-k' else 2560
        hidden = 576 if layout == 'unsupported-shape' else 640
        for block in range(2):
            for lane, name in enumerate(('gate', 'up', 'down')):
                projections.append(dict(name=f'block{block}.{name}', eligible=eligible[lane],
                                        weight_shape=[hidden, 2560, 512, 1] if lane == 2 else [k, hidden, 512, 1],
                                        activation_shape=[hidden, 10, rows, 1] if lane == 2 else [k, 1, rows, 1],
                                        weight_type='q2_0', activation_type='f16' if lane != 2 and layout == 'activation-f16' else 'f32',
                                        source_precision=20 if layout == 'precision-f16' else 0, id_stride_bytes=2048,
                                        weight_contiguous=True, activation_contiguous=True, output_contiguous=True))
        routes = []
        for block in range(2):
            counts = probe.route_counts(expected, block, 0)
            routes.append(dict(expert_counts=counts, memberships=10*rows, nonempty_tiles32=sum((x+31)//32 for x in counts),
                               static_tile_capacity=(10*rows+31*512)//32, distinct_top10_per_token=True))
        weights = [dict(name=name, bytes=235929600, sha256='f'*64, experts=512, k=640 if name == 'down.weight' else 2560,
                        m=2560 if name == 'down.weight' else 640) for name in ('gate.weight', 'up.weight', 'down.weight')]
        row = dict(expected, id=probe.expected_id(expected), mode='perf', scope='compact', eligible=any(eligible),
                   executions=81, triplets_per_graph=2, eligible_mm_per_graph=sum(eligible)*2, mm_ids_per_graph=6,
                   projections=projections, count_delta=81*sum(eligible)*2, counter_available=True,
                   counter_semantics=probe.COUNTER_SEMANTICS, inputs_preserved=True, ids_preserved=True, all_nodes_metal=True,
                   scheduler_splits=1, cpu_compute_nodes=0, evaluation_callbacks=False,
                   outputs=[dict(name='block1.residual', elements=2560*rows, bytes=10240*rows, sha256='a'*64, finite=True)],
                   output_sha256='a'*64, exact_oracle=probe.EXACT_ORACLE, route_source='synthetic',
                   input_sha256='b'*64, ids_sha256=['d'*64, 'e'*64], coefficients_sha256='c'*64, weights=weights,
                   routes=routes, input_version=0, same_graph_mutation=False, allocation_estimate_bytes=1024,
                   ns_samples=[50000000.0]*7, ns_per_triplet=[25000000.0]*7, median_ns=50000000.0,
                   warmup_ns=500000000, warmup_iterations=10, pipeline_primed=True,
                   block_iterations=[10]*7, block_ns=[500000000]*7)
        done = dict(mode='perf', scope='compact', cases=1, fixtures=1, models_loaded=False,
                    weights_preserved=True, route_source='synthetic', counter_available=True, weights=weights)
        return expected, row, done

    def parse(self, expected, row, done):
        text = 'M5_COMPACT_CASE '+json.dumps(row)+'\nM5_COMPACT_DONE '+json.dumps(done)
        with patch.object(probe, 'inventory', return_value=[expected]):
            return probe.parse(text, 'perf', 'compact')

    def test_every_eligible_mm_encoding_is_required(self):
        expected, row, done = self.fixture()
        self.assertEqual(len(self.parse(expected, row, done)), 1)
        for delta in (0, 81, 485, 487, True):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                self.parse(expected, dict(row, count_delta=delta), done)
        for layout, count in (('different-input', 6), ('different-ids', 6), ('intervening-gate-scale', 6),
                              ('activation-unfused', 6), ('unsupported-k', 2), ('activation-f16', 2),
                              ('unsupported-shape', 0), ('precision-f16', 0)):
            self.assertEqual(sum(probe.eligible_projections(dict(expected, layout=layout))), count)
        for layout in ('unsupported-k', 'activation-f16', 'unsupported-shape', 'precision-f16'):
            expected, row, done = self.fixture(layout)
            self.assertEqual(len(self.parse(expected, row, done)), 1)
            with self.assertRaises(ValueError):
                self.parse(expected, dict(row, count_delta=row['count_delta']+1), done)
        expected, row, done = self.fixture(rows=513)
        self.assertEqual(row['eligible_mm_per_graph'], 0)
        self.assertEqual(len(self.parse(expected, row, done)), 1)

    def test_missing_counter_and_forged_predicate_fail_closed(self):
        expected, row, done = self.fixture()
        with self.assertRaises(ValueError):
            self.parse(expected, dict(row, counter_available=False), done)
        with self.assertRaises(ValueError):
            self.parse(expected, row, dict(done, counter_available=False))
        broken = copy.deepcopy(row)
        broken['projections'][5]['eligible'] = False
        broken['eligible_mm_per_graph'] = 5
        broken['count_delta'] = 405
        with self.assertRaises(ValueError):
            self.parse(expected, broken, done)
        for field, value in (('scheduler_splits', 2), ('all_nodes_metal', False), ('evaluation_callbacks', True),
                             ('exact_oracle', 'CPU tolerance'), ('weights', []), ('executions', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.parse(expected, dict(row, **{field: value}), done)

    def test_timed_blocks_are_sustained_and_count_all_executions(self):
        expected, row, done = self.fixture()
        for field, value in (('ns_samples', [40000000.0]*7), ('block_ns', [500000000]*6),
                             ('block_iterations', [True]*7), ('warmup_iterations', 0), ('executions', 80),
                             ('ns_per_triplet', [50000000.0]*7), ('pipeline_primed', False)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.parse(expected, dict(row, **{field: value}), done)

    def test_complete_terminal_result_is_exact_original_engine_oracle(self):
        _, control, _ = self.fixture()
        candidate = copy.deepcopy(control)
        candidate['scope'] = 'control'
        probe.compare_exact([control], [candidate])
        candidate['outputs'][-1]['sha256'] = 'b'*64
        candidate['output_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'terminal/projection'):
            probe.compare_exact([control], [candidate])
        _, row, done = self.fixture()
        row['outputs'][-1]['finite'] = False
        with self.assertRaises(ValueError):
            self.parse({key: row[key] for key in ('rows', 'route', 'id_stride_bytes', 'layout', 'precision', 'terminal_only', 'round')}, row, done)

    def test_valid_distinct_top10_routes_attain_exact_capacity(self):
        for rows, expected_histogram, tiles in ((508, {1: 369, 25: 1, 33: 142}, 654),
                                                (512, {1: 368, 33: 144}, 656)):
            fixture = dict(rows=rows, route='capacity')
            counts = probe.route_counts(fixture, 0, 0)
            self.assertEqual(Counter(counts), expected_histogram)
            self.assertEqual(sum(counts), 10*rows)
            self.assertEqual(sum((count+31)//32 for count in counts), tiles)
            self.assertEqual((10*rows+31*512)//32, tiles)
            permuted = probe.route_counts(dict(fixture, route='capacity-permuted'), 1, 1)
            self.assertEqual(Counter(permuted), expected_histogram)
        for rows in (33, 64, 127, 508, 512):
            counts = probe.route_counts(dict(rows=rows, route='skewed'), 0, 0)
            self.assertTrue({0, 1, 31, 32, 33, rows}.issubset(set(counts)))

    def test_gate_requires_both_uniform_endpoints_strictly_above_ten_percent(self):
        fixtures = []
        for rows in (508, 512):
            _, row, _ = self.fixture(rows=rows)
            fixtures.append(row)
        def runs(candidate_ns):
            result = []
            for ns in (100000000, candidate_ns, candidate_ns, 100000000):
                cases = [dict(row, median_ns=ns) for row in fixtures]
                result.append((dict(status='passed', cases=cases), probe.ROOT/'bench/results/fixture'))
            return result
        self.assertFalse(probe.summarize(runs(90000000))['qualifies_for_model_trial'])
        self.assertTrue(probe.summarize(runs(89000000))['qualifies_for_model_trial'])
        timed = runs(89000000)
        timed[2][0]['cases'][1]['median_ns'] = 100000000
        self.assertFalse(probe.summarize(timed)['qualifies_for_model_trial'])


if __name__ == '__main__':
    unittest.main()
