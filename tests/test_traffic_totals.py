import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

JAVA = Path(__file__).resolve().parents[1] / 'android/app/src/main/java/za/co/topprivateplug'

@unittest.skipUnless(shutil.which('javac'), 'JDK required; CI runs after Java setup')
class TrafficTotalsTests(unittest.TestCase):
    def test_real_wrapper_format_deltas_large_values_and_safe_messages(self):
        harness = '''package za.co.topprivateplug;
public class TrafficHarness {
 public static void main(String[] args) {
  TrafficTotals t=new TrafficTotals();
  t.add("trojan,uplink,1000000000;trojan,downlink,9000000000;http-upstream,downlink,123;", "trojan");
  if(t.up!=1000000000L||t.down!=9000000000L)throw new AssertionError("10GB counters");
  t.add("", "trojan");t.add("trojan,downlink,7;", "trojan");
  if(t.down!=9000000007L)throw new AssertionError("Delta reset handling");
  boolean rejected=false;try{t.add("trojan,downlink,-1;","trojan");}catch(Exception e){rejected=true;}
  if(!rejected||t.down!=9000000007L)throw new AssertionError("Invalid stats");
  for(int status:new int[]{400,401,403,409,426,429,500}) {
   String message=CustomerMessage.forStatus(status);
   if(message.isEmpty()||message.contains("http")||message.contains("UUID"))throw new AssertionError("Unsafe message");
  }
 }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'TrafficHarness.java'; file.write_text(harness)
            subprocess.run(['javac','-d',tmp,str(JAVA/'TrafficTotals.java'),str(JAVA/'CustomerMessage.java'),str(file)],check=True,capture_output=True)
            subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.TrafficHarness'],check=True,capture_output=True)
