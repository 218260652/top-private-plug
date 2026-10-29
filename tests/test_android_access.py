"""Exercise the account gate used by the real Activity after a cold restart."""
from pathlib import Path
import shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('javac'), 'JDK required')
class AndroidAccessTests(unittest.TestCase):
    def test_saved_activation_is_not_rejected_when_account_refresh_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            shutil.copy(ROOT/'android/app/src/main/java/za/co/topprivateplug/AccessState.java',root/'AccessState.java')
            (root/'AccessHarness.java').write_text('''package za.co.topprivateplug;
public class AccessHarness {
    static void check(boolean b){if(!b)throw new AssertionError();}
    public static void main(String[] args){
        check(AccessState.resolve(true,false,"")==AccessState.State.CHECK_REQUIRED);
        check(AccessState.resolve(true,true,"active")==AccessState.State.ACTIVE);
        check(AccessState.resolve(false,false,"")==AccessState.State.ACTIVATION_REQUIRED);
        check(AccessState.resolve(false,true,"active")==AccessState.State.ACTIVATION_REQUIRED);
        for(String status:new String[]{"expired","suspended","deleted","exhausted","unknown"})
            check(AccessState.resolve(true,true,status)==AccessState.State.INACTIVE);
        check(AccessState.resolve(true,false,"active")!=AccessState.State.ACTIVE);
        System.out.println("PASS: restart/network failure requires a check, never false activation or offline authorization");
    }
}''')
            subprocess.run(['javac','-d',temp,str(root/'AccessState.java'),str(root/'AccessHarness.java')],check=True,capture_output=True,text=True,timeout=30)
            result=subprocess.run(['java','-cp',temp,'za.co.topprivateplug.AccessHarness'],check=True,capture_output=True,text=True,timeout=10)
            self.assertIn('PASS:',result.stdout)
