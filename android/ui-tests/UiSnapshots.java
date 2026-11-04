package za.co.topprivateplug;
import android.app.*;
import android.content.*;
import android.os.*;
import android.graphics.Bitmap;
import android.view.*;
import org.json.*;
import java.io.*;

/** Isolated emulator fixtures; never packaged in the shipping application. */
public class UiSnapshots extends Instrumentation {
 MainActivity a;
 @Override public void onCreate(Bundle args){super.onCreate(args);start();}
 void main(Runnable r){runOnMainSync(r);}
 void require(boolean pass,String message){if(!pass)throw new AssertionError(message);}
 boolean has(View v,String s){if(v instanceof android.widget.TextView&&s.contentEquals(((android.widget.TextView)v).getText()))return true;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)if(has(((ViewGroup)v).getChildAt(i),s))return true;return false;}
 void shot(String name)throws Exception {
  Bundle progress=new Bundle();progress.putString("stream","Capturing "+name+"\n");sendStatus(0,progress);
  Thread.sleep(700);waitForIdleSync();boolean ready=false;String activePackage="unknown";
  for(int i=0;i<60;i++){
   android.view.accessibility.AccessibilityNodeInfo active=getUiAutomation().getRootInActiveWindow();
   if(active!=null){activePackage=String.valueOf(active.getPackageName());ready="za.co.topprivateplug".equals(activePackage);active.recycle();}
   if(ready)break;
   if(i==15 && "android".equals(activePackage)){
    // A transient system dialog can cover a freshly upgraded app on the emulator.
    getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
   }
   if(i==30){
    Intent reopen=new Intent(getTargetContext(),MainActivity.class)
      .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP);
    getTargetContext().startActivity(reopen);
   }
   Thread.sleep(250);
  }
  require(ready,"App window unavailable for screenshot: "+activePackage);
  Bitmap b=getUiAutomation().takeScreenshot();require(b!=null,"Screenshot unavailable");
  try(OutputStream out=new FileOutputStream(new File(a.getExternalFilesDir(null),name+".png"))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();
 }
 JSONObject fixture(String id,long quota)throws Exception{return new JSONObject().put("id",id).put("status","active").put("quota",quota).put("used",1200000000L).put("remaining_bytes",quota-1200000000L).put("expires",System.currentTimeMillis()/1000+14*86400);}
 @Override public void onStart(){Bundle result=new Bundle();try{
  require("keep-existing-data".equals(getTargetContext().getSharedPreferences("update_probe",Context.MODE_PRIVATE).getString("sentinel","")),"Upgrade lost preferences");
  a=(MainActivity)startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
  main(()->{a.handler.removeCallbacks(a.poll);a.updates.close();a.nextAccountRefresh=Long.MAX_VALUE;require(!has(a.root,"Home")&&!has(a.root,"Usage")&&!has(a.root,"Plans")&&!has(a.root,"Settings")&&!has(a.root,"Buy access via WhatsApp"),"Circled options remain on activation screen");});shot("01-first-activation");
  main(()->{try{
   Vault v=a.vault;
   // Exercise migration of the original encrypted token and cache, not plain fixtures.
   v.token("legacy-fixture");v.catalog(new JSONArray().put(new JSONObject().put("id","p").put("engine","xray").put("carrier","Any")));
   android.content.SharedPreferences prefs=getTargetContext().getSharedPreferences("tpp",Context.MODE_PRIVATE);
   prefs.edit().putString("token",prefs.getString("access.MTN.token","")).putString("catalog",prefs.getString("access.MTN.catalog","")).remove("access.MTN.token").remove("access.MTN.catalog").remove("access_migrated").commit();
   v=new Vault(getTargetContext());require("legacy-fixture".equals(v.token())&&v.catalog().length()==1,"Legacy access migration failed");
   String[] nets={"MTN","Cell C","Telkom"};
   for(int i=0;i<3;i++){v.selectNetwork(nets[i]);v.activateToken("fixture-"+i,fixture("account-"+i,(i+2)*10000000000L).put("carrier",nets[i]));v.catalog(new JSONArray().put(new JSONObject().put("id","p"+i).put("engine","xray").put("carrier",nets[i])));v.bootstrap("p"+i,new JSONObject().put("config",new JSONObject()).put("profile",new JSONObject()),v.token(),v.endpoint());}
   for(int i=0;i<3;i++){v.selectNetwork(nets[i]);require(v.token().equals("fixture-"+i),"Network token overwritten");require(v.savedAccount().getString("id").equals("account-"+i),"Account crossed network slots");require(v.bootstrap("p"+i)!=null&&v.bootstrap("p"+((i+1)%3))==null,"Profile crossed network slots");}
   // Same account in a second slot rotates its token without invalidating its old cache.
   v.selectNetwork("MTN");v.activateToken("rotated-fixture",fixture("account-0",20000000000L).put("carrier","MTN"));
   v.selectNetwork("Telkom");try{v.activateToken("wrong-network",fixture("account-0",20000000000L).put("carrier","MTN"));throw new AssertionError("Wrong-network slot accepted");}catch(Exception expected){}require(v.token().equals("fixture-2"),"Rejected activation replaced Telkom token");
   v.selectNetwork("MTN");require(v.token().equals("rotated-fixture")&&v.bootstrap("p0")!=null,"Repeated account lost original saved connection");
   v.selectNetwork("Cell C");require(v.token().equals("fixture-1"),"Unrelated account token changed");v.token("");
   v.selectNetwork("MTN");require(!v.token().isEmpty(),"Logout removed another activation");
   a.carrier="MTN";a.account=v.savedAccount();a.profiles=v.catalog();a.accountSyncedAt=SystemClock.elapsedRealtime();a.render();
   require(has(a.root,"MTN")&&has(a.root,"Cell C")&&has(a.root,"Telkom"),"Missing network");
   require(!has(a.root,"Plans")&&!has(a.root,"Buy access via WhatsApp")&&!has(a.root,"Top up via WhatsApp"),"Activated screen contains payment navigation");
   require(has(a.root,"CONNECT"),"Missing connection button");
  }catch(Exception e){throw new RuntimeException(e);}});shot("02-simple-disconnected");
  main(()->{TunnelService.state="Connecting";TunnelService.detail="Establishing your connection";a.render();require(has(a.root,"CANCEL"),"Cannot cancel connecting");});shot("03-simple-connecting");
  main(()->{TunnelService.state="Connected";TunnelService.detail="";TunnelService.uploaded=7300000;TunnelService.downloaded=95100000;TunnelService.latency=308;a.render();require(has(a.root,"DISCONNECT"),"Missing disconnect");String before=a.vault.network();a.selectNetwork("Telkom");require(before.equals(a.vault.network()),"Changed account under active tunnel");});
  main(()->{
   android.widget.TextView latency=a.liveLabels.stream().filter(v->"LATENCY".equals(v.getTag())).findFirst().orElseThrow(AssertionError::new);
   require("308 ms".contentEquals(latency.getText()),"Missing first latency reading");
   TunnelService.latency=162;TunnelService.uploaded+=1000000;TunnelService.downloaded+=2000000;
   a.updateLiveLabels();require("162 ms".contentEquals(latency.getText()),"Latency did not refresh");
   require(has(a.root,a.bytes(8300000))&&has(a.root,a.bytes(97100000)),"Traffic readings did not refresh");
   TunnelService.latency=-1;a.updateLiveLabels();require("—".contentEquals(latency.getText()),"Failed check left stale latency");
   TunnelService.latency=162;a.updateLiveLabels();
  });
  // Dismiss the expected network-switch explanation before capturing app content.
  main(()->{if(a.noticeDialog!=null)a.noticeDialog.dismiss();});shot("04-simple-connected");
  main(()->{TunnelService.state="Disconnected";TunnelService.detail="";a.selectNetwork("Telkom");a.nextAccountRefresh=Long.MAX_VALUE;a.render();require(a.account!=null&&a.accountSyncedAt==0,"Cached overview marked fresh");require(has(a.root,"Saved overview · refresh to confirm current balance"),"Missing stale balance label");});shot("05-saved-telkom");
  main(()->{a.selectNetwork("Cell C");a.nextAccountRefresh=Long.MAX_VALUE;require(a.vault.token().isEmpty(),"Empty slot has foreign activation");require(!has(a.root,"Buy access via WhatsApp"),"Payment exposed while other activation saved");});shot("06-add-cell-c");
  main(()->{a.selectNetwork("MTN");a.nextAccountRefresh=Long.MAX_VALUE;a.accountSyncedAt=SystemClock.elapsedRealtime();a.render();});waitForIdleSync();
  final java.util.concurrent.CountDownLatch release=new java.util.concurrent.CountDownLatch(1);final java.util.concurrent.atomic.AtomicInteger calls=new java.util.concurrent.atomic.AtomicInteger();final android.widget.ScrollView[] retained={null};
  main(()->{retained[0]=a.scroll;for(int i=0;i<50;i++)a.runNetwork(()->{calls.incrementAndGet();release.await(5,java.util.concurrent.TimeUnit.SECONDS);},true);require(a.scroll==retained[0],"Refresh replaced screen at start");});
  release.countDown();long deadline=SystemClock.elapsedRealtime()+6000;while(a.refreshing&&SystemClock.elapsedRealtime()<deadline)Thread.sleep(20);waitForIdleSync();
  main(()->{require(calls.get()==1&&!a.refreshing,"Refresh requests overlap");require(a.scroll==retained[0],"Unchanged refresh redraws screen");});
  main(()->{a.logout();require(a.vault.token().isEmpty(),"Logout failed");a.vault.selectNetwork("Telkom");require(!a.vault.token().isEmpty(),"Logout erased other activation");});
  result.putString("stream","UI snapshots and logout checks passed\n");finish(Activity.RESULT_OK,result);
 }catch(Throwable e){result.putString("stream",android.util.Log.getStackTraceString(e));finish(Activity.RESULT_CANCELED,result);}}
}
