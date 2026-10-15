"""Tests for setup.py's reproducible installs (#214): the engine of the checkout's own release first, installed only
with its pinned SHA-256 (the latest release, unpinned, only with --allow-unpinned), llama.cpp's zip with its pinned
SHA-256, Hugging Face files at pinned revisions (a revision that is gone stops setup; --allow-unpinned takes the
current files), the pinned CUDA key package, the pinned requirements file, and an existing install left as it is.
Mocked network - nothing is downloaded.

    python -m unittest tools.test_setup_pins
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import setup  # noqa: E402

SHA = re.compile(r"/resolve/[0-9a-f]{40}/")


class Response(io.BytesIO):
    def __init__(self, body=b"", status=200):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def not_found(url):
    return urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def quiet(fn, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        return fn(*args, **kw), out.getvalue()


class HuggingFacePins(unittest.TestCase):
    def test_every_model_url_is_pinned(self):
        for name, fam in setup.FAMILIES.items():
            for key in ("hf", "mmproj_hf"):
                with self.subTest(family=name, key=key):
                    self.assertRegex(fam[key], SHA)
                    self.assertNotIn("/resolve/main/", fam[key])
        self.assertRegex(setup.HF, SHA)

    def test_unpinned(self):
        url = setup.FAMILIES["swift"]["hf"] + "x.gguf"
        self.assertEqual(setup.hf_unpinned(url),
                         "https://huggingface.co/ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF/resolve/main/x.gguf")
        self.assertEqual(setup.hf_unpinned("https://example.com/a/b"), "https://example.com/a/b")

    @staticmethod
    def gone_revision():
        seen = []

        def urlopen(req, timeout=None):
            seen.append((req.get_method(), req.full_url))
            if "/resolve/main/" not in req.full_url:
                raise not_found(req.full_url)
            return Response(b"model bytes", status=200)

        return seen, urlopen

    def test_a_gone_revision_stops_setup(self):
        """The current file is not the pinned one, and nothing checks it: setup stops and says how to go on."""
        seen, urlopen = self.gone_revision()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(setup.urllib.request, "urlopen", urlopen):
            dst = Path(d) / "m.gguf"
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                setup.download(setup.FAMILIES["qwen"]["mmproj_hf"] + "m.gguf", dst)
            self.assertFalse(dst.exists())
        self.assertIn("not at the pinned revision any more", out.getvalue())
        self.assertIn("--allow-unpinned", out.getvalue())
        self.assertEqual([m for m, _ in seen], ["HEAD"])

    def test_allow_unpinned_downloads_the_current_file(self):
        seen, urlopen = self.gone_revision()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(setup.urllib.request, "urlopen", urlopen), \
                mock.patch.object(setup, "ALLOW_UNPINNED", True):
            dst = Path(d) / "m.gguf"
            _, out = quiet(setup.download, setup.FAMILIES["qwen"]["mmproj_hf"] + "m.gguf", dst)
            self.assertEqual(dst.read_bytes(), b"model bytes")
        self.assertIn("not at the pinned revision any more", out)
        self.assertEqual([m for m, _ in seen], ["HEAD", "HEAD", "GET"])
        self.assertTrue(all("/resolve/main/" in u for _, u in seen[1:]))

    def test_the_flag_sets_it(self):
        seen = []

        def stop(*args):                                # main's first line of output: the arguments are parsed
            seen.append(setup.ALLOW_UNPINNED)
            raise RuntimeError("parsed")

        for argv in (["setup.py", "--allow-unpinned"], ["setup.py"]):
            with mock.patch.object(sys, "argv", argv), mock.patch.object(setup, "ALLOW_UNPINNED", None), \
                    mock.patch.object(setup, "say", stop), self.assertRaisesRegex(RuntimeError, "parsed"):
                setup.main()
        self.assertEqual(seen, [True, False])

    def test_a_complete_part_is_finished_without_a_request(self):
        """A .part with every byte (setup stopped between the last byte and the rename): renamed, not resumed with a
        range past its end - the server answers that with 416, which download() retried 30 times, 10 s apart."""
        seen = []

        def urlopen(req, timeout=None):
            seen.append((req.get_method(), req.headers.get("Range")))
            if req.get_method() == "HEAD":
                return Response(b"model bytes")
            raise urllib.error.HTTPError(req.full_url, 416, "Range Not Satisfiable", {}, None)

        with tempfile.TemporaryDirectory() as d, mock.patch.object(setup.urllib.request, "urlopen", urlopen), \
                mock.patch.object(setup.time, "sleep", lambda s: None):
            dst = Path(d) / "m.gguf"
            dst.with_name("m.gguf.part").write_bytes(b"model bytes")
            quiet(setup.download, "https://example.com/m.gguf", dst)
            self.assertEqual(dst.read_bytes(), b"model bytes")
            self.assertTrue(setup.done(dst))
        self.assertEqual(seen, [("HEAD", None)])

    def test_mtp_fetch_is_pinned_and_falls_back(self):
        import mtp_fetch
        self.assertRegex(mtp_fetch.REPO, SHA)
        self.assertIn(mtp_fetch.REVISION, mtp_fetch.REPO)
        pinned = mtp_fetch.REPO

        def urlopen(req, timeout=None):
            raise not_found(req.full_url)

        try:
            with mock.patch.object(mtp_fetch.urllib.request, "urlopen", urlopen), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(mtp_fetch.resolve_repo(), "https://huggingface.co/Qwen/Qwen3.8-Flash-Next/resolve/main/")
            self.assertIn("pinned revision", err.getvalue())
        finally:
            mtp_fetch.REPO = pinned

    def test_hf_endpoint(self):
        # #495: HF_ENDPOINT (a mirror) serves the same pinned revision; a trailing slash and blanks are dropped
        repo = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF"
        with mock.patch.dict(setup.os.environ, {}, clear=False):
            setup.os.environ.pop("HF_ENDPOINT", None)
            self.assertEqual(setup.hf(repo), f"https://huggingface.co/{repo}/resolve/{setup.HF_REVISIONS[repo]}/")
            for value in ("https://hf-mirror.com", "https://hf-mirror.com/", " https://hf-mirror.com/ "):
                setup.os.environ["HF_ENDPOINT"] = value
                url = setup.hf(repo)
                self.assertEqual(url, f"https://hf-mirror.com/{repo}/resolve/{setup.HF_REVISIONS[repo]}/")
                self.assertRegex(url, SHA)
                self.assertEqual(setup.hf_unpinned(url + "x.gguf"), f"https://hf-mirror.com/{repo}/resolve/main/x.gguf")
            setup.os.environ["HF_ENDPOINT"] = ""
            self.assertEqual(setup.hf_endpoint(), "https://huggingface.co")

    def test_mtp_fetch_honours_hf_endpoint(self):
        import importlib
        import mtp_fetch
        try:
            with mock.patch.dict(mtp_fetch.os.environ, {"HF_ENDPOINT": "https://hf-mirror.com/"}):
                importlib.reload(mtp_fetch)
                self.assertTrue(mtp_fetch.REPO.startswith("https://hf-mirror.com/Qwen/Qwen3.8-Flash-Next/resolve/"))
                self.assertRegex(mtp_fetch.REPO, SHA)
                self.assertTrue(mtp_fetch.pinned())                 # the tensors' SHA-256 checks still apply
        finally:
            importlib.reload(mtp_fetch)
        self.assertTrue(mtp_fetch.REPO.startswith("https://huggingface.co/"))

    def test_step5_names_the_folder(self):
        # #495: where setup expects the model files, and how to give it files downloaded by hand
        from test_setup_golden import PROFILES, install
        ram, found = PROFILES["96GB-1x16GB"]
        with mock.patch.dict(setup.os.environ, {"HF_ENDPOINT": "https://hf-mirror.com"}):
            code, out, cfg, _ = install(ram, found, ["--family", "qwen", "--model", "IQ3_XXS", "--no-start"])
        self.assertEqual(code, 0)
        text = out.replace("\\", "/")
        self.assertRegex(text, r"The model files go in .*/models/IQ3_XXS")
        self.assertIn("put them here with their original names (Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
                      text)
        self.assertIn("--gguf-dir", text)
        self.assertIn("Downloading from https://hf-mirror.com (HF_ENDPOINT)", text)



class CudaKeyring(unittest.TestCase):
    """NVIDIA's key package is installed as root: from a new private folder (a fixed /tmp name could be another user's
    file, which download() kept), and only with its pinned SHA-256."""

    def install(self, body):
        ran, folders = [], []

        def download(url, dst, what=None):
            self.assertIn("/ubuntu2404/", url)
            folders.append((dst.parent, stat.S_IMODE(dst.parent.stat().st_mode)))
            dst.write_bytes(body)

        def run(cmd, **kw):
            ran.append(cmd)
            self.assertTrue(Path(cmd[-1]).is_file())    # dpkg runs while the package is still there

        pins = {"2404": hashlib.sha256(b"key package").hexdigest()}
        with mock.patch.object(setup, "download", download), mock.patch.object(setup, "run", run), \
                mock.patch.object(setup, "CUDA_KEYRING_SHA256", pins):
            quiet(setup.install_cuda_keyring, "2404")
        return ran, folders

    def test_every_supported_release_is_pinned(self):
        self.assertEqual(set(setup.CUDA_KEYRING_SHA256), {"2204", "2404"})
        for sha in setup.CUDA_KEYRING_SHA256.values():
            self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_the_pinned_package_is_installed_from_a_private_folder(self):
        ran, folders = self.install(b"key package")
        (folder, mode), = folders
        self.assertTrue(folder.name.startswith("strata-cuda-"))
        if os.name != "nt":
            self.assertEqual(mode, 0o700)
        self.assertFalse(folder.exists())               # removed after the install
        self.assertEqual([c[:3] for c in ran], [["sudo", "dpkg", "-i"]])

    def test_another_package_is_not_installed(self):
        with self.assertRaises(SystemExit):
            self.install(b"someone else's package")


def engine_zip(meta) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("BUILD.json", json.dumps(meta))
        z.writestr(setup.EXE, b"engine")
    return out.getvalue()


def pin_of(body: bytes) -> tuple[int, str]:
    return len(body), hashlib.sha256(body).hexdigest()


class Engine(unittest.TestCase):
    TAG = "https://github.com/Niko1221/Strata/releases/download/v0.1.31/"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "engine").mkdir()
        self.body = engine_zip({"version": ".".join(map(str, setup.MIN_ENGINE)), "archs": [89]})
        self.patches = [mock.patch.object(setup, "ROOT", self.root),
                        mock.patch.object(setup, "source_version", lambda: "0.1.31"),
                        mock.patch.object(setup, "PREBUILT_PINS", {"0.1.31": {setup.PREBUILT_ASSET: pin_of(self.body)}})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def fake_download(self, got, body=None):
        def download(url, dst, what=None):
            got.append(url)
            dst.write_bytes(self.body if body is None else body)
            setup.mark(dst)
        return download

    def run_get(self, published, body=None):
        heads, got = [], []

        def urlopen(req, timeout=None):
            heads.append(req.full_url)
            if not any(req.full_url.startswith(p) for p in published):
                raise not_found(req.full_url)
            return Response()

        with mock.patch.object(setup.urllib.request, "urlopen", urlopen), \
                mock.patch.object(setup, "download", self.fake_download(got, body)):
            eng, out = quiet(setup.get_prebuilt, setup.PREBUILT_URL, {"arch": 89}, "gpu")
        return eng, out, heads, got

    def test_bases(self):
        self.assertEqual(setup.prebuilt_bases(setup.PREBUILT_URL),
                         ["https://github.com/Niko1221/Strata/releases/download/v0.1.31/", setup.PREBUILT_URL])
        self.assertEqual(setup.prebuilt_bases("https://mirror.example/x"), ["https://mirror.example/x/"])

    def test_the_checkout_s_release_first(self):
        eng, out, heads, got = self.run_get([self.TAG, setup.PREBUILT_URL])
        self.assertEqual(eng, self.root / "engine")
        self.assertEqual(got, [self.TAG + setup.PREBUILT_ASSET])
        self.assertEqual(len(heads), 1)
        self.assertIn("checking " + setup.PREBUILT_ASSET, out)

    def test_the_latest_is_not_installed_without_a_pin(self):
        eng, out, heads, got = self.run_get([setup.PREBUILT_URL])
        self.assertIsNone(eng)
        self.assertEqual(got, [])                       # not even downloaded
        self.assertIn("No ready-made engine for v0.1.31", out)
        self.assertIn("has no pinned SHA-256", out)
        self.assertIn("--allow-unpinned", out)

    def test_the_latest_with_allow_unpinned(self):
        with mock.patch.object(setup, "ALLOW_UNPINNED", True):
            eng, out, heads, got = self.run_get([setup.PREBUILT_URL])
        self.assertEqual(eng, self.root / "engine")
        self.assertEqual(got, [setup.PREBUILT_URL + setup.PREBUILT_ASSET])

    def test_a_release_without_pins_is_not_installed(self):
        with mock.patch.object(setup, "PREBUILT_PINS", {}):
            eng, out, heads, got = self.run_get([self.TAG])
        self.assertIsNone(eng)
        self.assertEqual(got, [])

    def test_another_engine_is_deleted(self):
        z = self.root / "engine" / setup.PREBUILT_ASSET
        with self.assertRaises(SystemExit):
            self.run_get([self.TAG], body=engine_zip({"version": "9.9.9", "archs": [89]}))
        self.assertFalse(z.exists())
        self.assertFalse(z.with_name(z.name + ".done").exists())
        self.assertFalse((self.root / "engine" / setup.EXE).exists())

    def test_a_folder_the_user_gave_is_not_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / setup.PREBUILT_ASSET).write_bytes(engine_zip({"version": "9.9.9", "archs": [89]}))
            eng, _ = quiet(setup.get_prebuilt, folder, {"arch": 89}, "gpu")
        self.assertEqual(eng, self.root / "engine")
        self.assertEqual(json.loads((eng / "BUILD.json").read_text())["version"], "9.9.9")

    def test_the_amd_engine_too(self):
        def urlopen(req, timeout=None):
            if not req.full_url.startswith(setup.PREBUILT_URL):
                raise not_found(req.full_url)
            return Response()

        got = []
        with mock.patch.object(setup.urllib.request, "urlopen", urlopen), \
                mock.patch.object(setup, "download", self.fake_download(got)):
            eng, out = quiet(setup.get_prebuilt_hip, setup.PREBUILT_URL, {"arch": "gfx1201"})
        self.assertIsNone(eng)
        self.assertEqual(got, [])
        self.assertIn("AMD engine at " + setup.PREBUILT_URL + " has no pinned SHA-256", out)

    def test_a_refused_archive_is_not_kept(self):
        """PR #324: a refused archive (too old, or no code for the GPU) kept its zip and .done mark, and every later
        run reused it ("already downloaded") instead of the published one."""
        for meta in ({"version": "0.1.0", "archs": [89]},
                     {"version": ".".join(map(str, setup.MIN_ENGINE)), "archs": [120]}):
            with self.subTest(meta=meta):
                body, got = engine_zip(meta), []
                with mock.patch.object(setup.urllib.request, "urlopen", lambda req, timeout=None: Response()), \
                        mock.patch.object(setup, "download", self.fake_download(got, body)), \
                        mock.patch.object(setup, "PREBUILT_PINS", {"0.1.31": {setup.PREBUILT_ASSET: pin_of(body)}}):
                    eng, _ = quiet(setup.get_prebuilt, setup.PREBUILT_URL, {"arch": 89}, "gpu")
                self.assertEqual(len(got), 1)                   # downloaded and checked, then refused
                self.assertIsNone(eng)
                z = self.root / "engine" / setup.PREBUILT_ASSET
                self.assertFalse(z.exists())
                self.assertFalse(z.with_name(z.name + ".done").exists())

    def test_an_archive_that_does_not_unpack_is_not_kept(self):
        """#397, for an archive that does not unpack (not a zip, or a damaged one): it kept its zip and .done mark,
        so every later run failed on it, even after the right one was published."""
        with tempfile.TemporaryDirectory() as folder:  # a --prebuilt folder, through the real download()
            asset = Path(folder) / setup.PREBUILT_ASSET
            asset.write_bytes(b"<html>not a zip</html>")
            with self.assertRaises(zipfile.BadZipFile):
                quiet(setup.get_prebuilt, folder, {"arch": 89}, "gpu")
            with zipfile.ZipFile(asset, "w") as z:
                z.writestr("BUILD.json", json.dumps({"version": ".".join(map(str, setup.MIN_ENGINE)), "archs": [89]}))
                z.writestr(setup.EXE, b"engine")
            eng, _ = quiet(setup.get_prebuilt, folder, {"arch": 89}, "gpu")
        self.assertEqual(eng, self.root / "engine")
        self.assertEqual((self.root / "engine" / setup.EXE).read_bytes(), b"engine")

    def test_an_installed_engine_is_kept(self):
        (self.root / "engine" / "BUILD.json").write_text(json.dumps(
            {"version": ".".join(map(str, setup.MIN_ENGINE)), "archs": [89]}))
        (self.root / "engine" / setup.EXE).write_bytes(b"old")

        def urlopen(req, timeout=None):
            raise AssertionError("asked the network for an installed engine")

        with mock.patch.object(setup.urllib.request, "urlopen", urlopen):
            eng, out = quiet(setup.get_prebuilt, setup.PREBUILT_URL, {"arch": 89}, "gpu")
        self.assertEqual(eng, self.root / "engine")
        self.assertEqual((self.root / "engine" / setup.EXE).read_bytes(), b"old")


class EnginePins(unittest.TestCase):
    def test_this_version_is_pinned(self):
        pins = setup.PREBUILT_PINS[setup.source_version()]
        self.assertEqual(set(pins), {"strata-windows-x64.zip", "strata-windows-x64-cuda12.zip",
                                     "strata-windows-x64-hip.zip"})
        for size, sha in pins.values():
            self.assertGreater(size, 0)
            self.assertRegex(sha, r"^[0-9a-f]{64}$")


class LlamaCpp(unittest.TestCase):
    """llama.cpp's zip (the source the engine is built from) is unpacked only with its pinned size and SHA-256."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("llama.cpp-3cf0325/ggml/CMakeLists.txt", "project(ggml)")
            z.writestr("llama.cpp-3cf0325/gguf-py/gguf/__init__.py", "")
        self.body = out.getvalue()
        self.published = self.root / "published.zip"
        self.published.write_bytes(self.body)

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, pin):
        with mock.patch.object(setup, "ROOT", self.root), \
                mock.patch.object(setup, "LLAMA_CPP_ZIP", str(self.published)), \
                mock.patch.object(setup, "LLAMA_CPP_ZIP_PIN", pin):
            return quiet(setup.get_llama_cpp)

    def test_the_pin(self):
        self.assertIn(setup.LLAMA_CPP_COMMIT, setup.LLAMA_CPP_ZIP)
        size, sha = setup.LLAMA_CPP_ZIP_PIN
        self.assertGreater(size, 0)
        self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_the_pinned_zip_is_unpacked(self):
        llama, out = self.get(pin_of(self.body))
        self.assertEqual(llama, self.root / "third_party" / "llama.cpp")
        self.assertTrue((llama / "ggml" / "CMakeLists.txt").exists())
        self.assertIn("checking llama.cpp-3cf0325.zip (SHA-256, 0 MB)", out)

    def test_another_zip_is_deleted(self):
        with self.assertRaises(SystemExit):
            self.get((len(self.body), "0" * 64))
        third = self.root / "third_party"
        self.assertEqual(sorted(p.name for p in third.iterdir()), [])
        with self.assertRaises(SystemExit):              # another size: deleted as well
            self.get((len(self.body) + 1, hashlib.sha256(self.body).hexdigest()))
        self.assertEqual(sorted(p.name for p in third.iterdir()), [])


