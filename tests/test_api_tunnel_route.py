"""Execute production Api transport selection with recording HTTPS adapters."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/'android/app/src/main/java/za/co/topprivateplug'
@unittest.skipUnless(shutil.which('javac'),'JDK required; CI runs after Java setup')
class ApiTunnelRouteTests(unittest.TestCase):
    def test_account_https_uses_proxy_without_direct_fallback(self):
        harness=r'''package za.co.topprivateplug;
import java.net.*;import java.io.*;import javax.net.ssl.*;import java.security.cert.Certificate;
public class ApiHarness {
 static Proxy last;static int calls;static FakeConnection connection;
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] a)throws Exception {
  URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
   protected URLConnection openConnection(URL u){last=null;calls++;return connection=new FakeConnection(u);}
   protected URLConnection openConnection(URL u,Proxy p){last=p;calls++;return connection=new FakeConnection(u);}
  }:null);
  Vault vault=new Vault();Api api=new Api(vault);
  api.request("/v1/status",null,true);check(last==null);
  Api.throughTunnel(vault.endpoint(),12345);
  api.request("/v1/challenge",null,false);
  check(last!=null&&last.type()==Proxy.Type.HTTP&&last.address().equals(new InetSocketAddress("127.0.0.1",12345)));
  check(connection.getInstanceFollowRedirects()==false);
  api.request("/v1/xray/heartbeat",null,true);
  check(last!=null&&connection.getConnectTimeout()==5000&&connection.getReadTimeout()==10000);
  int before=calls;vault.origin="https://different.example";
  try {api.request("/v1/status",null,true);throw new AssertionError();}catch(Exception expected){}
  check(calls==before); // no direct fallback across an account-origin change
  Api.clearTunnel();api.request("/v1/status",null,true);check(last==null);
  check(ConnectionReport.snapshot().contains("TUNNEL_ACCOUNT /v1/challenge"));
  check(!ConnectionReport.snapshot().contains("secret-token"));
 }
 static class FakeConnection extends HttpsURLConnection {
  FakeConnection(URL u){super(u);}public void connect(){}public void disconnect(){}public boolean usingProxy(){return true;}
  public String getCipherSuite(){return "TLS-fixture";}public Certificate[] getLocalCertificates(){return null;}
  public Certificate[] getServerCertificates(){return null;}
  public int getResponseCode(){return 200;}public InputStream getInputStream(){return new ByteArrayInputStream("{}".getBytes());}
 }
}
class Vault {
 String origin="https://account.example";
 String endpoint(){return origin;}String token(){return "secret-token";}void token(String s){}
 void bootstrap(String id,org.json.JSONObject result,String token,String origin){}
}
class DeviceKey {static String publicKey(){return "public";}static String sign(String s){return "signed";}}
'''
        json_stub='''package org.json;public class JSONObject {
 public JSONObject(){}public JSONObject(String value){}public JSONObject put(String k,Object v){return this;}
 public String optString(String k){return "";}public String optString(String k,String d){return d;}
 public String getString(String k){return "value";}public JSONObject getJSONObject(String k){return this;}
 public String toString(){return "{}";}
}'''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'ApiHarness.java';source.write_text(harness)
            stub=root/'JSONObject.java';stub.write_text(json_stub)
            subprocess.run(['javac','-d',tmp,str(source),str(stub),str(JAVA/'Api.java'),str(JAVA/'ConnectionReport.java')],check=True,capture_output=True,text=True,timeout=30)
            subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.ApiHarness'],check=True,capture_output=True,text=True,timeout=10)
