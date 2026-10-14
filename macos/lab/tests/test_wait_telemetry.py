"""Reject misleading native diagnostics and retain failed/unknown observations."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wait_telemetry import Event, parse, summarize, union_us


class WaitTelemetryTests(unittest.TestCase):
    def events(self):
        return [
            ("M5_CPU_POOL", dict(action="create", threads=8, begin_us=11, end_us=21)),
            ("M5_CPU_POOL", dict(action="free", threads=8, begin_us=60, end_us=75)),
            ("M5_CPU_GRAPH", dict(threads=8, nodes=4, status=0, disposable_pool=True, begin_us=10, end_us=80)),
            ("M5_GPU_WAIT", dict(begin_us=40, end_us=60)),
            ("M5_HELPER_SCOPE", dict(phase="process", rows=4, begin_us=0, end_us=100)),
            ("M5_HELPER_SCOPE", dict(phase="draft", rows=1, begin_us=110, end_us=125)),
            ("M5_CPU_GRAPH", dict(threads=8, nodes=3, status=0, disposable_pool=False, begin_us=140, end_us=160)),
            ("M5_CPU_WORKER", dict(sample=0, timestamp_us=15, worker=3, threads=8, qos_valid=True,
                                   qos_class=25, relative_priority=0, thread_id_valid=True, thread_id=55)),
        ]

    def text(self, events):
        return "ordinary native log\n" + "\n".join(prefix + " " + json.dumps(data) for prefix, data in events)

    def test_complete_marker_fixture_preserves_overlap_and_attribution(self):
        report = summarize(parse(self.text(self.events())))
        self.assertEqual(report["helper_phase_envelope_us"], {"process": 100, "draft": 15, "accept": 0})
        self.assertEqual(report["cpu_graphs"], 2)
        self.assertEqual(report["helper_cpu_graphs"], 1)
        self.assertEqual(report["helper_disposable_graphs"], 1)
        self.assertEqual(report["helper_cpu_envelope_us"], 70)
        self.assertEqual(report["helper_pool_lifecycle_envelope_us"], 25)
        self.assertEqual(report["helper_pool_create_calls"], 1)
        self.assertEqual(report["helper_pool_free_calls"], 1)
        self.assertEqual(report["helper_gpu_wait_envelope_us"], 20)
        self.assertEqual(report["requested_qos_classes"], [25])
        self.assertEqual(report["helper_requested_qos_classes"], [25])
        self.assertEqual(report["helper_worker_samples"], 1)
        self.assertFalse(report["effective_qos_measured"])
        self.assertTrue(report["timings_excluded_from_speed_results"])

    def test_unspecified_or_failed_qos_remains_unknown(self):
        for valid in (True, False):
            with self.subTest(valid=valid):
                events = self.events()
                events[-1][1].update(qos_valid=valid, qos_class=0)
                report = summarize(parse(self.text(events)))
                self.assertEqual(report["requested_qos_unavailable_samples"], 1)
                self.assertFalse(report["effective_qos_measured"])

    def test_target_or_outside_worker_sample_is_not_labelled_as_helper(self):
        events = self.events()
        events[-1][1]["timestamp_us"] = 145
        report = summarize(parse(self.text(events)))
        self.assertEqual(report["requested_qos_classes"], [25])
        self.assertEqual(report["helper_requested_qos_classes"], [])
        self.assertEqual(report["helper_worker_samples"], 0)

    def test_native_graph_failure_is_retained_as_failed_diagnostic(self):
        for status in (-2, -1, 1):
            with self.subTest(status=status):
                events = self.events()
                events[2][1]["status"] = status
                report = summarize(parse(self.text(events)))
                self.assertEqual(report["status"], "diagnostic-failure")
                self.assertEqual(report["failed_cpu_graphs"], 1)

    def test_pool_reuse_records_no_disposable_helper_graph(self):
        events = self.events()[2:]
        events[0][1]["disposable_pool"] = False
        report = summarize(parse(self.text(events)))
        self.assertEqual(report["helper_disposable_graphs"], 0)
        self.assertEqual(report["helper_pool_create_calls"], 0)
        self.assertEqual(report["helper_pool_free_calls"], 0)

    def test_cross_boundary_graph_is_not_assigned_to_helper(self):
        events = self.events()
        events[2][1].update(begin_us=99, end_us=104)
        report = summarize(parse(self.text(events)))
        self.assertEqual(report["cpu_graphs"], 2)
        self.assertEqual(report["helper_cpu_graphs"], 0)

    def test_invalid_intervals_fields_and_native_worker_bounds_fail(self):
        mutations = [
            (4, "begin_us", -1), (4, "end_us", -1), (4, "end_us", -0.5),
            (4, "begin_us", True), (4, "rows", False), (4, "phase", "guess"),
            (2, "threads", 0), (2, "nodes", -1), (2, "status", False),
            (2, "disposable_pool", 1), (0, "action", "allocate"),
            (7, "sample", 512), (7, "worker", 8), (7, "timestamp_us", -1),
            (7, "qos_class", -1), (7, "relative_priority", -16),
            (7, "qos_valid", 0), (7, "thread_id_valid", 0), (7, "thread_id", -1),
            (4, "end_us", 0),
        ]
        for index, key, value in mutations:
            with self.subTest(index=index, key=key, value=value):
                events = copy.deepcopy(self.events())
                events[index][1][key] = value
                if key == "end_us" and value == 0:
                    events[index][1]["begin_us"] = 1
                text = self.text(events)
                with self.assertRaises(ValueError):
                    parse(text)

    def test_missing_and_malformed_coverage_is_rejected(self):
        texts = ["", "unrelated log", "M5_CPU_GRAPH", "M5_CPU_GRAPH not-json",
                 "M5_HELPER_SCOPE []", 'M5_HELPER_SCOPE {"phase":"process"}',
                 'M5_GPU_WAIT {"begin_us":1,"end_us":2,"extra":NaN}',
                 'M5_GPU_WAIT {"begin_us":1,"begin_us":2,"end_us":3}']
        for text in texts:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)
        text = self.text([self.events()[2]])
        with self.assertRaises(ValueError):
            parse(text)
        self.assertEqual(len(parse(text, require_helper=False)), 1)

    def test_summary_revalidates_events_instead_of_trusting_direct_objects(self):
        samples = [[], [Event("unknown", {})], [Event("gpu", dict(begin_us=2, end_us=1))]]
        for events in samples:
            with self.subTest(events=events), self.assertRaises(ValueError):
                summarize(events)

    def test_overlap_union_does_not_double_count_envelopes(self):
        events = [Event("gpu", dict(begin_us=b, end_us=e)) for b, e in ((20, 50), (10, 30), (60, 70))]
        self.assertEqual(union_us(events), 50)

    def test_zero_length_helper_observation_is_not_fabricated_as_positive(self):
        text = self.text([("M5_HELPER_SCOPE", dict(phase="accept", rows=0, begin_us=5, end_us=5))])
        report = summarize(parse(text))
        self.assertEqual(report["helper_phase_envelope_us"], {"process": 0, "draft": 0, "accept": 0})


if __name__ == "__main__":
    unittest.main()
