#!/usr/bin/env python3
"""Dependency-free Android build with the official SDK and JDK 17.

Produces a DEBUG-SIGNED pilot, not a store release. Requires the pinned native Xray AAR.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', default=os.environ.get('ANDROID_HOME', ''))
    parser.add_argument('--ecj', default=os.environ.get('ECJ_JAR', ''))
    args = parser.parse_args()
    if not args.sdk:
        parser.error('Set ANDROID_HOME or pass --sdk')
    sdk = Path(args.sdk)
    tools = sdk / 'build-tools' / '35.0.0'
    for executable in ['aapt2', 'd8', 'zipalign', 'apksigner']:
        path = tools / executable
        if not os.access(path, os.X_OK):
            path.chmod(0o755)
    android = sdk / 'platforms' / 'android-35' / 'android.jar'
    source = ROOT / 'android' / 'app' / 'src' / 'main'
    build = ROOT / 'android' / 'build'
    if build.exists():
        shutil.rmtree(build)
    for directory in ['gen', 'classes', 'dex']:
        (build / directory).mkdir(parents=True, exist_ok=True)
    run(tools / 'aapt2', 'compile', '--dir', source / 'res', '-o', build / 'res.zip')
    ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
    manifest = ET.parse(source / 'AndroidManifest.xml')
    manifest.getroot().set('package', 'za.co.topprivateplug.test')
    manifest.write(build / 'AndroidManifest.xml', encoding='utf-8', xml_declaration=True)
    run(tools / 'aapt2', 'link', '-o', build / 'base.apk', '--manifest', build / 'AndroidManifest.xml',
        '-I', android, '--java', build / 'gen', '--min-sdk-version', '26', '--target-sdk-version', '35',
        '-A', source / 'assets', '--version-code', '24', '--version-name', '0.1.23-test', '--debug-mode', build / 'res.zip')
    aar = ROOT / 'android' / 'app' / 'libs' / 'libv2ray.aar'
    if not aar.exists():
        raise SystemExit('Build the pinned libv2ray.aar first; see tools/build_xray.sh')
    with zipfile.ZipFile(aar) as archive:
        (build / 'libv2ray.jar').write_bytes(archive.read('classes.jar'))
    classpath = str(android) + os.pathsep + str(build / 'libv2ray.jar')
    java = sorted(source.glob('java/**/*.java')) + sorted((build / 'gen').glob('**/*.java'))
    if args.ecj:
        run('java', '-jar', args.ecj, '-encoding', 'UTF-8', '-source', '1.8', '-target', '1.8', '-bootclasspath', str(android) + os.pathsep + str(tools / 'core-lambda-stubs.jar'), '-classpath', classpath, '-d', build / 'classes', *java)
    else:
        run('javac', '-encoding', 'UTF-8', '--release', '8', '-classpath', classpath, '-d', build / 'classes', *java)
    classes = sorted((build / 'classes').glob('**/*.class'))
    run(tools / 'd8', '--min-api', '26', '--lib', android, '--output', build / 'dex', build / 'libv2ray.jar', *classes)
    shutil.copy2(build / 'base.apk', build / 'unsigned.apk')
    with zipfile.ZipFile(build / 'unsigned.apk', 'a', zipfile.ZIP_DEFLATED) as apk:
        for dex in (build / 'dex').glob('*.dex'):
            apk.write(dex, dex.name)
        with zipfile.ZipFile(aar) as archive:
            for entry in archive.infolist():
                if entry.filename.startswith('jni/') and entry.filename.endswith('.so'):
                    apk.writestr('lib/' + entry.filename[4:], archive.read(entry))
                elif entry.filename.startswith('assets/') and not entry.is_dir():
                    apk.writestr(entry.filename, archive.read(entry))
    run(tools / 'zipalign', '-p', '-f', '4', build / 'unsigned.apk', build / 'aligned.apk')
    signing = ROOT / '.local-signing'
    signing.mkdir(exist_ok=True)
    keystore = signing / 'debug.keystore'
    if not keystore.exists():
        run('keytool', '-genkeypair', '-keystore', keystore, '-storepass', 'android', '-keypass', 'android', '-alias',
            'androiddebugkey', '-dname', 'CN=Android Debug,O=Android,C=ZA', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000')
    output = ROOT / 'Top-private-Plug-Test-0.1.23-pilot.apk'
    run(tools / 'apksigner', 'sign', '--ks', keystore, '--ks-key-alias', 'androiddebugkey', '--ks-pass', 'pass:android',
        '--key-pass', 'pass:android', '--out', output, build / 'aligned.apk')
    run(tools / 'apksigner', 'verify', '--verbose', output)
    print('Built DEBUG-SIGNED PILOT:', output)


if __name__ == '__main__':
    main()








