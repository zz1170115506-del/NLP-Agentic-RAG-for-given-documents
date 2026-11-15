"""Authenticated, bounded-memory encryption for the handoff's numbered volumes.

Each invocation creates a fresh 256-bit key in a separate local file (0600).
Each data frame and an obligatory final frame use AES-256-GCM authentication.
Nonces are the unique uint32 part number followed by uint64 frame number.
The complete header and frame position are authenticated as associated data.
Never upload the key or plaintext volumes; upload only this output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"CRAGAE1\x00"
BLOCK = 4 * 1024 * 1024
LIMIT = 2**31


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def exact(stream, length):
    value = stream.read(length)
    if len(value) != length:
        raise ValueError("Encrypted volume is truncated")
    return value


def nonce(part, frame):
    return struct.pack(">IQ", part, frame)


def aad(header, role, frame, length):
    return MAGIC + header + role + struct.pack(">QQ", frame, length)


def read_key(path):
    if path.is_symlink():
        raise ValueError("Key must be a regular local file")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("Expected a 32-byte key")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Key must be readable only by its owner: chmod 600 key-file")
    return key


def check_inner(inner):
    if not inner.get("parts") or not 0 < inner["part_limit_bytes"] < LIMIT:
        raise ValueError("Invalid plaintext volume manifest")
    for index, row in enumerate(inner["parts"], 1):
        if index >= 2**32 or row["name"] != f"course-data.tar.gz.part{index:05d}":
            raise ValueError("Unexpected plaintext part order or name")
        if not 0 < row["bytes"] <= inner["part_limit_bytes"]:
            raise ValueError("Invalid plaintext part size")


def encrypt(args):
    inner = json.loads(args.volumes.read_text())
    check_inner(inner)
    source = args.volumes.parent
    label = getattr(args, "label", "")
    if label and not re.fullmatch(r"[a-z0-9_-]{1,48}", label):
        raise ValueError("Label must use 1-48 lowercase letters, digits, underscores or hyphens")
    if args.key_file.is_symlink():
        raise ValueError("Key destination must not be a symlink")
    output, key_path = args.output.resolve(), args.key_file.resolve()
    if output.exists() or key_path.exists() or key_path.is_symlink():
        raise ValueError("Encryption output and key file must both be new")
    if key_path.is_relative_to(output):
        raise ValueError("The key must be stored outside the public upload directory")
    for row in inner["parts"]:
        path = source / row["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row["bytes"]:
            raise ValueError("Plaintext volume size/type differs")
        # Header <= 4096 bytes, one 16-byte tag and 4-byte size per 4 MiB frame.
        if row["bytes"] + math.ceil(row["bytes"] / BLOCK) * 20 + 4132 >= LIMIT:
            raise ValueError("Encrypted volume would exceed the strict 2 GiB ceiling")
    output.mkdir(parents=True)
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = AESGCM.generate_key(bit_length=256)
    with os.fdopen(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(key)
        handle.flush()
        os.fsync(handle.fileno())
    cipher, package_id = AESGCM(key), os.urandom(16).hex()
    key_id = hashlib.sha256(key).hexdigest()[:24]
    outer = {"format_version": 1, "algorithm": "AES-256-GCM-framed-v1", "package_id": package_id, "label": label,
             "key_id": key_id, "chunk_bytes": BLOCK, "inner_volumes": inner,
             "crypto_script_sha256": file_hash(Path(__file__)), "parts": []}
    combined = hashlib.sha256()
    for index, row in enumerate(inner["parts"], 1):
        header = {"format_version": 1, "algorithm": outer["algorithm"], "package_id": package_id,
                  "key_id": key_id, "part": index, "plaintext_name": row["name"],
                  "plaintext_bytes": row["bytes"], "plaintext_sha256": row["sha256"],
                  "total_parts": len(inner["parts"]), "archive_bytes": inner["archive_bytes"],
                  "archive_sha256": inner["archive_sha256"], "handoff_sha256": inner["handoff_sha256"],
                  "chunk_bytes": BLOCK, "chunk_count": math.ceil(row["bytes"] / BLOCK)}
        raw = canonical(header)
        name = (label + "." if label else "") + row["name"] + ".aead"
        temporary = output / (name + ".partial")
        digest, total = hashlib.sha256(), 0
        with (source / row["name"]).open("rb") as original, temporary.open("xb") as encrypted:
            encrypted.write(MAGIC + struct.pack(">I", len(raw)) + raw)
            for frame in range(header["chunk_count"]):
                data = original.read(BLOCK)
                digest.update(data)
                combined.update(data)
                total += len(data)
                encoded = cipher.encrypt(nonce(index, frame), data, aad(raw, b"DATA", frame, len(data)))
                encrypted.write(struct.pack(">I", len(encoded)) + encoded)
            if original.read(1) or total != row["bytes"] or digest.hexdigest() != row["sha256"]:
                raise ValueError("Plaintext changed or checksum differs; no valid encrypted manifest produced")
            final = cipher.encrypt(nonce(index, header["chunk_count"]), b"",
                                   aad(raw, b"FINAL", header["chunk_count"], total))
            encrypted.write(struct.pack(">I", len(final)) + final)
            encrypted.flush()
            os.fsync(encrypted.fileno())
        temporary.rename(output / name)
        outer["parts"].append({"name": name, "bytes": (output / name).stat().st_size,
                               "sha256": file_hash(output / name)})
    if combined.hexdigest() != inner["archive_sha256"]:
        raise ValueError("Combined plaintext archive checksum differs")
    write_json(output / "ENCRYPTED_VOLUMES.json", outer)
    (output / "SHA256SUMS").write_text("".join(
        f"{row['sha256']}  {row['name']}\n" for row in outer["parts"]), encoding="utf-8")
    print(json.dumps({"status": "encrypted", "package_id": package_id, "key_id": key_id,
                      "parts": len(outer["parts"]), "max_part_bytes": max(r["bytes"] for r in outer["parts"])}))


def decrypt(args):
    outer = json.loads(args.manifest.read_text())
    if outer.get("format_version") != 1 or outer.get("algorithm") != "AES-256-GCM-framed-v1" or outer.get("chunk_bytes") != BLOCK:
        raise ValueError("Unsupported encrypted package format")
    inner = outer["inner_volumes"]
    label = outer.get("label", "")
    if label and not re.fullmatch(r"[a-z0-9_-]{1,48}", label):
        raise ValueError("Invalid encrypted package label")
    check_inner(inner)
    if len(inner["parts"]) != len(outer["parts"]):
        raise ValueError("Encrypted part count differs")
    key = read_key(args.key_file)
    if hashlib.sha256(key).hexdigest()[:24] != outer["key_id"]:
        raise ValueError("Key does not match this package")
    cipher, destination = AESGCM(key), args.output.resolve()
    temporary = destination.with_name(destination.name + ".partial")
    if destination.exists() or temporary.exists():
        raise ValueError("Decryption destination must be new")
    combined, all_bytes = hashlib.sha256(), 0
    temporary.mkdir(parents=True, mode=0o700)
    try:
        for index, (plain, encrypted) in enumerate(zip(inner["parts"], outer["parts"], strict=True), 1):
            if encrypted["name"] != (label + "." if label else "") + plain["name"] + ".aead":
                raise ValueError("Encrypted part order differs")
            path = args.manifest.parent / encrypted["name"]
            if path.is_symlink() or not 0 < encrypted["bytes"] < LIMIT or path.stat().st_size != encrypted["bytes"]:
                raise ValueError("Encrypted part size/type differs")
            if file_hash(path) != encrypted["sha256"]:
                raise ValueError("Encrypted part checksum differs")
            with path.open("rb") as source, (temporary / plain["name"]).open("xb") as target:
                if exact(source, len(MAGIC)) != MAGIC:
                    raise ValueError("Encrypted volume magic differs")
                length = struct.unpack(">I", exact(source, 4))[0]
                if not 0 < length <= 4096:
                    raise ValueError("Invalid encrypted header length")
                raw = exact(source, length)
                header = json.loads(raw)
                expected = {"format_version": 1, "algorithm": outer["algorithm"], "package_id": outer["package_id"],
                            "key_id": outer["key_id"], "part": index, "plaintext_name": plain["name"],
                            "plaintext_bytes": plain["bytes"], "plaintext_sha256": plain["sha256"],
                            "total_parts": len(inner["parts"]), "archive_bytes": inner["archive_bytes"],
                            "archive_sha256": inner["archive_sha256"], "handoff_sha256": inner["handoff_sha256"],
                            "chunk_bytes": BLOCK, "chunk_count": math.ceil(plain["bytes"] / BLOCK)}
                if header != expected or raw != canonical(expected):
                    raise ValueError("Encrypted header identity differs")
                digest, total = hashlib.sha256(), 0
                for frame in range(header["chunk_count"]):
                    needed = min(BLOCK, plain["bytes"] - total)
                    size = struct.unpack(">I", exact(source, 4))[0]
                    if size != needed + 16:
                        raise ValueError("Encrypted frame size differs")
                    data = cipher.decrypt(nonce(index, frame), exact(source, size), aad(raw, b"DATA", frame, needed))
                    target.write(data)
                    digest.update(data)
                    combined.update(data)
                    total += len(data)
                if struct.unpack(">I", exact(source, 4))[0] != 16:
                    raise ValueError("Missing authenticated final frame")
                cipher.decrypt(nonce(index, header["chunk_count"]), exact(source, 16),
                               aad(raw, b"FINAL", header["chunk_count"], total))
                if source.read(1) or total != plain["bytes"] or digest.hexdigest() != plain["sha256"]:
                    raise ValueError("Plaintext identity differs or trailing data exists")
                all_bytes += total
        if all_bytes != inner["archive_bytes"] or combined.hexdigest() != inner["archive_sha256"]:
            raise ValueError("Decrypted archive identity differs")
        write_json(temporary / "VOLUMES.json", inner)
        (temporary / "SHA256SUMS").write_text("".join(
            f"{row['sha256']}  {row['name']}\n" for row in inner["parts"]), encoding="utf-8")
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    print(json.dumps({"status": "authenticated_and_decrypted", "parts": len(outer["parts"]),
                      "archive_sha256": inner["archive_sha256"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    enc = sub.add_parser("encrypt")
    enc.add_argument("--volumes", type=Path, required=True)
    enc.add_argument("--output", type=Path, required=True)
    enc.add_argument("--key-file", type=Path, required=True)
    enc.add_argument("--label", default="", help="Unique public asset prefix, e.g. data or run-evidence")
    dec = sub.add_parser("decrypt")
    dec.add_argument("--manifest", type=Path, required=True)
    dec.add_argument("--output", type=Path, required=True)
    dec.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    encrypt(args) if args.command == "encrypt" else decrypt(args)


if __name__ == "__main__":
    main()
