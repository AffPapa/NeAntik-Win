import hashlib
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from prepare_release_attestation import build_predicate


class PrepareReleaseAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tag = "v1.2.3-preview"
        self.commit = "a" * 40
        self.archive_path = self.root / "NeAntikWin-portable-v1.2.3-preview.zip"
        self.checksum_path = self.root / (self.archive_path.name + ".sha256")
        self.manifest_path = self.root / "NeAntikWin-portable-v1.2.3-preview.manifest.json"
        self._write_archive()
        digest = hashlib.sha256(self.archive_path.read_bytes()).hexdigest()
        self.checksum_path.write_text(f"{digest}  {self.archive_path.name}\n", encoding="utf-8")
        self.manifest_path.write_text(json.dumps({
            "version": "1.2.3-preview",
            "source_commit": self.commit,
            "source_state": "clean",
            "source_tree_sha256": "b" * 64,
            "archive": {"filename": self.archive_path.name, "sha256": digest, "size_bytes": self.archive_path.stat().st_size},
        }), encoding="utf-8")
        checksum_digest = hashlib.sha256(self.checksum_path.read_bytes()).hexdigest()
        manifest_digest = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self.release = {
            "tag_name": self.tag,
            "draft": False,
            "repository": "AffPapa/NeAntik-Win",
            "html_url": "https://github.com/AffPapa/NeAntik-Win/releases/tag/" + self.tag,
            "tag_commit": self.commit,
            "assets": [
                {"name": self.archive_path.name, "size": self.archive_path.stat().st_size, "digest": "sha256:" + digest},
                {"name": self.archive_path.name + ".sha256", "size": self.checksum_path.stat().st_size, "digest": "sha256:" + checksum_digest},
                {"name": "NeAntikWin-portable-v1.2.3-preview.manifest.json", "size": self.manifest_path.stat().st_size, "digest": "sha256:" + manifest_digest},
            ],
        }

    def _write_archive(self, source_commit=None):
        source_commit = source_commit or self.commit
        version = {"version": "1.2.3-preview"}
        fields = {"version": "1.2.3-preview", "source_commit": source_commit, "source_state": "clean", "source_tree_sha256": "b" * 64}
        with zipfile.ZipFile(self.archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            root = "NeAntikWin-portable-v1.2.3-preview/"
            archive.writestr(root + "release-version.json", json.dumps(version))
            archive.writestr(root + "release-manifest.json", json.dumps(fields))
            archive.writestr(root + "build-provenance.json", json.dumps(fields))

    def _refresh_asset_digest(self, name, path):
        asset = next(asset for asset in self.release["assets"] if asset["name"] == name)
        asset["size"] = path.stat().st_size
        asset["digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def test_accepts_matching_release_and_tag(self):
        predicate = build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)
        self.assertEqual(predicate["source"]["annotatedTagCommit"], self.commit)
        self.assertIn("does not prove a reproducible build", " ".join(predicate["limitations"]))

    def test_rejects_digest_mismatch(self):
        self.release["assets"][0]["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "GitHub Release metadata"):
            build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)

    def test_rejects_tag_and_embedded_commit_mismatch(self):
        self.release["tag_commit"] = "c" * 40
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["source_commit"] = self.release["tag_commit"]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self._refresh_asset_digest("NeAntikWin-portable-v1.2.3-preview.manifest.json", self.manifest_path)
        with self.assertRaisesRegex(ValueError, "source_commit"):
            build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)

    def test_rejects_unpublished_or_wrong_repository_release(self):
        self.release["draft"] = True
        with self.assertRaisesRegex(ValueError, "non-draft"):
            build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)
        self.release["draft"] = False
        self.release["repository"] = "attacker/other"
        with self.assertRaisesRegex(ValueError, "repository"):
            build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)

    def test_rejects_tampered_checksum_sidecar(self):
        self.checksum_path.write_text("0" * 64 + "  " + self.archive_path.name, encoding="utf-8")
        self._refresh_asset_digest(self.archive_path.name + ".sha256", self.checksum_path)
        with self.assertRaisesRegex(ValueError, "sidecar"):
            build_predicate(self.release, self.archive_path, self.checksum_path, self.manifest_path)

    def test_workflow_is_manual_and_scoped_to_review_only(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "attest-existing-release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotRegex(workflow, re.compile(r"(?m)^\s{2}(?:push|pull_request):"))
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6", workflow)
        self.assertIn("verify-release-archive.ps1", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
