# Contributing to Strata

Strata has four parts: the C++/CUDA/HIP engine (`src/`, `include/`), the Python server with its web app (`serve/`),
the installer (`setup.py`, started by `START-HERE.bat` / `setup.sh`) and the tools it uses (`tools/`). `macos/lab/`
is this fork's Mac lab, with its own guide ([macos/lab/README.md](macos/lab/README.md)) and checks.

How the engine works, every measured number, the API and all settings: [docs/DETAILS.md](docs/DETAILS.md) and the
[paper](docs/paper/Strata-Paper.pdf). AMD: [docs/AMD_HIP.md](docs/AMD_HIP.md). Several GPUs:
[docs/MULTI_GPU.md](docs/MULTI_GPU.md).

## Run the tests

These need no GPU, no model and no download beyond llama.cpp's `gguf-py`. CI runs them on Python 3.10 and 3.12
([strata-tests.yml](.github/workflows/strata-tests.yml) shows each command). Install the pinned packages first:

```
python -m venv .venv-tests
.venv-tests/bin/python -m pip install --only-binary :all: --require-hashes -r .github/requirements-tests.lock
```

| What | Command (from the repository root, with that Python) |
| --- | --- |
| Server and web app | `python -m unittest discover -s serve -t . -p 'test_*.py'` |
| Installer | `cd tools && python -m unittest discover -s . -p 'test_setup_*.py'` |
| Tools | `git ls-files -z 'tools/test_*.py' ':!tools/test_setup_*' \| xargs -0 python -m unittest`, with `STRATA_GGUF_PY` set to the `gguf-py` folder of llama.cpp at the commit `setup.py` pins (`LLAMA_CPP_COMMIT`; the workflow fetches only that folder) |
| Web app in Node 22 | `node --test serve/*.test.cjs` |
| Lint | `git ls-files -z '*.py' ':(exclude)macos' \| xargs -0 ruff check --isolated --target-version py310 --select E9,F63,F7,F82`, with ruff from [.github/requirements-lint.lock](.github/requirements-lint.lock) |

One installer area at a time: `python tools/test_setup_<name>.py` (for example `tools/test_setup_amd.py`). The Mac
lab's checks are in [mac-lab-offline.yml](.github/workflows/mac-lab-offline.yml).

The engine's own tests: build it with `-DSTRATA_BUILD_TESTS=ON` and run `ctest` in the build folder. Some run on
the CPU alone; the others use the card the build is for (AMD: [docs/AMD_HIP.md](docs/AMD_HIP.md)).

## Pull requests

- Open them against `mac-m5-lab`, this fork's main branch.
- One change per commit, saying what it fixes and how it was checked. Add a test that fails without the change.
- Fix a warning or a failing test; don't silence the warning or skip the test.
- The server listens on `127.0.0.1`. Nothing may expose it beyond this PC without an API key (`--api-key`).
- The docs use plain words, and every number says what it was measured on (the card, the model and size, the engine
  version). No claim without a measurement.
- Raw measurements, machine paths, model weights and local config stay out of commits (`.gitignore` lists them).
  Revision-pinned vendor source stays as it is.

CI runs the tests above, the lint and SonarCloud on each pull request; `macos/` changes also run the Mac lab's
offline checks.
