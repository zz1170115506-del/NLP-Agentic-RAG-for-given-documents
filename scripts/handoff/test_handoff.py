"""Small synthetic roundtrips and corruption tests; never opens real project data."""
import argparse
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from cryptography.exceptions import InvalidTag

import handoff_archive as archive
import handoff_crypto as crypto
from handoff_paths import documentation_dir


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="synthetic-handoff-"))
        cls.plain = cls.base / "plain"
        cls.plain.mkdir()
        blocks = [os.urandom(crypto.BLOCK * 2 + 37), os.urandom(83)]
        rows = []
        for index, block in enumerate(blocks, 1):
            name = f"course-data.tar.gz.part{index:05d}"
            (cls.plain / name).write_bytes(block)
            rows.append({"name": name, "bytes": len(block), "sha256": hashlib.sha256(block).hexdigest()})
        archive_hash = hashlib.sha256(b"".join(blocks)).hexdigest()
        crypto.write_json(cls.plain / "VOLUMES.json", {"format_version": 1, "parts": rows,
            "part_limit_bytes": archive.PART_BYTES, "archive_bytes": sum(map(len, blocks)),
            "archive_sha256": archive_hash, "handoff_sha256": "fixture"})
        cls.encrypted, cls.key = cls.base / "encrypted", cls.base / "private" / "fixture.key"
        with redirect_stdout(io.StringIO()):
            crypto.encrypt(argparse.Namespace(volumes=cls.plain / "VOLUMES.json", output=cls.encrypted, key_file=cls.key))

    def case(self):
        root = Path(tempfile.mkdtemp(prefix="case-", dir=self.base))
        encrypted = root / "encrypted"
        shutil.copytree(self.encrypted, encrypted)
        return root, encrypted

    def decrypt(self, encrypted, output, key=None):
        with redirect_stdout(io.StringIO()):
            crypto.decrypt(argparse.Namespace(manifest=encrypted / "ENCRYPTED_VOLUMES.json",
                                               output=output, key_file=key or self.key))

    def change_cipher(self, encrypted, transform):
        manifest_path = encrypted / "ENCRYPTED_VOLUMES.json"
        manifest = json.loads(manifest_path.read_text())
        first = manifest["parts"][0]
        path = encrypted / first["name"]
        changed = transform(bytearray(path.read_bytes()))
        path.write_bytes(changed)
        # Update untrusted public hashes to ensure actual AEAD rejects the tamper.
        first.update(bytes=len(changed), sha256=hashlib.sha256(changed).hexdigest())
        crypto.write_json(manifest_path, manifest)

    def assert_rejected(self, encrypted, output, error=(ValueError, InvalidTag)):
        with self.assertRaises(error):
            self.decrypt(encrypted, output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_name(output.name + ".partial").exists())

    def test_01_crypto_roundtrip_and_key_permissions(self):
        output = self.base / "roundtrip"
        self.decrypt(self.encrypted, output)
        for path in self.plain.glob("*.part*"):
            self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
        self.assertFalse(any("key" in p.name.lower() for p in self.encrypted.iterdir()))
        self.assertLess(max(p.stat().st_size for p in self.encrypted.iterdir()), 2**31)

    def test_02_ciphertext_modification_rejected_by_tag(self):
        root, encrypted = self.case()
        def mutate(raw):
            offset = 12 + struct.unpack(">I", raw[8:12])[0] + 4
            raw[offset + 100] ^= 1
            return raw
        self.change_cipher(encrypted, mutate)
        self.assert_rejected(encrypted, root / "restore", InvalidTag)

    def test_03_frame_reordering_rejected_by_tag(self):
        root, encrypted = self.case()
        def mutate(raw):
            start = 12 + struct.unpack(">I", raw[8:12])[0]
            width = 4 + crypto.BLOCK + 16
            first, second = raw[start:start + width], raw[start + width:start + 2 * width]
            raw[start:start + 2 * width] = second + first
            return raw
        self.change_cipher(encrypted, mutate)
        self.assert_rejected(encrypted, root / "restore", InvalidTag)

    def test_04_truncated_final_frame_rejected(self):
        root, encrypted = self.case()
        self.change_cipher(encrypted, lambda raw: raw[:-20])
        self.assert_rejected(encrypted, root / "restore", ValueError)

    def test_05_extra_bytes_rejected(self):
        root, encrypted = self.case()
        self.change_cipher(encrypted, lambda raw: raw + b"trailing")
        self.assert_rejected(encrypted, root / "restore", ValueError)

    def test_06_final_authentication_tag_rejected(self):
        root, encrypted = self.case()
        def mutate(raw):
            raw[-1] ^= 1
            return raw
        self.change_cipher(encrypted, mutate)
        self.assert_rejected(encrypted, root / "restore", InvalidTag)

    def test_07_wrong_key_rejected(self):
        root, encrypted = self.case()
        key = root / "wrong.key"
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        with self.assertRaises(ValueError):
            self.decrypt(encrypted, root / "restore", key)
        self.assertFalse((root / "restore").exists())

    def test_08_header_and_public_identity_tamper_rejected(self):
        root, encrypted = self.case()
        path = encrypted / "ENCRYPTED_VOLUMES.json"
        outer = json.loads(path.read_text())
        previous = outer["package_id"]
        outer["package_id"] = "0" * 32
        crypto.write_json(path, outer)
        self.change_cipher(encrypted, lambda raw: raw.replace(previous.encode(), b"0" * 32, 1))
        self.assert_rejected(encrypted, root / "restore", InvalidTag)

    def test_09_missing_or_reordered_volumes_rejected(self):
        for operation in ("missing", "reorder"):
            with self.subTest(operation=operation):
                root, encrypted = self.case()
                path = encrypted / "ENCRYPTED_VOLUMES.json"
                outer = json.loads(path.read_text())
                outer["parts"] = outer["parts"][:1] if operation == "missing" else list(reversed(outer["parts"]))
                crypto.write_json(path, outer)
                self.assert_rejected(encrypted, root / "restore", ValueError)

    def test_10_key_reuse_rejected(self):
        with self.assertRaises(ValueError):
            crypto.encrypt(argparse.Namespace(volumes=self.plain / "VOLUMES.json",
                                               output=self.base / "reuse-output", key_file=self.key))

    def test_11_tiny_sqlite_vector_archive_roundtrip(self):
        root = self.base / "tiny-archive"
        source = root / "source"
        source.mkdir(parents=True)
        (source / "src").mkdir()
        (source / "src" / "example.py").write_text("# Synthetic fixture only\n")
        corpus = {"fingerprint": "synthetic-fingerprint", "document_count": 2, "chunk_count": 4,
                  "chunking": {"size": 256, "overlap": 0, "unit": "python_unicode_characters"},
                  "importing": False, "source": {"type": "synthetic"}}
        document_path = source / archive.DATABASES[0]
        document_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(document_path)
        conn.executescript("CREATE TABLE documents(doc_id TEXT PRIMARY KEY,text TEXT,url TEXT);"
                           "CREATE TABLE chunks(seq INTEGER PRIMARY KEY,chunk_id TEXT,doc_id TEXT,offset INTEGER,text TEXT,url TEXT);"
                           "CREATE TABLE metadata(key TEXT,value TEXT);")
        chunks = []
        for number in range(2):
            text = "university " + os.urandom(256).hex()
            doc_id = str(number)
            conn.execute("INSERT INTO documents VALUES(?,?,?)", (doc_id, text, "https://example.invalid"))
            for offset in (0, 256):
                chunks.append((len(chunks) + 1, f"{doc_id}:{offset}:256", doc_id, offset, text[offset:offset+256], "https://example.invalid"))
        conn.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?)", chunks)
        conn.executemany("INSERT INTO metadata VALUES(?,?)", [(k, json.dumps(v)) for k, v in corpus.items()])
        conn.commit()
        conn.close()
        sparse = source / archive.DATABASES[1]
        sparse.parent.mkdir(parents=True)
        conn = sqlite3.connect(sparse)
        conn.executescript("CREATE TABLE metadata(key TEXT,value TEXT);"
                           "CREATE TABLE records(seq INTEGER PRIMARY KEY,chunk_id TEXT,doc_id TEXT,offset INTEGER,text TEXT,url TEXT);"
                           "CREATE VIRTUAL TABLE fts USING fts5(text,content=records,content_rowid=seq);")
        conn.executemany("INSERT INTO records VALUES(?,?,?,?,?,?)", chunks)
        conn.executemany("INSERT INTO metadata VALUES(?,?)", [("ready", "true"), ("fingerprint", corpus["fingerprint"])])
        conn.execute("INSERT INTO fts(fts) VALUES ('rebuild')")
        conn.commit()
        conn.close()
        archive.json_write(source / archive.SPARSE_MANIFEST, {"method": "sparse", "fingerprint": corpus["fingerprint"], "chunk_count": 4})
        for method, rel in archive.DENSE.items():
            folder = (source / rel).parent
            folder.mkdir(parents=True)
            sqlite3.connect(folder / "build-lock.sqlite").close()
            np.save(folder / "shard-000000.npy", np.ones((2, 4), dtype=np.float32))
            (folder / "shard-000000.jsonl").write_text('{"chunk_id":"0:0:256"}\n{"chunk_id":"0:256:256"}\n')
            shard = {"vectors": "shard-000000.npy", "metadata": "shard-000000.jsonl", "source_chunks": 2, "rows": 2,
                     "vectors_sha256": archive.digest(folder / "shard-000000.npy"),
                     "metadata_sha256": archive.digest(folder / "shard-000000.jsonl")}
            archive.json_write(source / rel, {"method": method, "fingerprint": corpus["fingerprint"],
                "source_chunk_count": 2, "vector_count": 2, "shards": [shard], "ready": False, "dimension": 4})
        expected = root / "inventory.json"
        archive.json_write(expected, archive.inventory(source))
        package = root / "package"
        with redirect_stdout(io.StringIO()):
            archive.pack(argparse.Namespace(source=source, output=package, expected_inventory=expected,
                license_evidence=documentation_dir() / "licenses", part_bytes=4096, execute=True, writers_stopped=True))
            archive.verify(argparse.Namespace(volumes=package / "VOLUMES.json", extract=root / "restored", semantic=True))
        volumes = json.loads((package / "VOLUMES.json").read_text())
        self.assertGreater(len(volumes["parts"]), 1)
        self.assertLessEqual(max(row["bytes"] for row in volumes["parts"]), 4096)
        for rel, target in archive.LINKS.items():
            self.assertEqual((root / "restored" / rel).readlink().as_posix(), target)
        handoff = json.loads((root / "restored" / "HANDOFF.json").read_text())
        malicious = copy.deepcopy(handoff)
        malicious["source_snapshot"]["dense"]["encoder"]["path"] = "../outside.json"
        with self.assertRaisesRegex(ValueError, "fixed expected path"):
            archive.checked_dense_paths(root / "restored", malicious)
        malicious = copy.deepcopy(handoff)
        malicious["source_snapshot"]["dense"]["encoder"]["manifest"]["shards"][0]["vectors"] = "../outside.npy"
        with self.assertRaisesRegex(ValueError, "Unsafe relative"):
            archive.checked_dense_paths(root / "restored", malicious)
        malicious = copy.deepcopy(handoff)
        malicious["source_snapshot"]["dense"]["encoder"]["manifest"]["shards"][0]["vectors_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "bound to the verified payload"):
            archive.checked_dense_paths(root / "restored", malicious)
        # Encrypt the actual miniature tar, decrypt independently and verify it again.
        encrypted, restored = root / "encrypted-package", root / "decrypted-package"
        with redirect_stdout(io.StringIO()):
            crypto.encrypt(argparse.Namespace(volumes=package / "VOLUMES.json", output=encrypted, key_file=root / "tiny.key"))
            crypto.decrypt(argparse.Namespace(manifest=encrypted / "ENCRYPTED_VOLUMES.json", output=restored, key_file=root / "tiny.key"))
            archive.verify(argparse.Namespace(volumes=restored / "VOLUMES.json", extract=root / "decrypted-restored", semantic=True))

    def test_12_unique_release_label_roundtrip(self):
        root = self.base / "label-test"
        encrypted, restored = root / "encrypted", root / "decrypted"
        with redirect_stdout(io.StringIO()):
            crypto.encrypt(argparse.Namespace(volumes=self.plain / "VOLUMES.json", output=encrypted,
                                               key_file=root / "label.key", label="run-evidence"))
            crypto.decrypt(argparse.Namespace(manifest=encrypted / "ENCRYPTED_VOLUMES.json", output=restored,
                                               key_file=root / "label.key"))
        outer = json.loads((encrypted / "ENCRYPTED_VOLUMES.json").read_text())
        self.assertTrue(all(row["name"].startswith("run-evidence.") for row in outer["parts"]))

    def test_13_selected_trace_archive_and_credential_refusal(self):
        root = self.base / "selected-test"
        source = root / "source"
        source.mkdir(parents=True)
        (source / "predictions.jsonl").write_text('{"id":"synthetic","answer":"fixture only"}\n')
        include = root / "include.json"
        include.write_text('["predictions.jsonl"]')
        output = root / "packed"
        command = [sys.executable, str(Path(__file__).with_name("pack_selected_files.py")),
                   "--source", str(source), "--include-list", str(include), "--output", str(output)]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with redirect_stdout(io.StringIO()):
            archive.verify(argparse.Namespace(volumes=output / "VOLUMES.json", extract=root / "restored", semantic=False))
        self.assertEqual((root / "restored" / "predictions.jsonl").read_bytes(), (source / "predictions.jsonl").read_bytes())
        for candidate in (".env", ".ENV", "private/key", "PRIVATE/key", "client.KEY", "HANDOFF.json"):
            include.write_text(json.dumps([candidate]))
            result = subprocess.run(command[:-1] + [str(root / "refused")], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Secret/configuration", result.stderr)
            self.assertFalse((root / "refused").exists())
        for unsafe in ("../escape", "/absolute", "C:/drive-escape", "relative:stream", "a\\b", "a\x00b"):
            with self.assertRaises(ValueError):
                archive.safe_name(unsafe)

    def test_14_package_tail_truncation_with_rewritten_manifest_and_header(self):
        root, encrypted = self.case()
        path = encrypted / "ENCRYPTED_VOLUMES.json"
        outer = json.loads(path.read_text())
        first = outer["inner_volumes"]["parts"][0]
        outer["parts"] = outer["parts"][:1]
        outer["inner_volumes"]["parts"] = [first]
        outer["inner_volumes"]["archive_bytes"] = first["bytes"]
        outer["inner_volumes"]["archive_sha256"] = first["sha256"]
        crypto.write_json(path, outer)

        def rewrite_header(raw):
            length = struct.unpack(">I", raw[8:12])[0]
            header = json.loads(raw[12:12 + length])
            header.update(total_parts=1, archive_bytes=first["bytes"], archive_sha256=first["sha256"])
            encoded = crypto.canonical(header)
            return crypto.MAGIC + struct.pack(">I", len(encoded)) + encoded + raw[12 + length:]

        self.change_cipher(encrypted, rewrite_header)
        self.assert_rejected(encrypted, root / "restore", InvalidTag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
