"""Exercise executable update trust boundaries and all advertised purchase variants."""
from pathlib import Path
import shutil, subprocess, tempfile, unittest
JAVA=Path(__file__).resolve().parents[1]/'android/app/src/main/java/za/co/topprivateplug'
@unittest.skipUnless(shutil.which('javac'),'JDK required; explicitly run in CI')
class PremiumPolicyTests(unittest.TestCase):
 def test_update_sources_and_purchase_variants(self):
  source='''package za.co.topprivateplug;
import java.net.URLDecoder;
public class PremiumHarness {
 public static void main(String[] args)throws Exception {
  int[][] wanted={{50,30,7},{100,50,30},{135,80,30},{200,120,30}};
  for(String network:new String[]{"MTN","Telkom","Cell C"})for(int i=0;i<4;i++){
   PlanCatalog.Plan p=PlanCatalog.PLANS[i];if(p.gigabytes!=wanted[i][0]||p.rand!=wanted[i][1]||p.days!=wanted[i][2])throw new AssertionError("Plan mismatch");
   String selection=p.gigabytes+" GB • R"+p.rand+" • "+p.days+" days",url=PurchaseRequest.url(false,selection,network,null),decoded=URLDecoder.decode(url,"UTF-8");
   if(!url.startsWith("https://wa.me/27703841868?text=")||!decoded.contains(selection)||!decoded.contains("Network: "+network))throw new AssertionError(url);
  }
  for(String network:new String[]{"MTN","Telkom","Cell C"})if(!URLDecoder.decode(PurchaseRequest.supportUrl(network,null),"UTF-8").contains("Network: "+network))throw new AssertionError("Support network");
  TrafficMeter meter=new TrafficMeter();meter.sample(true,0,0,0);for(int t=1000;t<6000;t+=1000)meter.sample(true,0,0,t);meter.sample(true,6000000,12000000,6000);
  if(Math.abs(meter.uploadMbps-8)>0.0001||Math.abs(meter.downloadMbps-16)>0.0001)throw new AssertionError("Batched counter rate");
  meter.sample(true,6000000,12000000,7000);if(meter.downloadMbps!=16)throw new AssertionError("Hold latest measurement");
  meter.sample(true,6000000,12000000,19000);if(meter.downloadMbps!=0)throw new AssertionError("Stale rate");meter.sample(false,0,0,20000);if(meter.uploadMbps!=0)throw new AssertionError("Disconnected rate");
  if(!URLDecoder.decode(PurchaseRequest.supportUrl("Telkom",null),"UTF-8").contains("I need help"))throw new AssertionError("Support request");
  String good="https://"+UpdatePolicy.HOST+"/downloads/Top-private-Plug-0.1.15-pilot.apk",hash=new String(new char[64]).replace('\\0','a');
  UpdatePolicy.validate(16,"0.1.15-pilot",good,hash,43000000);
  for(String bad:new String[]{good.replace("https:","http:"),good.replace(UpdatePolicy.HOST,"evil.example"),good+"?redirect=evil",good+"#fragment",good.replace("/downloads/","/../downloads/"),good.replace("https://","https://user@"),good.replace(UpdatePolicy.HOST,UpdatePolicy.HOST+":8443")}){
   boolean reject=false;try{UpdatePolicy.validate(16,"next",bad,hash,43000000);}catch(Exception e){reject=true;}if(!reject)throw new AssertionError(bad);
  }
  for(long size:new long[]{0,9999,104857601}){boolean reject=false;try{UpdatePolicy.validate(16,"next",good,hash,size);}catch(Exception e){reject=true;}if(!reject)throw new AssertionError("Size");}
  boolean reject=false;try{UpdatePolicy.validate(16,"next",good,"bad",43000000);}catch(Exception e){reject=true;}if(!reject)throw new AssertionError("Hash");
 }
}'''
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'PremiumHarness.java';f.write_text(source)
   subprocess.run(['javac','-d',tmp,*map(str,[JAVA/'UpdatePolicy.java',JAVA/'PlanCatalog.java',JAVA/'PurchaseRequest.java',JAVA/'TrafficMeter.java',f])],check=True,capture_output=True,text=True)
   subprocess.run(['java','-cp',tmp,'za.co.topprivateplug.PremiumHarness'],check=True,capture_output=True,text=True)