class Requirements(unittest.TestCase):
    def test_every_package_is_pinned(self):
        lines = setup.requirement_lines()
        names = {setup.req_name(x) for x in lines}
        for p in setup.PY_PACKAGES:
            self.assertIn(p, names)
        for x in lines:
            self.assertIn("==", x, x)
        self.assertEqual(setup.req_name('numpy==2.5.3; python_version >= "3.12"'), "numpy")
        self.assertEqual(setup.req_name("charset_normalizer==3"), "charset-normalizer")

    def pip(self, stamp, packages, installed=()):
        ran = []
        with tempfile.TemporaryDirectory() as d:
            if stamp is not None:
                (Path(d) / ".strata-pip.json").write_text(json.dumps(stamp))
            with mock.patch.object(setup.sys, "prefix", d), \
                    mock.patch.object(setup, "run", lambda cmd, **kw: ran.append(cmd)), \
                    mock.patch.object(setup, "_installed", lambda name: name in installed):
                quiet(setup.pip_install, packages, "the packages")
            after = json.loads((Path(d) / ".strata-pip.json").read_text()) if ran else stamp
        return [c for cmd in ran for c in cmd if "==" in c or c in setup.PY_PACKAGES], after

    def test_fresh_install_gets_every_pin(self):
        lines = setup.requirement_lines()
        ran, stamp = self.pip(None, lines)
        self.assertEqual(ran, lines)
        self.assertEqual(sorted(stamp), sorted(lines))
        self.assertEqual(self.pip(stamp, lines)[0], [])                       # the second run: nothing

    def test_an_install_from_before_the_pins_is_left_alone(self):
        lines = setup.requirement_lines()
        legacy = sorted(setup.PY_PACKAGES) + ["nvidia-cublas==13.0.2.14"]
        deps = {"markupsafe", "certifi", "charset-normalizer", "idna", "urllib3", "colorama"}
        self.assertEqual(self.pip(legacy, lines, installed=deps)[0], [])
        missing = [p for p in legacy if p != "psutil"]                         # an older list without psutil
        ran, _ = self.pip(missing, lines, installed=deps)
        self.assertEqual(ran, ["psutil==7.2.2"])

    def test_a_changed_pin_is_installed(self):
        lines = setup.requirement_lines()
        old = [x.replace("tqdm==4.70.1", "tqdm==4.60.0") for x in lines]
        ran, _ = self.pip(old, lines)
        self.assertEqual(ran, ["tqdm==4.70.1"])


if __name__ == "__main__":
    unittest.main()
