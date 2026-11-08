"""Run the production report collector; no Android or network required."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('javac'), 'JDK required; CI runs after Java setup')
class ConnectionReportTests(unittest.TestCase):
    def test_report_is_bounded_concurrent_and_excludes_input_secrets(self):
        harness = r'''package za.co.topprivateplug;
import java.util.concurrent.*;
public class ReportHarness {
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        check(ConnectionReport.snapshot().contains("No connection events yet"));
        String secret="password-token-UUID-private-host";
        ConnectionReport.request("/v1/status?token="+secret, 403);
        ConnectionReport.failure(secret, new Exception(secret, new java.net.UnknownHostException(secret)));
        ConnectionReport.failure("/v1/connect", new java.net.SocketTimeoutException(secret));
        ConnectionReport.failure("/v1/connect", new javax.net.ssl.SSLHandshakeException(secret));
        ConnectionReport.failure("/v1/connect", new java.net.ConnectException(secret));
        ConnectionReport.stage(ConnectionReport.Stage.ACCOUNT_CHALLENGE);
        String report=ConnectionReport.snapshot();
        check(!report.contains(secret));
        for(String value:new String[]{"HTTP_403","DNS_LOOKUP","NETWORK_TIMEOUT","TLS_HANDSHAKE","TCP_CONNECT","ACCOUNT_CHALLENGE"})
            check(report.contains(value));
        ExecutorService pool=Executors.newFixedThreadPool(8);
        for(int i=0;i<200;i++)pool.submit(()->{
            ConnectionReport.stage(ConnectionReport.Stage.NATIVE_START);
            check(!ConnectionReport.snapshot().contains(secret));
        });
        pool.shutdown();check(pool.awaitTermination(5,TimeUnit.SECONDS));
        report=ConnectionReport.snapshot();
        check(report.split("\\n").length==51);
        check(!report.contains("DNS_LOOKUP")); // oldest entries evicted
        System.out.println("PASS: bounded, concurrent, credential-free diagnostics");
    }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'ReportHarness.java'
            source.write_text(harness)
            report = ROOT / 'android/app/src/main/java/za/co/topprivateplug/ConnectionReport.java'
            subprocess.run(['javac', '-d', tmp, str(report), str(report.with_name('ProxyFailure.java')), str(source)], check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run(['java', '-cp', tmp, 'za.co.topprivateplug.ReportHarness'], check=True, capture_output=True, text=True, timeout=10)
            self.assertIn('PASS:', result.stdout)


