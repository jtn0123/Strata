"""Long-input fixtures and capacity comparisons remain load-free until --run."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import benchmark_context as context
from context_fixture import SEEDS,build,correct


class ContextTests(unittest.TestCase):
    def test_exact_budget_preserves_all_facts_and_keeps_answers_out_of_question(self):
        for seed in SEEDS:
            f=build(lambda text:list(text.encode()),lambda text:"USER\n"+text+"\nASSISTANT\n",6144,seed)
            text=bytes(f["prompt"]).decode()
            self.assertEqual(len(f["prompt"]),6144)
            for key,value in f["expected"].items(): self.assertEqual(text.count(f"PRIMARY {key}: {value}"),1)
            self.assertEqual(f["fact_start_token_positions"]["middle"],3072)
            self.assertEqual(f,build(lambda text:list(text.encode()),lambda text:"USER\n"+text+"\nASSISTANT\n",6144,seed))
            self.assertTrue(correct(__import__('json').dumps(f["expected"]),f["expected"]))
            self.assertFalse(correct('text '+__import__('json').dumps(f["expected"]),f["expected"]))
            self.assertFalse(correct('```json\n'+__import__('json').dumps(f["expected"])+'\n```',f["expected"]))

    def records(self):
        records=[]
        for i,n in enumerate(context.ORDER):
            cases=[{"workload":"synthetic","prompt_tokens":size,"prompt_sha256":str(size),"output_tokens":128,
                "generation_tok_s":40,"prompt_tok_s":500,"ttft_s":1,"wall_s":4.2,"response":{"final":{"timings":{}}}}
                for size in (512,2048)]
            cached=[{"history_budget":size,"warmup":False,"prompt_sha256":str(size),"ttft_s":0.2,"wall_s":0.7,
                "native_timings":{"predicted_per_second":50,"prompt_per_second":600}} for size in (512,2048)]
            records.append({"status":"passed","settings":vars(context.settings(n,str(i),1)),"cases":cases,"cached_cases":cached,
                "checks":[{"passed":True}],"memory":{"swap_growth_bytes":0,"guard":None,"monitor_healthy":True,"child_exited":True},
                "retrieval_cases":[{"seed":seed,"prompt_tokens":6144,"prompt_sha256":str(seed),"passed":True} for seed in SEEDS] if n==8192 else [],
                **{key:{} for key in ("selected_engine","actual_sources","runtime","model","draft_model","metal_environment")}})
        return records

    def test_comparison_rejects_missing_recall_settings_drift_and_swap(self):
        original=self.records()
        self.assertEqual(len(context.compare(original,1)),4)
        for mutate in (lambda r:r[1]["retrieval_cases"].pop(),lambda r:r[1]["settings"].update(cache_type="q8_0"),
                       lambda r:r[1]["memory"].update(swap_growth_bytes=1),lambda r:r[1]["cases"][0].update(prompt_sha256="changed"),
                       lambda r:r[2]["retrieval_cases"][0].update(prompt_sha256="changed")):
            records=copy.deepcopy(original);mutate(records)
            with self.assertRaises(ValueError):context.compare(records,1)

    def test_default_is_plan_only(self):
        with patch.object(context,"execute") as execute: context.main([])
        execute.assert_not_called()

    def test_complete_wrapper_uses_model_ids_and_keeps_all_four_receipts(self):
        records=self.records()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bench/results').mkdir(parents=True)
            def run(args):
                result=records.pop(0)
                result.update(settings=vars(args),run_id=args.label)
                folder=root/'bench/results'/args.label;folder.mkdir();(folder/'server.log').write_text('')
                return result
            with patch.object(context,'ROOT',root),patch.object(context,'verify_engine',return_value={}), \
                 patch.object(context,'verify_models',return_value={}) as models,patch.object(context,'assert_unchanged'), \
                 patch.object(context,'run',side_effect=run):
                context.execute(1)
                models.assert_called_once_with(['flash','mtp_shared_packed_q3'])
            receipt=__import__('json').loads(next((root/'bench/results').glob('*/comparison.json')).read_text())
            self.assertEqual(receipt['status'],'passed');self.assertEqual(len(receipt['runs']),4)
