package za.co.topprivateplug;
import android.app.*;
import android.content.*;
import android.os.*;
import android.graphics.Bitmap;
import android.view.*;
import org.json.*;
import java.io.*;

/** Test-only account fixtures: never packaged in the shipping application. */
public class UiSnapshots extends Instrumentation {
 MainActivity a;
 @Override public void onCreate(Bundle args){super.onCreate(args);start();}
 void main(Runnable r){runOnMainSync(r);}
 void shot(String name)throws Exception {Bundle progress=new Bundle();progress.putString("stream","Capturing "+name+"\n");sendStatus(0,progress);Thread.sleep(700);Bitmap image=getUiAutomation().takeScreenshot();if(image==null)throw new Exception("Screenshot unavailable");try(OutputStream out=new FileOutputStream(new File(a.getExternalFilesDir(null),name+".png"))){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();}
 @Override public void onStart(){Bundle results=new Bundle();try{
  Bundle launch=new Bundle();launch.putString("stream","Launching native activity\n");sendStatus(0,launch);
  getTargetContext().getSharedPreferences("appearance",Context.MODE_PRIVATE).edit().putBoolean("reduce_motion",true).commit();
  a=(MainActivity)startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
  main(()->{a.handler.removeCallbacks(a.poll);a.updates.close();a.nextAccountRefresh=Long.MAX_VALUE;});shot("01-activation");
  main(()->{try{a.vault.token("ui-fixture-not-a-real-account");long now=System.currentTimeMillis()/1000;a.account=new JSONObject().put("id","00000000-0000-4000-8000-000000000000").put("status","active").put("quota",10000000000L).put("used",1200000000L).put("remaining_bytes",8800000000L).put("expires",now+14*86400).put("server_time",now);for(int i=0;i<24;i++)a.points.put(new JSONObject().put("at",now-3600+i*150).put("up",(long)(i%5+1)*12000000).put("down",(long)(i%7+1)*20000000));}catch(Exception e){throw new RuntimeException(e);}a.render();});shot("02-disconnected");
  main(()->{TunnelService.state="Connecting";TunnelService.detail="Authorizing account through saved profile";a.render();});shot("03-connecting");
  main(()->{TunnelService.state="Connected";TunnelService.detail="Test profile: server certificate verification is disabled.";TunnelService.connectedAt=SystemClock.elapsedRealtime()-924000;TunnelService.uploaded=12400000;TunnelService.downloaded=28700000;a.uploadRate=3.6;a.downloadRate=12.4;a.render();});shot("04-connected");
  main(()->{a.tab="Usage";a.render();});shot("05-usage");main(()->{try{a.account.put("quota",10000000000000L).put("remaining_bytes",10000000000000L);a.render();}catch(Exception e){throw new RuntimeException(e);}});shot("05b-large-quota");main(()->a.scroll.fullScroll(View.FOCUS_DOWN));shot("06-usage-history");
  main(()->{a.tab="Plans";a.render();});shot("07-plans");main(()->a.scroll.fullScroll(View.FOCUS_DOWN));shot("08-plans-telkom");
  main(()->{a.tab="Settings";a.render();});shot("09-settings");main(()->a.scroll.fullScroll(View.FOCUS_DOWN));shot("10-settings-bottom");
  for(String page:new String[]{"Account","Notifications","Service settings","Privacy & security","Support & help","About"}){main(()->{a.tab=page;a.render();});shot("11-"+page.replaceAll("[^a-zA-Z]","-"));}
  main(()->{a.prefs.edit().putString("theme","Light").apply();a.tab="Settings";a.render();});shot("12-light-theme");
  main(()->{a.prefs.edit().putString("theme","Dark").apply();a.tab="Home";TunnelService.state="Disconnected";TunnelService.detail="";a.logout();if(!a.vault.token().isEmpty()||a.account!=null)throw new AssertionError("Logout did not clear account");});shot("13-logged-out");
  results.putString("stream","UI snapshots and logout checks passed\n");finish(Activity.RESULT_OK,results);
 }catch(Throwable e){results.putString("stream",android.util.Log.getStackTraceString(e));finish(Activity.RESULT_CANCELED,results);}}
}
