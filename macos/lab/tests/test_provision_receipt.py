"""Setup must refuse source/Python drift before installing or rebuilding anything, and bind what it builds."""
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engines
import prepare_m5
import provision


class ProvisionTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / 'config').mkdir()
        (root / '.venv/bin').mkdir(parents=True)
        (root / '.venv/bin/python').touch()
        for name in ('llama.cpp', 'Strata-macOS'): (root / 'vendor' / name).mkdir(parents=True)
        (root / 'config/runtime.json').write_text(json.dumps({'build_flags': [],
            'llama_cpp': {'revision': 'pin', 'repository': 'unused'},
            'strata_macos': {'revision': 'pin', 'repository': 'unused'}}))
        return root

    def output(self, command, **kwargs):
        return '3.12' if '-c' in command else ('pin' if command[-1] == 'HEAD' else '')

    def test_dirty_source_and_wrong_python_refuse_before_mutations(self):
        for reason in ('dirty', 'python'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                def output(command, **kwargs):
                    if reason == 'dirty' and '--porcelain' in command: return ' M hacked.cpp'
                    if reason == 'python' and '-c' in command: return '3.13'
                    return self.output(command)
                with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                     patch.object(provision.platform, 'machine', return_value='arm64'), \
                     patch.object(provision.subprocess, 'check_output', side_effect=output), patch.object(provision, 'run') as run:
                    with self.assertRaises(RuntimeError): provision.main([])
                    run.assert_not_called()

    def test_success_writes_then_verifies_baseline_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); uv = root / 'uv'; uv.touch()
            events = []
            with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                 patch.object(provision.platform, 'machine', return_value='arm64'), \
                 patch.object(provision.subprocess, 'check_output', side_effect=self.output), \
                 patch.object(provision.shutil, 'which', return_value=str(uv)), \
                 patch.object(provision, 'run', side_effect=lambda command: events.append(('command', command))), \
                 patch.object(provision, 'write_receipt', side_effect=lambda name: events.append(('receipt', name))), \
                 patch.object(provision, 'verify_engine', side_effect=lambda name: events.append(('verify', name))):
                provision.main(['--jobs', '1', '--local-http-only'])
            self.assertEqual(events[-2:], [('receipt', 'baseline'), ('verify', 'baseline')])
            self.assertTrue(any('-DLLAMA_OPENSSL=OFF' in c for kind,c in events if kind == 'command'))

    def test_check_only_requires_receipt_and_never_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                 patch.object(provision.platform, 'machine', return_value='arm64'), \
                 patch.object(provision.subprocess, 'check_output', side_effect=self.output), \
                 patch.object(provision, 'verify_engine', side_effect=FileNotFoundError('missing receipt')), patch.object(provision, 'run') as run:
                with self.assertRaises(FileNotFoundError): provision.main(['--check-only'])
                run.assert_not_called()

    def install_commands(self, failing_lock=None):
        """Run provisioning with mocked tools; return every command and the receipt/verify mocks."""
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); uv = root / 'uv'; uv.touch()
            commands = []
            def run(command):
                commands.append(list(map(str, command)))
                if failing_lock in command:
                    raise RuntimeError(f'{failing_lock} wheel verification failed')
            with patch.object(provision, 'ROOT', root), patch.object(provision, 'preflight', return_value={
                    'build_flags': [], 'llama_cpp': {}, 'strata_macos': {}}), \
                    patch.object(provision, 'source_check'), \
                    patch.object(provision.shutil, 'which', return_value=str(uv)), \
                    patch.object(provision, 'run', side_effect=run), \
                    patch.object(provision, 'write_receipt') as receipt, patch.object(provision, 'verify_engine') as verify:
                if failing_lock:
                    with self.assertRaisesRegex(RuntimeError, 'wheel verification failed'):
                        provision.main([])
                else:
                    provision.main([])
            return commands, receipt, verify

    def test_runtime_and_quality_installs_use_the_same_hash_locked_wheel_policy(self):
        commands, _, _ = self.install_commands()
        installs = [command for command in commands if command[1:3] == ['pip', 'install']]
        self.assertEqual([command[command.index('-r') + 1] for command in installs],
                         ['requirements-ci.lock', 'requirements-quality.lock'])
        self.assertFalse(any('requirements.txt' in command for command in commands), 'Unhashed runtime pins')
        policies = [command[:command.index('-r')] for command in installs]
        self.assertEqual(policies[0], policies[1])
        for install in installs:
            self.assertEqual(install.count('-r'), 1)
            self.assertIn('--require-hashes', install)
            self.assertEqual(install[install.index('--only-binary') + 1], ':all:')
            self.assertEqual(install[install.index('--python') + 1], '.venv/bin/python')
        configure = next(index for index, command in enumerate(commands) if '-S' in command)
        self.assertTrue(all(commands.index(install) < configure for install in installs))

    def test_failed_locked_install_stops_before_build_or_receipt_publication(self):
        for lock in ('requirements-ci.lock', 'requirements-quality.lock'):
            with self.subTest(lock=lock):
                commands, receipt, verify = self.install_commands(failing_lock=lock)
                self.assertFalse(any('-S' in command or '--build' in command for command in commands))
                self.assertFalse(any(command[:2] == ['git', 'init'] for command in commands))
                receipt.assert_not_called(); verify.assert_not_called()

    def test_runtime_lock_pins_every_runtime_requirement_with_hashes(self):
        lab = Path(provision.__file__).resolve().parents[1]
        canonical = lambda name: re.sub(r'[-_.]+', '-', name).lower()
        pins = dict(line.split('==') for line in (lab / 'requirements.txt').read_text().split() if line)
        locked, current = {}, None
        for line in (lab / 'requirements-ci.lock').read_text().splitlines():
            if match := re.match(r'^([A-Za-z0-9_.-]+)==([^ \\]+)', line):
                current = canonical(match[1]); locked[current] = [match[2], 0]
            elif '--hash=sha256:' in line:
                locked[current][1] += 1
        self.assertEqual({canonical(name): version for name, version in pins.items()},
                         {name: version for name, (version, _) in locked.items()})
        self.assertTrue(all(count for _, count in locked.values()), 'Every locked package needs wheel hashes')

    def test_check_only_reports_a_legacy_receipt_without_external_library_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            legacy = {'engine': 'baseline', 'artifacts': {}, 'build_receipt': {'engine': 'baseline', 'artifacts': {}}}
            with patch.object(provision, 'ROOT', root), patch.object(provision.platform, 'system', return_value='Darwin'), \
                 patch.object(provision.platform, 'machine', return_value='arm64'), \
                 patch.object(provision.subprocess, 'check_output', side_effect=self.output), \
                 patch.object(provision, 'verify_engine', return_value=legacy), patch.object(provision, 'run') as run, \
                 patch('sys.stdout', new_callable=io.StringIO) as output:
                provision.main(['--check-only'])
            run.assert_not_called()
            self.assertIn('external libraries unrecorded', output.getvalue())


