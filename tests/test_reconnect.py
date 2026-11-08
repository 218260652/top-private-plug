"""Execute retry classification, bounded recovery and cancellation against production Java."""
from pathlib import Path
import shutil, subprocess, tempfile, unittest
from tests.test_android_lifecycle import method
ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/'android/app/src/main/java/za/co/topprivateplug'
@unittest.skipUnless(shutil.which('javac'),'JDK required')
class RecoveryTests(unittest.TestCase):
 def test_recovery_limit_terminal_errors_and_cancel(self):
  source=(JAVA/'TunnelService.java').read_text()
  harness=r'''package za.co.topprivateplug;
import java.util.*;
import java.util.concurrent.atomic.*;
class Api { static class HttpError extends Exception { final int status; HttpError(int s){status=s;} } }
public class RecoveryHarness {
 static final int STOP_FOREGROUND_REMOVE=1;
 final AtomicBoolean stopping=new AtomicBoolean(true);
 boolean reconnectAllowed=true,retryFailure=true,proxyFailure=true,retryPending,hadLease,foreground=true;
 int retryAttempt,starts,stops; String accessToken="access",accountOrigin="https://admin.example";
 String token="access",endpoint=accountOrigin; static String state="Connected",detail="";
 Runnable retryTask; final Main main=new Main();
 static class Main { Runnable delayed;long delay;void postDelayed(Runnable r,long ms){delayed=r;delay=ms;}void removeCallbacks(Runnable r){if(delayed==r)delayed=null;} }
 static class Vault { RecoveryHarness s;Vault(RecoveryHarness s){this.s=s;}String token(){return s.token;}String endpoint(){return s.endpoint;} }
 String sessionMarker(Vault vault){return vault.token();}
 void stopForeground(int flags){foreground=false;}void stopSelf(){stops++;}void showNotification(String s){}
 void stopTunnel(){stops++;}void beginAttempt(){starts++;}
 static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
 public static void main(String[] args)throws Exception {
  for(int status:new int[]{401,403,404,409,422})check(!RetryPolicy.transientFailure(new Api.HttpError(status)),"Retry terminal HTTP "+status);
  for(int status:new int[]{408,429,500,502,503,504})check(RetryPolicy.transientFailure(new Api.HttpError(status)),"No retry transient HTTP "+status);
  check(!RetryPolicy.transientFailure(new javax.net.ssl.SSLHandshakeException("untrusted")),"Retry certificate failure");
  check(!RetryPolicy.transientFailure(new Exception("expired")),"Retry unknown account failure");
  check(!RetryPolicy.transientFailure(new InterruptedException()),"Retry cancellation");
  check(RetryPolicy.transientFailure(new Exception("wrapped",new java.net.ConnectException())),"No retry wrapped socket failure");
  check(RetryPolicy.transientFailure(new ProxyFailure(429)),"No retry proxy limit");
  long prev=0;for(int i=1;i<=5;i++){long d=RetryPolicy.delayMillis(i,false,false);check(d>=prev&&d<=60000,"Unbounded delay");prev=d;}
  check(RetryPolicy.delayMillis(1,true,false)>=30000,"Proxy hammered");
  check(RetryPolicy.delayMillis(1,false,true)>=35000,"Lease overlap");
  RecoveryHarness s=new RecoveryHarness();
  for(int i=1;i<=5;i++){s.onCleanupComplete();check(s.retryAttempt==i&&s.retryPending&&state.equals("Reconnecting"),"Missing retry "+i);Runnable next=s.main.delayed;s.main.delayed=null;next.run();check(s.starts==i,"Attempt did not start");}
  s.onCleanupComplete();check(s.starts==5&&s.stops==1&&state.equals("Disconnected")&&!s.foreground,"Exceeded five retries");
  s=new RecoveryHarness();s.onCleanupComplete();s.requestStop();check(s.main.delayed==null&&!s.reconnectAllowed&&!s.retryPending,"Stop did not cancel scheduled reconnect");
  s=new RecoveryHarness();s.onCleanupComplete();s.token="changed";s.main.delayed.run();check(s.starts==0&&!s.reconnectAllowed,"Restarted after logout/account change");
  s=new RecoveryHarness();s.retryFailure=false;s.onCleanupComplete();check(s.main.delayed==null&&s.stops==1,"Retried terminal authorization failure");
  System.out.println("PASS");
 }
'''+method(source,'onCleanupComplete')+'\n'+method(source,'requestStop')+'\n}\n'
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'RecoveryHarness.java';f.write_text(harness)
   result=subprocess.run(['javac','-d',tmp,str(f),str(JAVA/'RetryPolicy.java'),str(JAVA/'ProxyFailure.java'),str(JAVA/'ConnectionReport.java')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   result=subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.RecoveryHarness'],capture_output=True,text=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr)

