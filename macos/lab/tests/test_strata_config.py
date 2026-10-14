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
import performance_metrics
import web_ui


class StrataConfigTests(unittest.TestCase):
    def config(self,argv):
        # Run startup registration without opening sockets or changing global handlers.
        with patch.object(server,'Service',server.Service), \
                patch.object(server,'make_handler',server.make_handler), \
                patch.object(server,'Server',server.Server), \
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

    def test_registration_precedes_config_read_and_handler_wrapping(self):
        events=[]
        def read_config(*args, **kwargs):
            events.append('config')
            return json.dumps({'performance': {'batch': 512}})
        def track(original, mock_type, settings):
            events.append(('service', settings))
            return original
        def wrap(original):
            events.append('handler')
            return original
        def bound(original):
            events.append('server')
            return original
        with patch.object(server, 'Service', server.Service), \
                patch.object(server, 'make_handler', server.make_handler), \
                patch.object(server, 'Server', server.Server), \
                patch.object(backends, 'register_backend', side_effect=lambda *args: events.append('backend')), \
                patch.object(Path, 'read_text', side_effect=read_config), \
                patch.object(performance_metrics, 'tracked_service', side_effect=track), \
                patch.object(web_ui, 'mac_handler_factory', side_effect=wrap), \
                patch.object(web_ui, 'bounded_server', side_effect=bound), \
                patch.object(sys, 'argv', ['strata_server.py', '--config=fixture.json']):
            result=runpy.run_path(str(ROOT/'scripts/strata_server.py'))
        self.assertEqual(events, ['backend', 'config', ('service', {'batch': 512}), 'handler', 'server'])
        self.assertEqual(result['config'], {'batch': 512})
        self.assertIs(result['main'], server.main)

    def test_pinned_server_class_is_wrapped_with_the_connection_bound(self):
        original=server.Server
        with patch.object(server,'Service',server.Service), \
                patch.object(server,'make_handler',server.make_handler), \
                patch.object(server,'Server',original), \
                patch.object(backends,'register_backend'), \
                patch.object(sys,'argv',['strata_server.py','--engine','mock']):
            runpy.run_path(str(ROOT/'scripts/strata_server.py'))
            wrapped=server.Server
        self.assertTrue(issubclass(wrapped,web_ui.ConnectionLimit) and issubclass(wrapped,original))
        self.assertIs(server.Server,original)

    def test_null_performance_and_additional_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.json'
            for settings in (None, {'batch': 512, 'future_setting': {'enabled': True}}):
                path.write_text(json.dumps({'performance': settings}))
                self.assertEqual(self.config(['--config', str(path)]), settings)


if __name__=='__main__':unittest.main()
