"""Run production account-only routing policy generation without Android."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/'android/app/src/main/java/za/co/topprivateplug'

@unittest.skipUnless(shutil.which('javac'),'JDK required; CI runs after Java setup')
class ControlPolicyTests(unittest.TestCase):
    def test_bootstrap_is_account_only_and_invalid_origins_are_rejected(self):
        source='''package za.co.topprivateplug;
public class PolicyHarness {
 public static void main(String[] args)throws Exception {
  System.out.println(ControlPolicy.inbound(12345));
  System.out.println(ControlPolicy.rules("https://account.example",true));
  System.out.println(ControlPolicy.rules("https://account.example:8443",false));
  System.out.println(ControlPolicy.rules("https://127.0.0.1:443",true));
  for(String origin:new String[]{"http://account.example","https://evil@account.example","https://account.example/path","https://account.example?x=y","https://account.example#x","https://account.example:99999"}) {
   boolean rejected=false;try{ControlPolicy.rules(origin,true);}catch(Exception e){rejected=true;}
   if(!rejected)throw new AssertionError(origin);
  }
 }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            harness=Path(tmp)/'PolicyHarness.java';harness.write_text(source)
            subprocess.run(['javac','-d',tmp,str(JAVA/'ControlPolicy.java'),str(harness)],check=True,capture_output=True,text=True,timeout=30)
            result=subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.PolicyHarness'],check=True,capture_output=True,text=True,timeout=10)
        inbound,boot,full,ip=map(json.loads,result.stdout.splitlines())
        self.assertEqual(inbound['listen'],'127.0.0.1');self.assertEqual(inbound['protocol'],'http')
        self.assertEqual(boot[0]['domain'],['full:account.example']);self.assertEqual(boot[0]['port'],'443')
        self.assertEqual(boot[0]['inboundTag'],['admin-control']);self.assertEqual(boot[0]['outboundTag'],'trojan')
        self.assertEqual(boot[1]['outboundTag'],'block');self.assertEqual(boot[2],{'type':'field','network':'tcp,udp','outboundTag':'block'})
        self.assertEqual(len(full),2);self.assertEqual(full[0]['port'],'8443')
        self.assertEqual(ip[0]['ip'],['127.0.0.1'])
