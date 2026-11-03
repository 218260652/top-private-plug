"""Fail closed on pilot signing, package, or version incompatibility."""
import json, os, re, subprocess, sys
from pathlib import Path
bt=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0'
def inspect(path):
 cert=subprocess.check_output([str(bt/'apksigner'),'verify','--print-certs',path],text=True)
 digest=re.findall(r'Signer #\d+ certificate SHA-256 digest: (\w+)',cert)
 if not digest: raise SystemExit('Missing verified signing certificate')
 badging=subprocess.check_output([str(bt/'aapt2'),'dump','badging',path],text=True)
 package=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
 if not package: raise SystemExit('Missing package metadata')
 return dict(package=package[1],version_code=int(package[2]),version_name=package[3],certificate_sha256=sorted(digest))
old,new=map(inspect,sys.argv[1:3])
assert old['package']==new['package']=='za.co.topprivateplug', 'Package changed'
assert old['certificate_sha256']==new['certificate_sha256'], 'Signing identity changed: do not install'
assert new['version_code']>old['version_code'], 'Version code did not increase'
assert old['version_name']=='0.1.17-pilot', 'Unexpected baseline'
report=dict(baseline=old,candidate=new,compatible=True,physical_device_upgrade_tested=False)
Path('update-compatibility.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
