"""Execute the production shutdown methods against deliberately blocked native I/O.

Android adapters are stubbed; this verifies Java lifecycle responsiveness, not
phone TUN routing. The unchanged 0.1.7 stop method fails by blocking the caller.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, name):
    # Locate by signature so visibility/synchronization remain production code.
    import re
    start = re.search(r'    private (?:synchronized )?void ' + name + r'\(\)', source).start()
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


@unittest.skipUnless(shutil.which('javac'), 'JDK required; CI runs this after Java setup')
class AndroidShutdownTests(unittest.TestCase):
    def test_cancel_is_nonblocking_during_native_start_and_stop(self):
        source = (ROOT / 'android/app/src/main/java/za/co/topprivateplug/TunnelService.java').read_text()
        harness = r'''package za.co.topprivateplug;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public class ShutdownHarness {
    static final int STOP_FOREGROUND_REMOVE=1;
    final AtomicBoolean running=new AtomicBoolean(true), stopping=new AtomicBoolean(false);
    final Object xrayLock=new Object();
    final FakeMain main=new FakeMain();
    volatile String state="Connecting";
    volatile FakeTun tun=new FakeTun();
    volatile FakeEngine xray=new FakeEngine();
    boolean foreground=true;
    Thread worker,pinger;
    int stopCalls;
    void stopSelf(){stopCalls++;}
    void stopForeground(int flags){}
    static class FakeMain {
        final BlockingQueue<Runnable> queue=new LinkedBlockingQueue<>();
        void post(Runnable r){queue.add(r);}
    }
    static class FakeTun {volatile boolean closed;void close(){closed=true;}}
    static class FakeEngine {
        final CountDownLatch entered=new CountDownLatch(1), release=new CountDownLatch(1);
        final AtomicInteger calls=new AtomicInteger();
        void stop(){calls.incrementAndGet();entered.countDown();try{release.await();}catch(InterruptedException e){throw new RuntimeException(e);}}
    }
    static void check(boolean b,String message){if(!b)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception{
        ShutdownHarness s=new ShutdownHarness();FakeEngine engine=s.xray;FakeTun tun=s.tun;
        CountDownLatch locked=new CountDownLatch(1), unlock=new CountDownLatch(1);
        Thread nativeStart=new Thread(()->{synchronized(s.xrayLock){locked.countDown();try{unlock.await();}catch(Exception e){throw new RuntimeException(e);}}});
        nativeStart.setDaemon(true);nativeStart.start();locked.await();
        long start=System.nanoTime();s.stopTunnel();
        check(TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start)<250,"Cancel blocked on startup lock");
        check(!s.running.get(),"Cancel did not stop work");
        check(s.state.equals("Disconnecting"),"Reconnect allowed before native cleanup");
        s.stopTunnel(); // Android onDestroy/onRevoke may repeat cancellation.
        unlock.countDown();check(engine.entered.await(2,TimeUnit.SECONDS),"Native shutdown not scheduled");
        check(tun.closed,"Android descriptor was not released before native shutdown");
        start=System.nanoTime();s.stopTunnel();
        check(TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start)<250,"Cancel blocked on native I/O");
        check(s.main.queue.isEmpty(),"Reported disconnected before native cleanup completed");
        engine.release.countDown();
        Runnable completion=s.main.queue.poll(2,TimeUnit.SECONDS);check(completion!=null,"No lifecycle completion");completion.run();
        check(engine.calls.get()==1,"Native stop ran more than once");
        check(s.state.equals("Disconnected")&&s.stopCalls==1&&!s.foreground,"Cleanup did not finish");
        check(s.xray==null&&s.tun==null,"Leaked transport resources");
        System.out.println("PASS: cancellation remains responsive with blocked native startup and shutdown; cleanup runs once");
    }
'''
        harness += method(source, 'closeTransport') + '\n' + method(source, 'stopTunnel') + '\n}\n'
        with tempfile.TemporaryDirectory() as tmp:
            java = Path(tmp) / 'ShutdownHarness.java'
            java.write_text(harness)
            report = ROOT / 'android/app/src/main/java/za/co/topprivateplug/ConnectionReport.java'
            subprocess.run(['javac', '-d', tmp, str(java), str(report)], check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run(['java', '-cp', tmp, 'za.co.topprivateplug.ShutdownHarness'], check=True, capture_output=True, text=True, timeout=8)
            self.assertIn('PASS:', result.stdout)
