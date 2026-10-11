"""Synthetic packaging fixtures, never a claim of compiled Chromium success."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

module_spec = importlib.util.spec_from_file_location("native_package", Path(__file__).with_name("package-engine.py"))
package = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(package)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="neantik-package-qa-")
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "chromium" / "src"
        self.output = self.source / "out" / "NeAntik"
        self.output.mkdir(parents=True)
        self.destination = self.root / "portable" / "Engine" / "NeAntikChromium"
        self.names = ("chrome.exe", "chrome.dll", "chrome_elf.dll", "resources.pak", "locales/en-US.pak")
        for name in self.names:
            file = self.output / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"synthetic runtime")
        self.document = {"//chrome:chrome": {"runtime_deps": list(self.names)}}
        self.credits = self.root / "credits.html"
        self.credits.write_text("<html>synthetic license fixture</html>", encoding="utf-8")
        self.licenses = self.root / "licenses.txt"
        self.licenses.write_text("synthetic third-party license", encoding="utf-8")
        (self.source / "LICENSE").write_bytes(b"synthetic upstream BSD license")
        (self.source / "DEPS").write_bytes(b"synthetic deps")
        spec = json.loads(Path(__file__).with_name("buildspec.json").read_text())
        (self.output / "args.gn").write_text("\n".join(spec["gn_args"]), encoding="utf-8")
        compiler = self.source / "third_party/llvm-build/Release+Asserts/bin/clang-cl.exe"
        compiler.parent.mkdir(parents=True)
        compiler.write_bytes(b"synthetic compiler")
        self.receipt = self.root / "receipt.json"
        self.receipt.write_text(json.dumps({"source_commit": package.core.SOURCE_COMMIT,
            "resolved_dependencies": [{"path": "src/third_party/mock", "origin": "https://example.invalid/mock", "revision": "abc", "kind": "git"}]}))

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, execute=True):
        with patch.object(package, "verify_source", return_value={"mock": True}), patch.object(package, "query_runtime", return_value=self.document), patch.object(package.subprocess, "run", return_value=SimpleNamespace(stdout=b"synthetic clang version")), patch.object(package.core.CoreResolver, "_probe"):
            return package.package(self.source, self.output, self.destination, self.credits, self.licenses, self.receipt, execute)

    def test_readonly_plan_then_atomic_package_exact_manifest(self):
        self.assertEqual(self.execute(False)["state"], "read-only-package-plan")
        self.assertFalse(self.destination.parent.exists())
        result = self.execute()
        self.assertEqual(result["state"], "packaged-runtime-info-verified")
        manifest_path = self.destination / package.core.MANIFEST_NAME
        self.assertEqual(result["manifest_sha256"], package.core.sha256_file(manifest_path))
        manifest = json.loads(manifest_path.read_text())
        self.assertTrue({"LICENSE", "credits.html", "THIRD_PARTY_LICENSES.txt", "DEPENDENCY_RECEIPT.json", "BUILD_PROVENANCE.json"} <= manifest["files"].keys())
        with patch.object(package.core.CoreResolver, "_probe"):
            self.assertEqual(package.core.CoreResolver(self.destination.parent.parent).resolve(), self.destination / "chrome.exe")
        with self.assertRaisesRegex(ValueError, "new Engine"):
            self.execute()

    def test_unsafe_and_case_colliding_runtime_paths_rejected(self):
        for path in ("../secret.txt", "C:/Data/token", "//server/share", "x\\y", "NUL", "a/COM1.txt", "a/b."):
            with self.subTest(path=path), self.assertRaises(ValueError):
                package.safe_relative(path)
        self.document["//chrome:chrome"]["runtime_deps"].append("Chrome.exe")
        with self.assertRaisesRegex(ValueError, "Case-colliding"):
            package.runtime_inventory(self.output, self.document)

    def test_debug_symbols_are_only_explicitly_omitted_class(self):
        self.document["//chrome:chrome"]["runtime_deps"] += ["./chrome.exe.pdb", "./chrome.exe"]
        self.assertEqual(set(package.runtime_inventory(self.output, self.document)), set(self.names))
        self.document["//chrome:chrome"]["runtime_deps"].append("missing.dll")
        with self.assertRaisesRegex(ValueError, "missing"):
            package.runtime_inventory(self.output, self.document)

    def test_receipt_rejects_local_paths_secrets_and_unpinned_source(self):
        valid = json.loads(self.receipt.read_text())
        package.validate_dependency_receipt(valid)
        for value in ({**valid, "token": "secret"}, {**valid, "source_commit": "bad"},
                      {**valid, "resolved_dependencies": [{"path": "<user-profile>", "revision": "abc"}]},
                      {**valid, "resolved_dependencies": [{"path": "src/mock", "revision": "abc", "origin": "https://user:pass@example.invalid/repo"}]}):
            with self.assertRaises(ValueError):
                package.validate_dependency_receipt(value)

    def test_gn_args_mismatch_rejected_before_packaging(self):
        (self.output / "args.gn").write_text('is_debug=true')
        with self.assertRaisesRegex(ValueError, "GN args"):
            self.execute()

    def test_existing_bundle_requires_exact_independent_qa(self):
        result = self.execute()
        sha = result["manifest_sha256"]
        qa = self.root / "qa.json"
        report = {"format": "neantik-own155-native-qa-v1", "status": "passed",
                  "verification": {"manifest_sha256": sha, "bundle_reverified_after_visits": True},
                  "assertions": [{"passed": True}]}
        qa.write_text(json.dumps(report))
        with patch.object(package.core.CoreResolver, "_probe"):
            self.assertEqual(package.verify_existing(self.destination, sha, qa)["qa_status"], "passed")
        report["assertions"][0]["passed"] = False
        qa.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "QA report"):
            package.verify_existing(self.destination, sha, qa)
        with self.assertRaisesRegex(ValueError, "manifest SHA"):
            package.verify_existing(self.destination, "0" * 64, qa)


if __name__ == "__main__":
    unittest.main()
