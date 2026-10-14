#!/usr/bin/env python3
"""Reproduce the bounded native matcher CPU probe without loading a model."""
import argparse
import json
import subprocess

from benchmark_editing import matcher_proof, write
from check_memory import assert_no_model_server
from engines import sha256, verify_engine
from lab import ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Compile and run the small CPU-only probe')
    args = parser.parse_args(argv)
    print('Plan: actual existing ngram-map object; synthetic keys4/12/16, proposal widths1/2/3,18 checks. No model or GPU.')
    if not args.build:
        return
    assert_no_model_server()
    folder = ROOT / 'bench/features/20261013-ngram-short-mechanism'
    if folder.exists():
        matcher_proof()
        print('Existing verified proof retained; no overwrite or execution.')
        return
    folder.mkdir(parents=True)
    native = ROOT / 'vendor/llama-m5-small-stack'
    source = ROOT / 'native/ngram_short_probe.cpp'
    obj = native / 'build/common/CMakeFiles/llama-common.dir/ngram-map.cpp.o'
    pin = verify_engine('m5-small-stack')
    command = ['clang++', '-std=c++17', '-O2', '-I' + str(native / 'common'),
               '-I' + str(native / 'include'), '-I' + str(native / 'ggml/include'),
               str(source), str(obj), '-o', str(folder / 'probe')]
    record = dict(status='attempting', engine=pin, source_sha256=sha256(source),
                  native_object_sha256=sha256(obj), command=command,
                  scope='Actual existing native CPU matcher object. Logging only is stubbed; no model, GPU, backend or socket initialization.')
    write(folder / 'proof.json', record)
    try:
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (folder / 'build.log').write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError('CPU probe compilation failed; see preserved build.log')
        result = subprocess.run([str(folder / 'probe')], capture_output=True, text=True, timeout=10)
        (folder / 'probe.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('CPU probe failed; see preserved probe.log')
        record.update(json.loads(result.stdout), binary_sha256=sha256(folder / 'probe'))
        if verify_engine('m5-small-stack') != pin:
            raise RuntimeError('Existing engine changed during CPU preparation')
        write(folder / 'proof.json', record)
        matcher_proof()
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        write(folder / 'proof.json', record)
        raise
    print('CPU matcher mechanism passed18 checks; exact native object and probe identities recorded.')


if __name__ == '__main__':
    main()
