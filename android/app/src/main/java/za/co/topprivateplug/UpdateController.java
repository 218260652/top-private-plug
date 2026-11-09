package za.co.topprivateplug;

import android.app.*;
import android.content.*;
import android.content.pm.*;
import android.net.Uri;
import android.os.Build;
import java.net.*;
import javax.net.ssl.HttpsURLConnection;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import org.json.JSONObject;

final class UpdateController {
    final MainActivity a;final ExecutorService worker=Executors.newSingleThreadExecutor();
    volatile String status="Check for the latest app update.",versionName="";volatile boolean checking,downloading;
    private JSONObject release;private volatile boolean closed;
    UpdateController(MainActivity a){this.a=a;try{release=new JSONObject(a.prefs.getString("update_release","{}"));versionName=release.optString("version_name","");}catch(Exception ignored){} }
    boolean available(){return release!=null&&release.optInt("version_code")>UpdatePolicy.VERSION_CODE;}
    File apk(){return new File(a.getFilesDir(),"updates/pilot.apk");}
    boolean ready(){return available()&&apk().isFile()&&release.optString("sha256").equals(a.prefs.getString("downloaded_sha",""));}
    void paint(){a.handler.post(()->{if(!closed&&a.visible&&"Notifications".equals(a.tab))a.render();});}
    HttpsURLConnection open(String value)throws Exception{
        URL url=new URL(value);if(!"https".equals(url.getProtocol())||!UpdatePolicy.HOST.equals(url.getHost()))throw new Exception("Untrusted update source.");
        Proxy proxy="Connected".equals(TunnelService.state)?Api.updateProxy():null;
        if("Connected".equals(TunnelService.state)&&proxy==null)throw new Exception("The VPN is closing. Retry the update check.");
        HttpsURLConnection c=(HttpsURLConnection)(proxy==null?url.openConnection():url.openConnection(proxy));c.setConnectTimeout(12000);c.setReadTimeout(20000);c.setInstanceFollowRedirects(false);c.setRequestProperty("Accept","application/json, application/vnd.android.package-archive");return c;
    }
    void check(boolean manual){if(closed||checking||downloading)return;if(!"Connected".equals(TunnelService.state)&&!"Disconnected".equals(TunnelService.state))return;long now=System.currentTimeMillis();if(!manual&&now-a.prefs.getLong("update_checked",0)<6*3600000L)return;checking=true;status="Checking for updates…";paint();worker.execute(()->{HttpsURLConnection c=null;try{c=open(UpdatePolicy.MANIFEST);if(c.getResponseCode()!=200)throw new IOException("Update service returned "+c.getResponseCode());ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream in=c.getInputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){bytes.write(b,0,n);if(bytes.size()>65536)throw new IOException("Update response too large.");}}
        JSONObject next=new JSONObject(bytes.toString("UTF-8"));validate(next);release=next;versionName=next.getString("version_name");a.prefs.edit().putString("update_release",next.toString()).putLong("update_checked",now).apply();status=available()?"New update available · "+versionName:"You're up to date · 0.2.14";
        if(available()&&a.prefs.getBoolean("notify_updates",true))notifyUser("updates",41,"New update available",versionName+" · tap to download",true);
    }catch(Exception error){status="Update check unavailable. Try again when your connection is working.";}finally{if(c!=null)c.disconnect();checking=false;paint();}});}
    void validate(JSONObject r)throws Exception{UpdatePolicy.validate(r.getInt("version_code"),r.getString("version_name"),r.getString("apk_url"),r.getString("sha256"),r.getLong("size"));}
    void download(){if(!available()||downloading||closed)return;if(ready()){install();return;}final JSONObject selected=release;downloading=true;status="Downloading update…";paint();worker.execute(()->{File partial=new File(a.getFilesDir(),"updates/download.part");HttpsURLConnection c=null;try{
        validate(selected);partial.getParentFile().mkdirs();c=open(selected.getString("apk_url"));if(c.getResponseCode()!=200)throw new IOException("Download unavailable.");long size=selected.getLong("size"),total=0;MessageDigest digest=MessageDigest.getInstance("SHA-256");try(InputStream in=c.getInputStream();OutputStream out=new FileOutputStream(partial)){byte[] buf=new byte[32768];int n;int last=-1;while((n=in.read(buf))!=-1){if(closed||Thread.currentThread().isInterrupted())throw new InterruptedIOException();total+=n;if(total>size)throw new IOException("Incorrect update size.");digest.update(buf,0,n);out.write(buf,0,n);int percent=(int)(total*100/size);if(percent!=last){last=percent;status="Downloading update… "+percent+"%";paint();}}}
        if(total!=size||!hex(digest.digest()).equals(selected.getString("sha256")))throw new IOException("Update checksum mismatch.");verifyApk(partial,selected);if(apk().exists()&&!apk().delete())throw new IOException("Cannot replace staged update.");if(!partial.renameTo(apk()))throw new IOException("Cannot stage update.");release=selected;a.prefs.edit().putString("downloaded_sha",selected.getString("sha256")).apply();status="Update verified. Tap Install downloaded update.";a.handler.post(()->{if(!closed)install();});
    }catch(Exception error){partial.delete();status="The update could not be downloaded or verified. Please retry. Your installed app is unchanged.";}finally{if(c!=null)c.disconnect();downloading=false;paint();}});}
    void verifyApk(File file,JSONObject selected)throws Exception{
        PackageManager pm=a.getPackageManager();int flag=Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo archive=pm.getPackageArchiveInfo(file.getAbsolutePath(),flag),current=pm.getPackageInfo(a.getPackageName(),flag);
        if(archive==null||!a.getPackageName().equals(archive.packageName)||archive.versionCode!=selected.getInt("version_code")||archive.versionCode<=current.versionCode)throw new Exception("Wrong package/version.");
        Signature[] expected=Build.VERSION.SDK_INT>=28?current.signingInfo.getApkContentsSigners():current.signatures,actual=Build.VERSION.SDK_INT>=28?archive.signingInfo.getApkContentsSigners():archive.signatures;
        if(expected==null||actual==null||expected.length!=actual.length)throw new Exception("Wrong signing identity.");for(int i=0;i<expected.length;i++)if(!Arrays.equals(expected[i].toByteArray(),actual[i].toByteArray()))throw new Exception("Wrong signing identity.");
    }
    void install(){if(!ready()){a.message("Download and verify an available update first.");return;}try{
        verifyApk(apk(),release);
        if(Build.VERSION.SDK_INT>=26&&!a.getPackageManager().canRequestPackageInstalls()){a.message("Android needs your permission to install this update. Enable updates from Top private Plug, return here, then tap Install downloaded update.");a.startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+a.getPackageName())));return;}
        Uri uri=Uri.parse("content://"+a.getPackageName()+".updates/pilot.apk");Intent i=new Intent(Intent.ACTION_INSTALL_PACKAGE).setDataAndType(uri,"application/vnd.android.package-archive").setFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);i.setClipData(ClipData.newRawUri("Verified app update",uri));a.startActivity(i);
    }catch(Exception error){a.message("Android could not open the verified update. Contact WhatsApp support for help.");}}
    void notifyUser(String channel,int id,String title,String detail,boolean update){try{NotificationManager m=a.getSystemService(NotificationManager.class);m.createNotificationChannel(new NotificationChannel(channel,update?"App updates":"Account alerts",NotificationManager.IMPORTANCE_DEFAULT));Intent intent=new Intent(a,MainActivity.class).putExtra("show_updates",update);PendingIntent tap=PendingIntent.getActivity(a,id,intent,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);m.notify(id,new Notification.Builder(a,channel).setSmallIcon(R.drawable.ic_launcher).setContentTitle(title).setContentText(detail).setContentIntent(tap).setAutoCancel(true).build());}catch(SecurityException ignored){}}
    void accountAlerts(JSONObject account){if(!a.prefs.getBoolean("notify_account",true))return;long remaining=account.optLong("remaining_bytes"),quota=account.optLong("quota"),expiry=account.optLong("expires"),now=account.optLong("server_time",System.currentTimeMillis()/1000);String key=account.optString("id")+":"+expiry;boolean low=quota>0&&remaining<=quota/10,soon=expiry>now&&expiry-now<=86400;String event=low?"low":soon?"expiry":"";if(!event.isEmpty()&&!a.prefs.getString("account_alert","").equals(key+event)){notifyUser("account",42,low?"Your data is running low":"Your access expires soon",low?"Open Plans to request a top-up.":"Open your account to review the expiry.",false);a.prefs.edit().putString("account_alert",key+event).apply();}}
    static String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
    void close(){closed=true;worker.shutdownNow();}
}


