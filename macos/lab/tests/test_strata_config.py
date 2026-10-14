"""The maintained server must accept the pinned shell's JSON/CLI config forms."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'vendor/Strata-macOS'))
from serve import server, backends


class StrataConfigTests(unittest.TestCase):
    def config(self,argv):
        # Run startup registration without opening sockets or changing global handlers.
        with patch.object(server,'Service',server.Service), \
                patch.object(server,'make_handler',server.make_handler), \
                patch.object(backends,'register_backend'), \
                patch.object(sys,'argv',['strata_server.py',*argv]):
            return runpy.run_path(str(ROOT/'scripts/strata_server.py'))['config']

    def test_split_and_equals_config_arguments_have_same_performance_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.json'
            expected={'batch':1536,'ubatch':1536}
            path.write_text(json.dumps({'performance':expected}))
            for argv in (['--config',str(path)],['--config='+str(path)]):
                with self.subTest(argv_form='equals' if '=' in argv[0] else 'split'):
                    self.assertEqual(self.config(['--engine','mock',*argv]),expected)

    def test_bom_json_supported_by_pinned_shell_still_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.json'
            path.write_text(json.dumps({'performance':{'batch':512}}),encoding='utf-8-sig')
            self.assertEqual(self.config(['--config',str(path)]),{'batch':512})

    def test_no_config_or_help_does_not_read_a_configuration_file(self):
        # runpy reads the script itself through the import machinery, not read_text.
        for argv in ([],['--help'],['--config','/unused/fixture.json','--help']):
            with patch.object(Path,'read_text',side_effect=AssertionError('No config read')):
                self.assertEqual(self.config(argv),{})

    def test_last_config_argument_matches_pinned_shell_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            paths=[Path(folder)/f'fixture-{i}.json' for i in (512,1536)]
            for path,size in zip(paths,(512,1536)):
                path.write_text(json.dumps({'performance':{'batch':size}}))
            self.assertEqual(self.config(['--config',str(paths[0]),'--config='+str(paths[1])]),{'batch':1536})


if __name__=='__main__':unittest.main()
