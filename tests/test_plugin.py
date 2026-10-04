import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="asdf esp-idf tests ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        fakebin = self.work / "fakebin"
        fakebin.mkdir()
        curl = fakebin / "curl"
        curl.write_text("""#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
from urllib.parse import parse_qs, urlparse
args = sys.argv[1:]
if '-o' in args:
    target = pathlib.Path(args[args.index('-o') + 1])
    if os.environ.get('FAIL_DOWNLOAD'):
        target.write_text('partial download')
        sys.exit(18)
    shutil.copyfile(os.environ['FIXTURE_ZIP'], target)
else:
    page = int(parse_qs(urlparse(args[-1]).query).get('page', ['1'])[0])
    if str(page) == os.environ.get('FAIL_PAGE'):
        sys.exit(22)
    pages = json.loads(pathlib.Path(os.environ['FIXTURE_RELEASES']).read_text())
    print(json.dumps(pages[page - 1] if page <= len(pages) else []))
""")
        curl.chmod(0o755)
        self.download = self.work / "download"
        self.install = self.work / "install"
        self.releases = self.work / "releases.json"
        self.archive = self.work / "release.zip"
        self.env = dict(os.environ)
        for name in ("IDF_PATH", "REVIEW_ACTIVATED", "BASH_ENV", "ENV"):
            self.env.pop(name, None)
        self.env.update(
            PATH=str(fakebin) + os.pathsep + os.environ["PATH"],
            FIXTURE_RELEASES=str(self.releases), FIXTURE_ZIP=str(self.archive),
            ASDF_INSTALL_VERSION="5.5.4", ASDF_INSTALL_TYPE="version",
            ASDF_DOWNLOAD_PATH=str(self.download), ASDF_INSTALL_PATH=str(self.install),
        )
        self.write_releases()
        self.write_archive()

    def write_releases(self):
        def release(version, **extra):
            return dict(assets=[dict(name=f"esp-idf-v{version}.zip")], **extra)
        first = [release("5.5.4"), release("6.0-beta1", prerelease=True)]
        first += [dict(assets=[])] * 98
        second = [release("5.4.3"), release("5.4.2"), release("5.5.4")]
        self.releases.write_text(json.dumps([first, second]))

    def write_archive(self, export="export REVIEW_ACTIVATED=yes\n"):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("esp-idf/install.sh", "exit 0\n")
            archive.writestr("esp-idf/export.sh", export)
            archive.writestr("esp-idf/.hidden", "included\n")

    def hook(self, name, *args):
        return subprocess.run([str(ROOT / "bin" / name), *args], env=self.env,
                              cwd=self.work, text=True, capture_output=True)

    def prepare_install(self, export="export REVIEW_ACTIVATED=yes\n"):
        self.write_archive(export)
        for hook in ("download", "install"):
            result = self.hook(hook)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_list_all_paginates_deduplicates_and_sorts(self):
        result = self.hook("list-all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "5.4.2 5.4.3 5.5.4 6.0-beta1")

    def test_latest_filter(self):
        for prefix, expected in (("", "5.5.4"), ("5.4", "5.4.3"), ("5.4.2", "5.4.2")):
            with self.subTest(prefix=prefix):
                result = self.hook("latest-stable", prefix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_latest_no_match_fails(self):
        result = self.hook("latest-stable", "9.9")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_latest_excludes_github_prereleases_without_suffixes(self):
        self.releases.write_text(json.dumps([[
            dict(assets=[dict(name="esp-idf-v6.0.zip")], prerelease=True),
            dict(assets=[dict(name="esp-idf-v5.5.4.zip")]),
        ]]))
        result = self.hook("latest-stable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "5.5.4")

    def test_later_page_failure_does_not_return_partial_versions(self):
        self.env["FAIL_PAGE"] = "2"
        for hook in ("list-all", "latest-stable"):
            result = self.hook(hook)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_archive_install_and_activation(self):
        self.prepare_install()
        self.assertEqual((self.install / ".hidden").read_text(), "included\n")
        for shell in ("bash", "zsh"):
            self.assertIsNotNone(shutil.which(shell), f"{shell} is required for tests")
            for helper in ("get_idf", "bin/get_idf"):
                with self.subTest(shell=shell, helper=helper):
                    result = subprocess.run(
                        [shell, "-f", "-c", '. "$1"; rc=$?; printf "%s\\n%s\\n%s\\n" "$rc" "$IDF_PATH" "$REVIEW_ACTIVATED"',
                         "test", str(self.install / helper)],
                        env=self.env, cwd=self.work, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(result.stdout.splitlines(), ["0", str(self.install), "yes"])

    def test_activation_failure_propagates(self):
        self.prepare_install('return 23\n')
        for shell in ("bash", "zsh"):
            for helper in ("get_idf", "bin/get_idf"):
                with self.subTest(shell=shell, helper=helper):
                    result = subprocess.run([shell, "-f", "-c", '. "$1"', "test", str(self.install / helper)],
                                            env=self.env, cwd=self.work, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 23, result.stderr)

    def test_executed_helpers_reject_activation(self):
        self.prepare_install()
        for helper in ("get_idf", "bin/get_idf"):
            result = subprocess.run([str(self.install / helper)], env=self.env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be sourced", result.stderr)

    def test_shell_function_activation_and_arguments(self):
        self.prepare_install('export REVIEW_ACTIVATED="$1"\n')
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                result = subprocess.run(
                    [shell, "-f", "-c",
                     'helper=$1; get_idf() { . "$helper" "$@"; }; get_idf "argument with spaces"; printf "%s\\n" "$REVIEW_ACTIVATED"',
                     "test", str(self.install / "bin/get_idf")],
                    env=self.env, cwd=self.work, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout.strip(), "argument with spaces")

    def test_install_without_download_hook(self):
        self.env.pop("ASDF_DOWNLOAD_PATH")
        result = self.hook("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.install / "export.sh").is_file())

    def test_download_accepts_existing_empty_directory(self):
        self.download.mkdir()
        result = self.hook("download")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(path.name for path in self.download.iterdir()),
                         [".hidden", "export.sh", "install.sh"])

    def test_download_preserves_existing_nonempty_directory(self):
        self.download.mkdir()
        marker = self.download / "existing"
        marker.write_text("keep me")
        result = self.hook("download")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), "keep me")
        self.assertEqual(list(self.download.iterdir()), [marker])

    def test_failed_download_leaves_no_partial_files(self):
        self.env["FAIL_DOWNLOAD"] = "1"
        result = self.hook("download")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.download.exists() and list(self.download.iterdir()))
        self.assertEqual(list(self.work.glob("download.tmp.*")), [])

    def test_corrupt_archive_leaves_no_partial_files(self):
        self.archive.write_text("not a zip")
        result = self.hook("download")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.download.exists() and list(self.download.iterdir()))


if __name__ == "__main__":
    unittest.main()