def otool_output(identity=None, loads=(), rpaths=()):
    """`otool -l` text with a segment, an optional LC_ID_DYLIB, dylib loads and run paths."""
    lines, number = ['fixture:', 'Mach header', 'Load command 0', '      cmd LC_SEGMENT_64', '  segname __TEXT'], 1
    commands = ([('LC_ID_DYLIB', 'name', identity)] if identity else []) + \
        [('LC_LOAD_DYLIB', 'name', name) for name in loads] + [('LC_RPATH', 'path', path) for path in rpaths]
    for command, field, value in commands:
        lines += [f'Load command {number}', f'          cmd {command}', '      cmdsize 56',
                  f'         {field} {value} (offset 24)']
        if field == 'name':
            lines += ['   time stamp 2 Wed Dec 31 16:00:02 1969', '      current version 3.0.0',
                      'compatibility version 3.0.0']
        number += 1
    return '\n'.join(lines) + '\n'


class ExternalLibraryReceiptTests(unittest.TestCase):
    """Mocked Mach-O closures: the receipt binds dylibs loaded from outside build/bin."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()  # macOS temporary folders sit behind a /var symlink.
        self.bin = self.root / 'engine/build/bin'; self.bin.mkdir(parents=True)
        self.binary = self.bin / 'llama-server'; self.binary.write_bytes(b'server fixture')
        (self.bin / 'libllama.0.dylib').write_bytes(b'lab library fixture')
        (self.bin.parent / 'CMakeCache.txt').write_text('LLAMA_OPENSSL:BOOL=ON\n')
        self.cellar = self.root / 'homebrew/Cellar/openssl/lib'; self.cellar.mkdir(parents=True)
        self.ssl, self.crypto = self.cellar / 'libssl.3.dylib', self.cellar / 'libcrypto.3.dylib'
        self.ssl.write_bytes(b'ssl fixture'); self.crypto.write_bytes(b'crypto fixture')
        opt = self.root / 'homebrew/opt/openssl/lib'; opt.mkdir(parents=True)
        for library in (self.ssl, self.crypto):
            (opt / library.name).symlink_to(library)
        self.opt = opt
        self.links = {
            self.binary: otool_output(loads=['@rpath/libllama.0.dylib', f'{opt}/libssl.3.dylib',
                                             '/usr/lib/libSystem.B.dylib'], rpaths=['@loader_path/../bin']),
            self.bin / 'libllama.0.dylib': otool_output('@rpath/libllama.0.dylib', [
                f'{opt}/libcrypto.3.dylib', '/System/Library/Frameworks/Security.framework/Versions/A/Security']),
            self.ssl: otool_output(f'{opt}/libssl.3.dylib', [str(self.crypto), '/usr/lib/libSystem.B.dylib']),
            self.crypto: otool_output(f'{opt}/libcrypto.3.dylib', ['/usr/lib/libSystem.B.dylib']),
        }
        self.info = {'engine': 'baseline', 'directory': 'engine', 'revision': 'pin',
                     'source_diff_sha256': 'diff', 'patch': None}
        for name, value in (('ROOT', self.root), ('source_info', lambda *args: dict(self.info)),
                            ('engine_binary', lambda *args: self.binary)):
            patcher = patch.object(engines, name, value); patcher.start(); self.addCleanup(patcher.stop)

    def check_output(self, command, **kwargs):
        if command[0] == engines.OTOOL:
            return self.links[Path(command[-1]).resolve()]
        return 'clang fixture\n' if command[0] == 'clang' else 'native fixture\n'

    def write(self):
        with patch.object(engines.subprocess, 'check_output', side_effect=self.check_output):
            return engines.write_receipt('baseline')

    def verify(self):
        with patch.object(engines.subprocess, 'check_output', side_effect=self.check_output) as tools:
            return engines.verify_engine('baseline', self.root), tools

    def test_new_receipt_records_the_resolved_closure_and_verifies_it(self):
        receipt = self.write()
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        versions = {'current': '3.0.0', 'compatibility': '3.0.0'}
        self.assertEqual(receipt['external_libraries'], [
            {'path': str(self.crypto.resolve()), 'install_names': sorted([str(self.crypto), f'{self.opt}/libcrypto.3.dylib']),
             'sha256': digest(self.crypto), 'versions': versions},
            {'path': str(self.ssl.resolve()), 'install_names': [f'{self.opt}/libssl.3.dylib'],
             'sha256': digest(self.ssl), 'versions': versions}])
        self.assertEqual(set(receipt['artifacts']), {'llama-server', 'libllama.0.dylib'}, 'Lab files stay artifacts')
        self.assertEqual(receipt['build_settings'], {'LLAMA_OPENSSL': 'ON'})
        verified, _ = self.verify()
        self.assertEqual(verified['build_receipt'], json.loads((self.bin.parent / 'lab-receipt.json').read_text()))
        self.assertEqual(engines.external_library_status(verified), 'verified: 2 external libraries unchanged')

    def test_changed_missing_or_new_external_library_is_refused(self):
        self.write()
        self.crypto.write_bytes(b'updated crypto')
        with self.assertRaisesRegex(RuntimeError, 'changed since the build receipt: baseline: .*libcrypto'):
            self.verify()
        self.crypto.write_bytes(b'crypto fixture'); self.verify()
        self.ssl.unlink()
        with self.assertRaisesRegex(RuntimeError, 'changed since the build receipt.*Missing native library'):
            self.verify()
        self.ssl.write_bytes(b'ssl fixture')
        receipt_path = self.bin.parent / 'lab-receipt.json'
        receipt = json.loads(receipt_path.read_text()); receipt['external_libraries'] = []
        receipt_path.write_text(json.dumps(receipt))  # A local-HTTP-only record that now links OpenSSL.
        with self.assertRaisesRegex(RuntimeError, 'changed since the build receipt: baseline: .*libssl'):
            self.verify()

    def test_duplicate_libraries_are_refused(self):
        self.write()
        receipt_path = self.bin.parent / 'lab-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['external_libraries'].append(receipt['external_libraries'][0])
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(RuntimeError, 'more than once'):
            self.verify()
        other = self.root / 'usr-local/lib/libcrypto.3.dylib'; other.parent.mkdir(parents=True)
        other.write_bytes(b'a second crypto')
        self.links[other] = otool_output(str(other))
        self.links[self.ssl] = otool_output(f'{self.opt}/libssl.3.dylib', [str(other)])
        with patch.object(engines.subprocess, 'check_output', side_effect=self.check_output), \
                self.assertRaisesRegex(RuntimeError, 'same native library: libcrypto.3.dylib'):
            engines.external_libraries(self.binary)

    def test_legacy_receipt_without_a_record_is_accepted_unchanged(self):
        receipt_path = self.bin.parent / 'lab-receipt.json'
        legacy = {**self.info, 'artifacts': engines.artifact_hashes(self.bin), 'binary_version': 'old',
                  'build_settings': {}, 'compiler': 'old'}
        receipt_path.write_text(json.dumps(legacy))
        before = receipt_path.read_bytes()
        self.crypto.write_bytes(b'unrecorded change')
        verified, tools = self.verify()
        tools.assert_not_called()
        self.assertEqual(verified, {**self.info, 'artifacts': legacy['artifacts'], 'build_receipt': legacy})
        self.assertEqual(engines.external_library_status(verified),
                         'unrecorded: the build receipt predates external library records')
        self.assertEqual(receipt_path.read_bytes(), before)
        without_receipt = {key: value for key, value in verified.items() if key != 'build_receipt'}
        self.assertEqual(engines.external_library_status(without_receipt), 'not checked: no build receipt')


class LocalHttpOnlyPropagationTests(unittest.TestCase):
    def test_baseline_cache_decides_the_openssl_flag_for_engine_preparers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cache = root / 'vendor/llama.cpp/build/CMakeCache.txt'
            flags = ['-DGGML_METAL=ON']
            self.assertEqual(engines.baseline_build_flags(flags, root), flags)
            cache.parent.mkdir(parents=True); cache.write_text('LLAMA_OPENSSL:BOOL=ON\n')
            self.assertEqual(engines.baseline_build_flags(flags, root), flags)
            cache.write_text('LLAMA_OPENSSL:BOOL=OFF\n')
            self.assertEqual(engines.baseline_build_flags(flags, root), [*flags, '-DLLAMA_OPENSSL=OFF'])
            self.assertEqual(engines.baseline_build_flags([*flags, '-DLLAMA_OPENSSL=OFF'], root),
                             [*flags, '-DLLAMA_OPENSSL=OFF'])
            self.assertEqual(flags, ['-DGGML_METAL=ON'], 'Runtime flags are not mutated')

    def test_m5_preparer_builds_without_openssl_after_a_local_http_only_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('config', 'bench/features', 'vendor/candidate', 'vendor/llama.cpp/build'):
                (root / folder).mkdir(parents=True)
            (root / 'vendor/llama.cpp/build/CMakeCache.txt').write_text('LLAMA_OPENSSL:BOOL=OFF\n')
            (root / 'config/runtime.json').write_text(json.dumps({
                'build_flags': ['-DGGML_METAL=ON', '-DLLAMA_BUILD_TESTS=OFF'], 'llama_cpp': {'repository': 'unused'}}))
            (root / 'config' / engines.EXPERIMENTS['m5-small-stack']).write_text(json.dumps({
                'directory': 'vendor/candidate', 'patch': 'unused.patch', 'components': []}))
            (root / 'config/m5_test_plan.json').write_text('{}')
            calls = []
            with patch.object(prepare_m5, 'ROOT', root), patch.object(prepare_m5, 'verify_engine', return_value={}), \
                    patch.object(prepare_m5, 'source_info', return_value={}), patch.object(prepare_m5, 'write_receipt'), \
                    patch.object(prepare_m5, 'inventory', return_value={}), \
                    patch.object(prepare_m5.subprocess, 'run', side_effect=lambda parts, **kwargs: calls.append(parts)), \
                    patch('sys.stdout', new_callable=io.StringIO):
                prepare_m5.main(['--engine', 'm5-small-stack', '--build'])
            configure = next(call for call in calls if '-S' in call)
            self.assertEqual(configure[5:], ['-DGGML_METAL=ON', '-DLLAMA_OPENSSL=OFF', '-DLLAMA_BUILD_TESTS=ON'])


if __name__ == '__main__':
    unittest.main()
