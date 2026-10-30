#!/usr/bin/env python3
"""Compile a test-only instrumentation APK, capture native screens, and verify logout."""
from pathlib import Path
import os,subprocess,time,zipfile,shutil
ROOT=Path(__file__).resolve().parents[1];sdk=Path(os.environ['ANDROID_HOME']);bt=sdk/'build-tools/35.0.0';android=sdk/'platforms/android-35/android.jar';work=ROOT/'android/ui-build';work.mkdir(exist_ok=True)
def run(*args,**kwargs):return subprocess.run(list(map(str,args)),check=True,**kwargs)
manifest=work/'AndroidManifest.xml';manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="za.co.topprivateplug.uitest"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/><application android:label="UI tests"/><instrumentation android:name="za.co.topprivateplug.UiSnapshots" android:targetPackage="za.co.topprivateplug"/></manifest>')
for directory in ['classes','dex']:(work/directory).mkdir(exist_ok=True)
run(bt/'aapt2','link','--manifest',manifest,'-I',android,'-o',work/'base.apk')
run('javac','--release','8','-cp',str(android)+os.pathsep+str(ROOT/'android/build/classes'),'-d',work/'classes',ROOT/'android/ui-tests/UiSnapshots.java')
run(bt/'d8','--min-api','26','--lib',android,'--classpath',ROOT/'android/build/classes','--output',work/'dex',*list((work/'classes').glob('**/*.class')))
shutil.copyfile(work/'base.apk',work/'test.apk')
with zipfile.ZipFile(work/'test.apk','a') as z:
 for file in (work/'dex').glob('*.dex'):z.write(file,file.name)
run(bt/'zipalign','-f','4',work/'test.apk',work/'aligned.apk')
run(bt/'apksigner','sign','--ks',ROOT/'.local-signing/debug.keystore','--ks-pass','pass:android','--out',work/'signed.apk',work/'aligned.apk')
adb=sdk/'platform-tools/adb';run(adb,'install','-r',ROOT/'Top-private-Plug-0.1.14-pilot.apk');run(adb,'install','-r',work/'signed.apk')
result=run(adb,'shell','am','instrument','-w','za.co.topprivateplug.uitest/za.co.topprivateplug.UiSnapshots',capture_output=True,text=True,timeout=180);print(result.stdout)
if 'UI snapshots and logout checks passed' not in result.stdout:raise SystemExit('Native UI check failed')
shots=ROOT/'ui-screenshots';shots.mkdir(exist_ok=True);run(adb,'pull','/sdcard/Android/data/za.co.topprivateplug/files/.',shots)
with zipfile.ZipFile(ROOT/'Top-private-Plug-0.1.14-ui-screenshots.zip','w',zipfile.ZIP_DEFLATED) as z:
 for image in sorted(shots.glob('*.png')):z.write(image,image.name)
