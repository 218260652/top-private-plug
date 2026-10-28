#!/usr/bin/env python3
"""Reproducible, explicit legacy test-TLS support for the pinned engine.

Only allowInsecure:true maps to a private sentinel. Ordinary profiles retain
normal certificate verification. The admin already requires explicit opt-in.
The copied/patched source is included in the rebuild-source artifact.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

VERSION = 'v1.260327.1-0.20261021115930-1b1647cd9ddf'
SENTINEL = 'tpp-legacy-test-insecure.invalid'


def replace(path, old, new):
    value = path.read_text()
    if value.count(old) != 1:
        raise SystemExit('Unexpected pinned source layout: ' + str(path))
    path.chmod(0o644)
    path.write_text(value.replace(old, new))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    target = source / 'tpp-xray-core'
    if not (target / 'TPP-COMPATIBILITY.txt').exists():
        if target.exists():
            raise SystemExit('Unexpected existing compatibility source')
        info = json.loads(subprocess.check_output(['go', 'mod', 'download', '-json', 'github.com/xtls/xray-core@' + VERSION], cwd=source, text=True))
        if info.get('Version') != VERSION or not info.get('Dir'):
            raise SystemExit('Pinned Xray source could not be resolved')
        shutil.copytree(info['Dir'], target)
        # Module-cache directories are read-only; this is a separate rebuild copy.
        target.chmod(0o755)
        for directory in target.rglob('*'):
            if directory.is_dir():
                directory.chmod(0o755)
        replace(target / 'infra/conf/transport_security.go',
            '\tif c.AllowInsecure {\n\t\treturn nil, errors.PrintRemovedFeatureError(`"allowInsecure"`, `"pinnedPeerCertSha256"(pcs) and "verifyPeerCertByName"(vcn)`)\n\t}',
            '\tif c.AllowInsecure {\n\t\tif c.PinnedPeerCertSha256 != "" || c.VerifyPeerCertByName != "" {\n\t\t\treturn nil, errors.New("legacy test TLS cannot be combined with certificate pins or verification-name overrides")\n\t\t}\n\t\tc.VerifyPeerCertByName = "' + SENTINEL + '"\n\t}')
        replace(target / 'transport/internet/tls/config.go',
            '\tfor _, opt := range opts {\n\t\topt(config)\n\t}',
            '\t// Top private Plug: preserve only explicitly opted-in legacy test TLS.\n\t// InsecureSkipVerify is already true for the sentinel; clear its name check.\n\tif len(c.VerifyPeerCertByName) == 1 && c.VerifyPeerCertByName[0] == "' + SENTINEL + '" {\n\t\trandCarrier.VerifyPeerCertByName = nil\n\t}\n\n\tfor _, opt := range opts {\n\t\topt(config)\n\t}')
        (target / 'TPP-COMPATIBILITY.txt').write_text('Base: github.com/xtls/xray-core ' + VERSION + '\nPatch: tools/prepare_xray_compat.py\nExplicit legacy allowInsecure testing only; certificate verification remains enabled otherwise.\n')
    subprocess.run(['go', 'mod', 'edit', '-replace=github.com/xtls/xray-core=./tpp-xray-core'], cwd=source, check=True)
    subprocess.run(['gofmt', '-w', str(target / 'infra/conf/transport_security.go'), str(target / 'transport/internet/tls/config.go')], check=True)
    print('Prepared pinned Xray compatibility source (explicit legacy test TLS only).')


if __name__ == '__main__':
    main()
