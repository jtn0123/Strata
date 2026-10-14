"""Keep the new opt-in diagnostic engine inside the inherited kept-stack guards."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from engines import EXPERIMENTS
from metal_environment import configure

class WaitEngineTests(unittest.TestCase):
    def test_wait_engine_is_registered_separately_from_kept_engine(self):
        self.assertEqual(EXPERIMENTS['m5-waits'],'m5_waits_experiment.json')
        self.assertEqual(EXPERIMENTS['m5-small-stack'],'m5_small_stack_experiment.json')

    def test_wait_engine_can_use_the_same_reduction_and_tensor_settings(self):
        control,_=configure({},'m5-small-stack','on','small-reduce')
        candidate,_=configure({},'m5-waits','on','small-reduce')
        self.assertEqual(candidate,control)
        self.assertNotIn('GGML_M5_HELPER_POOL',candidate)
        self.assertNotIn('GGML_M5_WAIT_TRACE',candidate)

    def test_new_engine_does_not_enable_unrelated_experimental_tunings(self):
        for tuning in ('compact-cols','qsa-all-pools','route-map'):
            with self.subTest(tuning=tuning):
                with self.assertRaises(ValueError):configure({},'m5-waits','on',tuning)

    def test_diagnostic_and_pool_flags_must_be_selected_by_the_trial(self):
        dirty={'GGML_M5_WAIT_TRACE':'1','GGML_M5_HELPER_POOL':'1'}
        clean,_=configure(dirty,'m5-waits','on','small-reduce')
        self.assertNotIn('GGML_M5_WAIT_TRACE',clean)
        self.assertNotIn('GGML_M5_HELPER_POOL',clean)

    def test_manifest_binds_all_source_changes_and_components(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'config/m5_waits_experiment.json').read_text())
        import hashlib
        patch=(root/manifest['patch']).read_bytes()
        self.assertEqual(hashlib.sha256(patch).hexdigest(),manifest['patch_sha256'])
        self.assertEqual(manifest['source_diff_sha256'],manifest['patch_sha256'])
        self.assertIn('common/speculative.cpp',manifest['modified_files'])
        self.assertIn('ggml/src/ggml-cpu/ggml-cpu.c',manifest['modified_files'])
        self.assertIn('ggml/src/ggml-cpu/ggml-cpu.cpp',manifest['modified_files'])
        self.assertIn('m5-small-stack',manifest['features'])
        for component in manifest['components']:
            self.assertEqual(hashlib.sha256((root/component['patch']).read_bytes()).hexdigest(),component['sha256'])
