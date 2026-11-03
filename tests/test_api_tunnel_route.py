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
 static int replyStatus=200;static boolean failRead;static Proxy last;static int calls;static FakeConnection connection;static java.util.List<String> paths=new java.util.ArrayList<>();
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] a)throws Exception {
  URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler(){
   protected URLConnection openConnection(URL u){last=null;calls++;return connection=new FakeConnection(u);}
   protected URLConnection openConnection(URL u,Proxy p){last=p;calls++;return connection=new FakeConnection(u);}
  }:null);
  Vault vault=new Vault();Api api=new Api(vault);
  api.request("/v1/status",null,true);check(last==null);check(connection.getRequestProperty("Connection")==null&&!connection.disconnected);
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
  org.json.JSONArray profiles=new org.json.JSONArray(new org.json.JSONObject().put("id","profile-A").put("engine","xray"));
  paths.clear();api.prepareProfiles(profiles);
  check(vault.saved&&vault.writes==1);
  check(paths.equals(java.util.Arrays.asList("/v1/challenge","/v1/connect","/v1/xray/disconnect")));
  paths.clear();api.prepareProfiles(profiles);check(paths.isEmpty());
  api.prepareProfiles(profiles,true);check(vault.writes==2);
  for(int status:new int[]{401,403,429,503}) {
   replyStatus=status;
   try {api.request("/v1/xray/heartbeat",null,true);throw new AssertionError();}
   catch(Api.HttpError expected){check(expected.status==status);}
   check(connection.disconnected);
  }
  replyStatus=200;
  failRead=true;
  try{api.request("/v1/status",null,true);throw new AssertionError();}catch(Exception expected){check(connection.disconnected);}
  failRead=false;
  check(ProxyFailure.status("proxy/http: Proxy responded with non 200 code: 429 Too Many Requests")==429);
  check(ProxyFailure.status("proxy/http: Proxy responded with non 200 code: 503 Service Unavailable")==503);
  check(ProxyFailure.status("certificate failure") == 0);
  check(ProxyFailure.status("HTTP_429 from account service") == 0);
  ConnectionReport.failure(null,new ProxyFailure(429));
  check(ConnectionReport.snapshot().contains("UPSTREAM_PROXY_429"));
  vault.saved=false;vault.failSave=true;paths.clear();
  try {api.prepareProfiles(profiles);throw new AssertionError();}catch(java.io.IOException expected){}
  check(paths.get(paths.size()-1).equals("/v1/xray/disconnect"));
  check(!vault.saved); // a failed save cannot report readiness
  vault.failSave=false;paths.clear();
  api.prepareProfiles(new org.json.JSONArray(new org.json.JSONObject().put("id","legacy").put("engine","other")));
  check(paths.isEmpty());
 }
 static class FakeConnection extends HttpsURLConnection {
  boolean disconnected;FakeConnection(URL u){super(u);paths.add(u.getPath());}public void connect(){}public void disconnect(){disconnected=true;}public boolean usingProxy(){return true;}
  public String getCipherSuite(){return "TLS-fixture";}public Certificate[] getLocalCertificates(){return null;}
  public Certificate[] getServerCertificates(){return null;}
  public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
  public int getResponseCode(){return replyStatus;}public InputStream getErrorStream(){return new ByteArrayInputStream("<html>Unavailable</html>".getBytes());}public InputStream getInputStream()throws IOException{if(failRead)throw new SSLException("fixture tunnel interrupted");return new ByteArrayInputStream("{}".getBytes());}
 }
}
class Vault {
 boolean saved,failSave;int writes;String origin="https://account.example";
 String endpoint(){return origin;}String token(){return "secret-token";}void token(String s){}void activateToken(String s,org.json.JSONObject a){}
 org.json.JSONObject bootstrap(String id){return saved?new org.json.JSONObject():null;}
 void bootstrap(String id,org.json.JSONObject result,String token,String origin)throws Exception{
  if(failSave)throw new java.io.IOException("fixture write failed");
  if(!"profile-A".equals(id)||!token.equals(token())||!origin.equals(endpoint()))throw new AssertionError();
  saved=true;writes++;
 }
}
class DeviceKey {static String publicKey(){return "public";}static String sign(String s){return "signed";}}
'''
        json_stub='''package org.json;public class JSONObject {
 private java.util.Map<String,Object> values=new java.util.HashMap<>();
 public JSONObject(){}public JSONObject(String value){if(value.startsWith("<"))throw new IllegalArgumentException("invalid JSON");values.put("engine","xray");}public JSONObject put(String k,Object v){values.put(k,v);return this;}
 public String optString(String k){return optString(k,"");}public String optString(String k,String d){return values.containsKey(k)?values.get(k).toString():d;}
 public String getString(String k){return optString(k,"value");}public JSONObject getJSONObject(String k){return this;}
 public String toString(){return "{}";}
}'''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'ApiHarness.java';source.write_text(harness)
            stub=root/'JSONObject.java';stub.write_text(json_stub)
            array=root/'JSONArray.java';array.write_text('package org.json;public class JSONArray {private JSONObject[] values;public JSONArray(JSONObject... v){values=v;}public int length(){return values.length;}public JSONObject getJSONObject(int i){return values[i];}}')
            subprocess.run(['javac','-d',tmp,str(source),str(stub),str(array),str(JAVA/'Api.java'),str(JAVA/'ConnectionReport.java'),str(JAVA/'ProxyFailure.java'),str(JAVA/'CustomerMessage.java')],check=True,capture_output=True,text=True,timeout=30)
            subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.ApiHarness'],check=True,capture_output=True,text=True,timeout=10)


