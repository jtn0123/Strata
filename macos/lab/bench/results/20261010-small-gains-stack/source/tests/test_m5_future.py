"""Keep future templates honest and diagnostic attribution separate from speed claims."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import prepare_m5_future as future
import profile_m5_routes as routes


class FutureTests(unittest.TestCase):
    def test_no_default_model_gpu_or_build_trigger(self):
        with patch.object(routes,"build") as build, patch.object(routes,"execute") as execute:
            routes.main([]); build.assert_not_called();execute.assert_not_called()
        with patch.object(future,"prepare") as prepare:
            future.main([]);prepare.assert_not_called()

    def test_expert_reuse_counts_assignments_per_active_expert(self):
        ids=[list(range(10)),list(range(10)),list(range(10,20)),list(range(10,20))]
        result=routes.reuse(ids)
        self.assertEqual(result["unique_experts"],20)
        self.assertEqual(result["assignments_per_active_expert"],2)
        self.assertEqual(result["reused_assignment_percent"],50)
        self.assertEqual(result["assignments_in_experts_with_two_or_more_tokens_percent"],100)
        self.assertEqual(result["expert_token_count_histogram"],{2:20})
        self.assertEqual(result["adjacent_shared_experts"],[10,0,10])
        for bad in ([],[[1]*10],[list(range(9))],[list(range(9))+[512]],[list(range(9))+[True]]):
            with self.assertRaises(ValueError):routes.reuse(bad)

    def fixture(self):
        ids=[list(range(10))]*4
        return {
            "M5_EVAL_CONFIG":[{"mode":"split"}],
            "M5_EVAL_BEGIN":[{"serial":1,"cpu_us":100,"name":"result_output","op":"MUL_MAT",
                "src0":[2560,248320,1,1],"src0_type":"q5_K","dst":[248320,4,1,1]},
                {"serial":2,"cpu_us":300,"name":"ffn_moe_topk-0","op":"VIEW","dst":[10,4,1,1]}],
            "M5_EVAL_END":[{"serial":1,"cpu_us":200},{"serial":2,"cpu_us":350}],
            "M5_ROUTE":[{"serial":2,"cpu_us":325,"layer":0,"role":"target","rows":4,"row_stride_bytes":2048,"ids":ids}],
            "M5_PROFILE":[{"context":"c","graph":1,"cb":2,"call":1,"role":"target","tokens":4,"submit_cpu_us":125,
                "original_nodes":1,"op_counts":{"MUL_MAT":1},"gpu_start_s":1,"gpu_end_s":1.002,
                "gpu_ms":2,"valid":True,"completed":True}],
            "M5_PHASE":[{"task":7,"phase":"prompt","cpu_us":50},{"task":7,"phase":"generation","cpu_us":90}],
            "M5_REQUEST_END":[{"task":7,"cpu_us":400}]}

    def render(self,data):
        # GPU completion lines can precede callback markers in the log.
        return "\n".join(marker+" "+json.dumps(row) for marker,values in reversed(list(data.items())) for row in values)

    def test_split_cost_uses_submission_interval_and_preserves_role(self):
        result=routes.parse(self.render(self.fixture()),"split")
        r=result["requests"][0]
        self.assertEqual(r["split_attributed_buffers"],1)
        self.assertEqual(r["split_costs"][0]["family"],"vocabulary")
        self.assertAlmostEqual(r["split_costs"][0]["gpu_elapsed_sum_ms"],2)
        self.assertEqual(r["expert_reuse"][0]["assignments_per_active_expert_median"],4)

    def test_ambiguous_capture_cannot_become_a_cost_or_reuse_claim(self):
        changes=[lambda d:d["M5_EVAL_END"].pop(),
            lambda d:d["M5_EVAL_END"][0].update(cpu_us=310),
            lambda d:d["M5_ROUTE"][0].update(role="helper"),
            lambda d:d["M5_ROUTE"][0].update(row_stride_bytes=40),
            lambda d:d["M5_ROUTE"].clear(),
            lambda d:d["M5_PROFILE"][0].update(submit_cpu_us=250),
            lambda d:d["M5_PROFILE"][0].update(op_counts={"MUL_MAT":1,"ADD":1}),
            lambda d:d.update(M5_EVAL_ERROR=[{"message":"bad tensor"}])]
        for change in changes:
            data=self.fixture();change(data)
            with self.subTest(change=change),self.assertRaises(ValueError):routes.parse(self.render(data),"split")

    def test_untimed_computational_buffer_cannot_disappear_from_split_cost(self):
        data = self.fixture()
        missing = copy.deepcopy(data["M5_PROFILE"][0])
        missing.update(cb=3, op_counts={"ADD":1}, valid=False,
                       gpu_start_s=0, gpu_end_s=0, gpu_ms=0)
        data["M5_PROFILE"].append(missing)
        with self.assertRaisesRegex(ValueError, "Untimed computational"):
            routes.parse(self.render(data), "split")

    def test_empty_copy_requires_explicit_native_geometry_proof(self):
        data = self.fixture()
        data["M5_PROFILE"][0]["op_counts"]["CPY"] = 1
        data["M5_EVAL_EMPTY"] = [{"serial":1,"cpu_us":99,"name":"empty-state-copy",
                                  "op":"CPY","dst":[32,0,1,1]}]
        result = routes.parse(self.render(data), "split")
        self.assertEqual(result["requests"][0]["segments"][0]["empty_original_ops"], {"CPY":1})
        for dims in ([32,1,1,1], [32,-1,1,1]):
            data["M5_EVAL_EMPTY"][0]["dst"] = dims
            with self.assertRaises(ValueError): routes.parse(self.render(data), "split")

    def test_templates_contain_no_measured_metrics_or_fake_candidates(self):
        plan=json.loads(future.PLAN.read_text());future.validate(plan)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/"packet";future.prepare(plan,folder)
            receipt=json.loads((folder/"preparation.json").read_text())
            self.assertFalse(receipt["benchmarks_run"]);self.assertFalse(receipt["gpu_tests_run"])
            for e in plan["experiments"]:
                result=json.loads((folder/e["id"]/"result-template.json").read_text())
                self.assertEqual(result["status"],"not-run")
                self.assertFalse(result["testing_authorized"])
                self.assertTrue(all(v is None for metrics in result["metrics"].values() for v in metrics.values()))
        for mutate in (lambda p:p.update(automatic_execution=True),
            lambda p:p["experiments"][0].update(depends_on=["targeted-gpu-kernel"]),
            lambda p:next(e for e in p["experiments"] if e["id"] == "macos-row-prefetch").update(future_run_command=["fake-candidate"])):
            bad=copy.deepcopy(plan);mutate(bad)
            with self.assertRaises(ValueError):future.validate(bad)


if __name__ == "__main__":unittest.main()
