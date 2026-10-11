"""Extract the pinned SDK bootstrapper's CAB metadata without launching setup."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("bootstrapper", type=Path)
args = parser.parse_args()
spec = json.loads(Path(__file__).with_name("buildspec.json").read_text(encoding="utf-8"))
payload = args.bootstrapper.read_bytes()
if hashlib.sha256(payload).hexdigest() != spec["toolchain"]["sdk_installer_sha256"]:
    raise SystemExit("SDK bootstrapper hash mismatch")
offset = payload.find(b"MSCF")
if offset < 0:
    raise SystemExit("Embedded metadata cabinet missing")
size = struct.unpack_from("<I", payload, offset + 8)[0]
if size < 36 or offset + size > len(payload):
    raise SystemExit("Invalid embedded cabinet bounds")
directory = Path(tempfile.mkdtemp(prefix="neantik-sdk-metadata-"))
cabinet = directory / "bootstrap-metadata.cab"
cabinet.write_bytes(payload[offset:offset + size])
subprocess.run(["expand.exe", "-F:*", str(cabinet), str(directory)], check=True, capture_output=True)
print(json.dumps({"metadata_directory": str(directory), "bootstrapper_sha256": spec["toolchain"]["sdk_installer_sha256"], "setup_executed": False}, indent=2))
