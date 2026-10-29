package za.co.topprivateplug;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.ActivityNotFoundException;
import android.net.Uri;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.VpnService;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URI;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int BG=0xff050d1b, PANEL=0xff0d1e33, LINE=0xff28435e, TEXT=0xffeef5ff, MUTED=0xffa6b9cf, CYAN=0xff13cff0, MINT=0xff2ce3b6;
    private LinearLayout root, content, navigation;
    private Vault vault;
    private Api api;
    private JSONObject account;
    private JSONArray profiles = new JSONArray(), points = new JSONArray();
    private String tab = "Home", carrier = "MTN", selectedProfile = "";
    private String lastError = "";
    private boolean busy, refreshing, visible;
    private int graphHours = 1;
    private long nextAccountRefresh;
    private String renderedTunnelState = "", renderedTunnelDetail = "";
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final ExecutorService backgroundNetwork = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!visible) return;
            long now = android.os.SystemClock.elapsedRealtime();
            if (!busy && !refreshing && !vault.token().isEmpty() && now >= nextAccountRefresh) {
                nextAccountRefresh = now + ("Connected".equals(TunnelService.state) ? 10000 : 20000);
                refresh();
            }
            if (!renderedTunnelState.equals(TunnelService.state) || !renderedTunnelDetail.equals(TunnelService.detail)) render();
            handler.postDelayed(this, 1000);
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); vault = new Vault(this); api = new Api(vault); profiles=vault.catalog(); chooseCarrier();
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackground(new Backdrop());
        root.setPadding(dp(22),dp(20),dp(22),dp(12));
        root.setOnApplyWindowInsetsListener((view,insets)->{
            android.graphics.Insets bars = Build.VERSION.SDK_INT>=30 ? insets.getInsets(WindowInsets.Type.systemBars()) : null;
            int top=bars==null?insets.getSystemWindowInsetTop():bars.top, bottom=bars==null?insets.getSystemWindowInsetBottom():bars.bottom;
            root.setPadding(dp(22),top+dp(12),dp(22),bottom+dp(8)); return insets;
        });
        setContentView(root); root.requestApplyInsets(); render();
    }
    @Override protected void onResume() { super.onResume(); visible=true; handler.removeCallbacks(poll); handler.post(poll); render(); }
    @Override protected void onPause() { visible=false; handler.removeCallbacks(poll); super.onPause(); }
    @Override protected void onDestroy() { network.shutdownNow(); backgroundNetwork.shutdownNow(); super.onDestroy(); }
    int dp(float n) { return (int)(n*getResources().getDisplayMetrics().density+.5f); }
    GradientDrawable shape(int color, int border, int radius) { GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));if(border!=0)d.setStroke(dp(1),border);return d; }
    TextView text(String value, int size, int color, boolean bold) { TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(3),1);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t; }
    void add(LinearLayout parent, View child, int margin) { LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(margin);parent.addView(child,p); }
    LinearLayout column() { LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.VERTICAL);return v; }
    LinearLayout card() { LinearLayout c=column();c.setPadding(dp(20),dp(21),dp(20),dp(21));c.setBackground(shape(PANEL,LINE,24));add(content,c,18);return c; }
    Button button(String label, boolean primary, View.OnClickListener click) { Button b=new Button(this);b.setText(label);b.setTextSize(14);b.setTextColor(primary?BG:TEXT);b.setAllCaps(false);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setMinHeight(dp(53));b.setPadding(dp(14),dp(8),dp(14),dp(8));b.setBackground(shape(primary?CYAN:0xff102b43,primary?0:LINE,16));b.setOnClickListener(click);b.setEnabled(!busy);return b; }
    void render() {
        if (isFinishing()) return;
        renderedTunnelState = TunnelService.state; renderedTunnelDetail = TunnelService.detail;
        root.removeAllViews();
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        ImageView icon=new ImageView(this);icon.setImageResource(R.drawable.ic_launcher);icon.setContentDescription("Top private Plug shield");header.addView(icon,new LinearLayout.LayoutParams(dp(40),dp(40)));
        TextView name=text("Top private Plug",21,TEXT,true);LinearLayout.LayoutParams nameP=new LinearLayout.LayoutParams(0,-2,1);nameP.leftMargin=dp(10);header.addView(name,nameP);
        TextView menu=text("⚙",26,CYAN,false);menu.setGravity(Gravity.CENTER);menu.setContentDescription("Service settings");menu.setOnClickListener(v->{tab="Settings";render();});header.addView(menu,new LinearLayout.LayoutParams(dp(48),dp(48)));add(root,header,18);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);scroll.setVerticalScrollBarEnabled(false);
        content=column();scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if (!lastError.isEmpty()) add(content,text(lastError,12,0xffffcc88,false),14);
        switch(tab){case "Usage":usage();break;case "Plans":plans();break;case "Settings":settings();break;default:home();}
        navigation=new LinearLayout(this);navigation.setPadding(dp(4),dp(9),dp(4),dp(9));navigation.setBackground(shape(0xff091b2f,LINE,22));
        String[] tabs={"Home","Usage","Plans","Settings"};String[] symbols={"⌂","▥","▣","⚙"};
        for(int i=0;i<tabs.length;i++){final String chosen=tabs[i];TextView item=text(symbols[i]+"\n"+chosen,13,tab.equals(chosen)?CYAN:MUTED,false);item.setGravity(Gravity.CENTER);item.setMinHeight(dp(48));item.setContentDescription(chosen);item.setOnClickListener(v->{tab=chosen;render();if(chosen.equals("Usage"))loadGraph();});navigation.addView(item,new LinearLayout.LayoutParams(0,-2,1));}
        root.addView(navigation,new LinearLayout.LayoutParams(-1,-2));
    }
    void home() {
        TextView country=text("●  South Africa",13,MINT,false);country.setGravity(Gravity.CENTER);add(content,country,24);
        if(vault.token().isEmpty()) { activation();return; }
        if(account==null) { accountRecovery();return; }
        LinearLayout networks=new LinearLayout(this);
        for(String item:new String[]{"MTN","Telkom","Cell C"}){Button b=button(item,false,v->{if(!TunnelService.state.equals("Disconnected")){message("Disconnect before changing the network.");return;}carrier=item;selectedProfile="";render();});b.setTextColor(item.equals(carrier)?CYAN:MUTED);if(item.equals(carrier))b.setBackground(shape(0xff0c3546,CYAN,16));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(49),1);p.setMargins(dp(3),0,dp(3),0);networks.addView(b,p);}add(content,networks,20);
        LinearLayout connection=card();TextView state=text(TunnelService.state,21,TEXT,true);state.setGravity(Gravity.CENTER);add(connection,state,8);
        TextView hint=text(TunnelService.detail.isEmpty()?"Your private connection, one tap away.":TunnelService.detail,12,MUTED,false);hint.setGravity(Gravity.CENTER);add(connection,hint,22);
        TextView power=text("Connected".equals(TunnelService.state)?"STOP":"Connecting".equals(TunnelService.state)?"CANCEL":"CONNECT",18,"Connected".equals(TunnelService.state)?MINT:CYAN,false);power.setGravity(Gravity.CENTER);power.setContentDescription("Connected".equals(TunnelService.state)?"Disconnect VPN":"Connect VPN");power.setBackground(shape(0xff0d414c,"Connected".equals(TunnelService.state)?MINT:CYAN,100));LinearLayout.LayoutParams pp=new LinearLayout.LayoutParams(dp(150),dp(150));pp.gravity=Gravity.CENTER;pp.bottomMargin=dp(14);connection.addView(power,pp);power.setOnClickListener(v->toggle());
        TextView action=text("Connected".equals(TunnelService.state)?"Tap to disconnect":"Connecting".equals(TunnelService.state)?"Tap to cancel":"Tap to connect",15,TEXT,true);action.setGravity(Gravity.CENTER);add(connection,action,8);
        JSONArray available=carrierProfiles();
        if(available.length()==0)add(connection,text("No enabled "+carrier+" profile is assigned. Ask your service admin.",12,MUTED,false),0);
        else if(available.length()>1){String[] names=new String[available.length()];for(int i=0;i<names.length;i++)names[i]=available.optJSONObject(i).optString("name");add(connection,button("Choose connection profile",false,v->new AlertDialog.Builder(this).setTitle("Connection profile").setItems(names,(d,n)->{selectedProfile=available.optJSONObject(n).optString("id");message(names[n]+" selected.");}).show()),0);}
        addReportButton(connection);
        planCard();
        LinearLayout live=card();add(live,text("Live session",16,TEXT,true),14);add(live,text("↑ "+bytes(TunnelService.uploaded)+"     ↓ "+bytes(TunnelService.downloaded),17,CYAN,true),8);add(live,text(TunnelService.latency<0?"Latency —":("Gateway latency "+TunnelService.latency+" ms"),12,MUTED,false),0);
    }
    void accountRecovery() {
        LinearLayout c=card();
        add(c,text("Access saved",25,TEXT,true),12);
        add(c,text(refreshing?"Checking your account…":"Account check needed",16,CYAN,true),12);
        add(c,text("Your activation is saved. A saved connection profile can start VLESS first and verify your account through it. Connect once on Wi-Fi after updating to save the profile. A failed network request does not mean your access has expired.",14,MUTED,false),18);
        Button retry=button(refreshing?"Checking…":"Retry account check",true,v->refresh());
        retry.setEnabled(!refreshing&&!busy);add(c,retry,12);
        if(hasSavedProfile()) add(c,button("Connect using saved profile",true,v->toggle()),12);
        addReportButton(c);
        add(c,button("Open service status",false,v->{
            try { startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(vault.endpoint()+"/health"))); }
            catch(ActivityNotFoundException error) { message("Open "+vault.endpoint()+"/health in your browser."); }
        }),12);
        add(c,text("Check that normal websites open with other VPN apps turned off. If mobile data cannot reach the service, try Wi-Fi. Keep this app installed and do not clear its data.",12,MUTED,false),0);
        if(!"Disconnected".equals(TunnelService.state))add(content,button("Disconnect VPN",false,v->toggle()),12);
    }
    AccessState.State accessState() {
        return AccessState.resolve(!vault.token().isEmpty(),account!=null,account==null?"":account.optString("status"));
    }
    void activation() {
        TextView globe=text("◉",105,0xff167d9e,false);globe.setGravity(Gravity.CENTER);add(content,globe,20);
        LinearLayout c=card();add(c,text("Activate your access",27,TEXT,true),10);add(c,text("Enter the access code supplied by your service admin. Your time starts on first activation.",14,MUTED,false),25);
        add(c,button("Enter activation code",true,v->codeDialog(false)),12);add(c,button("Use a trial code",false,v->codeDialog(true)),12);
        add(c,button("Buy access via WhatsApp",false,v->purchaseDialog(false)),12);
        add(c,text("Opens WhatsApp with your plan request and network. You review and send the message to arrange payment.",12,MUTED,false),12);
        add(c,text("Trial hours and data allowances are set by the admin. No automatic payment or renewal.",12,MUTED,false),0);
        add(content,button(vault.endpoint().isEmpty()?"Set service address":"Service settings",false,v->endpointDialog()),20);
    }
    void planCard() {
        if(account==null&&!vault.token().isEmpty()){accountRecovery();return;}
        LinearLayout c=card();add(c,text("Your access",13,MUTED,false),8);
        if(account==null){add(c,text("Activate your access to see its limits.",15,TEXT,false),0);return;}
        add(c,text(account.optString("kind").equals("trial")?"FREE TRIAL":"PRIVATE ACCESS",22,TEXT,true),8);
        String status=account.optString("status","unknown");add(c,text(status.toUpperCase(Locale.ROOT),12,status.equals("active")?MINT:CYAN,true),15);
        long used=account.optLong("used"),quota=account.optLong("quota");
        add(c,text(bytes(account.optLong("remaining_bytes"))+" remaining",22,TEXT,true),10);
        ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);progress.setProgress((int)Math.min(1000,used*1000.0/Math.max(1,quota)));add(c,progress,10);
        add(c,text(bytes(used)+" used of "+bytes(quota)+" · upload + download",12,MUTED,false),15);
        add(c,text("Expires: "+expiry(account),12,MUTED,false),5);
        long left=account.optLong("expires",0)-account.optLong("server_time",0);if(left>0)add(c,text((left/86400>0?left/86400+" days ":"")+(left%86400/3600)+" hours remaining at last refresh",12,CYAN,false),0);
        add(c,button("Top up via WhatsApp",true,v->purchaseDialog(true)),10);
        add(c,text("Includes your plan request, network and account reference. Access changes after the admin confirms payment.",12,MUTED,false),0);
    }
    void usage() {
        add(content,text("Usage",28,TEXT,true),20);planCard();
        LinearLayout c=card();add(c,text("This connection",18,TEXT,true),15);add(c,text("↑ Upload    "+bytes(TunnelService.uploaded)+"\n↓ Download    "+bytes(TunnelService.downloaded),18,CYAN,true),12);add(c,text("Live counters reset on reconnect. Usage is reported by this app to your account service.",12,MUTED,false),0);
        add(content,text("Server data history",19,TEXT,true),12);LinearLayout controls=new LinearLayout(this);
        for(int hours:new int[]{1,6,24}){Button b=button(hours+"H",hours==graphHours,v->{graphHours=hours;loadGraph();});LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(48),1);p.setMargins(dp(4),0,dp(4),0);controls.addView(b,p);}add(content,controls,15);add(content,new UsageGraph(),20);
    }
    void plans() {
        add(content,text("Your plan",28,TEXT,true),20);if(vault.token().isEmpty()){activation();return;}planCard();
        LinearLayout c=card();add(c,text("Access that fits your needs",20,TEXT,true),12);add(c,text("Your admin can issue 7, 15 or 30-day plans, custom durations, and trials measured in hours. Each code has its own data allowance.",14,MUTED,false),20);add(c,button("Buy / top up via WhatsApp",true,v->purchaseDialog(true)),12);add(c,button("Activate another code",false,v->codeDialog(false)),12);add(c,button("Use a trial code",false,v->codeDialog(true)),10);add(c,text("A new code is a separate plan. It does not automatically add data or time to an existing account. Ask your admin to renew an existing plan.",12,MUTED,false),0);
    }
    void settings() {
        add(content,text("Settings",28,TEXT,true),20);LinearLayout c=card();add(c,text("Service address",16,TEXT,true),6);add(c,text(vault.endpoint().isEmpty()?"Not configured":vault.endpoint(),13,MUTED,false),14);add(c,button("Change service address",false,v->endpointDialog()),0);
        addReportButton(c);
        c=card();add(c,text("Connection security",18,TEXT,true),12);add(c,text("TLS 1.2 / 1.3 encryption\nCertificate checks depend on the selected profile\nDevice keys kept in Android Keystore\nAccount limits checked with the service",14,MUTED,false),10);add(c,text("Connection settings come only from your admin’s imported profile. Profile updates require reconnecting.",12,MUTED,false),0);
        c=card();add(c,text("Open-source engine",18,TEXT,true),12);add(c,text("AndroidLibXrayLite · LGPL-3.0\nXray-core · MPL-2.0",14,MUTED,false),10);
        add(c,button("Engine notices and licenses",false,v->showLicenses()),0);
        c=card();add(c,text("Privacy & service",18,TEXT,true),12);add(c,text("Your service stores your activation time, device public key, access status and upload/download byte totals. This app does not request contacts, location or media access.\n\nImported profiles route IPv4 and IPv6 through the tunnel after account approval. First activation and saving a profile require internet access. Saved profiles start VLESS or Trojan first, then verify your account through that connection. MTN, Telkom and Cell C labels do not guarantee network compatibility or provide mobile data.\n\nDisconnecting or a failed connection restores your normal network. Always-on VPN and a kill switch are not included in this pilot.",13,MUTED,false),0);
        add(content,button("Activate / recover access",false,v->codeDialog(false)),15);
        add(content,button("WhatsApp: "+PurchaseRequest.DISPLAY_PHONE,false,v->purchaseDialog(account!=null)),15);
        add(content,button("Forget access on this phone",false,v->new AlertDialog.Builder(this).setTitle("Forget access?").setMessage("This removes the local login. Your subscription keeps its original expiry. You can recover it with the same code on this installation.").setPositiveButton("Forget",(d,n)->{stopService(new Intent(this,TunnelService.class));try{vault.token("");}catch(Exception ignored){}account=null;profiles=new JSONArray();tab="Home";render();}).setNegativeButton("Cancel",null).show()),20);
        add(content,text("Top private Plug · 0.1.11 pilot\nImported VLESS / Trojan / Xray profiles",11,MUTED,false),20);
    }
    void addReportButton(LinearLayout parent) {
        Button report=button("Connection report",false,v->showConnectionReport());
        report.setEnabled(true);add(parent,report,12);
    }
    String networkSummary() {
        try {
            android.net.ConnectivityManager manager=getSystemService(android.net.ConnectivityManager.class);
            android.net.NetworkCapabilities caps=manager.getNetworkCapabilities(manager.getActiveNetwork());
            if(caps==null)return "Current network: unavailable\n";
            String transport=caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN)?"VPN":
                caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI)?"Wi-Fi":
                caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_CELLULAR)?"Mobile":"Other";
            return "Current network: "+transport+"; Android validated internet: "+
                caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED)+"\n";
        } catch(Exception ignored) { return "Current network: unknown\n"; }
    }
    void showConnectionReport() {
        final String report="Android API "+Build.VERSION.SDK_INT+"\n"+networkSummary()+ConnectionReport.snapshot();
        TextView body=text(report,12,TEXT,false);body.setTextIsSelectable(true);body.setPadding(dp(16),dp(16),dp(16),dp(16));
        ScrollView scroll=new ScrollView(this);scroll.addView(body);
        new AlertDialog.Builder(this).setTitle("Connection report").setView(scroll)
            .setPositiveButton("Close",null).setNeutralButton("Share",(d,n)->{
                Intent send=new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,report);
                try { startActivity(Intent.createChooser(send,"Share connection report")); }
                catch(ActivityNotFoundException error) { message("Select and copy the report text instead."); }
            }).show();
    }
    void purchaseDialog(boolean topUp) {
        String[] options={"7 days", "15 days", "30 days", "Custom duration or data top-up"};
        new AlertDialog.Builder(this).setTitle(topUp?"Request a top-up / renewal":"Request access")
            .setItems(options,(dialog,index)->{
                String id=account==null?null:account.optString("id",null);
                String link=PurchaseRequest.url(topUp,options[index],carrier,id);
                try { startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(link)).addCategory(Intent.CATEGORY_BROWSABLE)); }
                catch (ActivityNotFoundException error) { message("Install WhatsApp or a browser, or contact "+PurchaseRequest.DISPLAY_PHONE+" to arrange payment."); }
            }).setNegativeButton("Cancel",null).show();
    }
    void showLicenses() {
        try {
            StringBuilder text = new StringBuilder();
            for(String path : new String[]{"licenses/NOTICE.txt","licenses/LGPL-3.0.txt","licenses/GPL-3.0.txt","licenses/MPL-2.0.txt"}) {
                try(java.io.InputStream input=getAssets().open(path)) {
                    java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();byte[] buf=new byte[4096];int n;
                    while((n=input.read(buf))!=-1)bytes.write(buf,0,n);
                    text.append(bytes.toString("UTF-8")).append("\n\n");
                }
            }
            TextView body=text(text.toString(),12,TEXT,false);body.setPadding(dp(16),dp(16),dp(16),dp(16));
            ScrollView scroll=new ScrollView(this);scroll.addView(body);
            new AlertDialog.Builder(this).setTitle("Engine licenses").setView(scroll).setPositiveButton("Close",null).show();
        } catch(Exception error) { message("License texts are included in the APK assets."); }
    }
    JSONArray carrierProfiles() { JSONArray list=new JSONArray();for(int i=0;i<profiles.length();i++){JSONObject p=profiles.optJSONObject(i);if(p!=null&&"xray".equals(p.optString("engine"))&&(carrier.equals(p.optString("carrier"))||"Any".equals(p.optString("carrier"))))list.put(p);}return list; }
    boolean hasSavedProfile() {
        JSONArray available=carrierProfiles();
        for(int i=0;i<available.length();i++) if(vault.bootstrap(available.optJSONObject(i).optString("id"))!=null) return true;
        return false;
    }
    void toggle() {
        if("Disconnecting".equals(TunnelService.state)){message("The tunnel is closing. Please wait before reconnecting.");return;}
        if(!"Disconnected".equals(TunnelService.state)){startService(new Intent(this,TunnelService.class).setAction("STOP"));handler.postDelayed(this::render,300);return;}
        if(busy)return;
        AccessState.State access=accessState();
        if(access==AccessState.State.ACTIVATION_REQUIRED){codeDialog(false);return;}
        if(access==AccessState.State.CHECK_REQUIRED && !hasSavedProfile()){
            if(!refreshing)refresh();
            message("Your activation is saved. We need to reach the account service before connecting. Check your internet or try Wi-Fi, then retry the account check.");return;
        }
        if(access==AccessState.State.INACTIVE && !hasSavedProfile()){message("The service last reported your account as "+account.optString("status","unavailable")+". Retry the account check or contact your admin.");return;}
        JSONArray available=carrierProfiles();if(available.length()==0){message("No assigned profile for "+carrier+".");return;}
        boolean found=false;for(int i=0;i<available.length();i++)if(available.optJSONObject(i).optString("id").equals(selectedProfile))found=true;
        if(!found) {
            selectedProfile=available.optJSONObject(0).optString("id");
            for(int i=0;i<available.length();i++) if(vault.bootstrap(available.optJSONObject(i).optString("id"))!=null) {selectedProfile=available.optJSONObject(i).optString("id");break;}
        }
        new AlertDialog.Builder(this).setTitle("Connect to Top private Plug?").setMessage("Your internet traffic will pass through your service's VPN server. Upload and download both count toward your allowance.")
            .setPositiveButton("Continue",(d,n)->{Intent permission=VpnService.prepare(this);if(permission==null)startTunnel();else startActivityForResult(permission,77);}).setNegativeButton("Cancel",null).show();
    }
    @Override protected void onActivityResult(int request,int result,Intent data) { super.onActivityResult(request,result,data);if(request==77&&result==RESULT_OK)startTunnel(); }
    void startTunnel() {
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},78);
        startForegroundService(new Intent(this,TunnelService.class).putExtra("profile_id",selectedProfile));handler.postDelayed(this::render,400);
    }
    void codeDialog(boolean trial) {
        if(!"Disconnected".equals(TunnelService.state)){message("Disconnect before activating another code.");return;}
        if(vault.endpoint().isEmpty()){endpointDialog();return;}
        EditText input=new EditText(this);input.setSingleLine(true);input.setHint("TPP-…");input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);input.setPadding(dp(24),dp(16),dp(24),dp(16));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(trial?"Enter trial code":"Enter activation code").setView(input).setPositiveButton("Activate",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String code=input.getText().toString().trim();if(code.isEmpty()){input.setError("Enter your code");return;}dialog.dismiss();runNetwork(()->{JSONObject a=api.activate(code);JSONObject p=api.request("/v1/profiles",null,true);vault.catalog(p.getJSONArray("profiles"));handler.post(()->{lastError="";account=a;profiles=p.optJSONArray("profiles");chooseCarrier();tab="Home";render();message("Access activated. The server has recorded your start time.");});});}));dialog.show();
    }
    void endpointDialog() {
        EditText input=new EditText(this);input.setSingleLine(true);input.setText(vault.endpoint());input.setHint("https://admin.your-domain.co.za");input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);input.setPadding(dp(24),dp(16),dp(24),dp(16));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Service address").setMessage("Use the HTTPS address supplied by your VPN admin. Changing it clears your local access login.").setView(input).setPositiveButton("Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try{String value=input.getText().toString().trim().replaceAll("/+$","");URI uri=new URI(value);if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||(!uri.getPath().isEmpty()&&!uri.getPath().equals("/")))throw new Exception();stopService(new Intent(this,TunnelService.class));vault.endpoint(value);account=null;profiles=new JSONArray();dialog.dismiss();render();}catch(Exception error){input.setError("Enter an HTTPS origin without a path, username or query.");}}));dialog.show();
    }
    interface Work { void run() throws Exception; }
    void runNetwork(Work work) { runNetwork(work,false); }
    void runNetwork(Work work,boolean quiet) {
        if (quiet ? refreshing : busy) return;
        if (quiet) refreshing=true; else busy=true;
        render();
        final String requestToken=vault.token(), requestEndpoint=vault.endpoint();
        (quiet ? backgroundNetwork : network).execute(()->{
            try { work.run(); handler.post(()->{if(requestToken.equals(vault.token())&&requestEndpoint.equals(vault.endpoint()))lastError="";}); }
            catch(Exception error) {
                handler.post(()->{
                    if(!requestToken.equals(vault.token())||!requestEndpoint.equals(vault.endpoint()))return;
                    if(error instanceof Api.HttpError && ((Api.HttpError)error).status==401 && ((Api.HttpError)error).authenticated && !requestToken.isEmpty()) {
                        try { vault.token(""); } catch(Exception ignored) {}
                        account=null;profiles=new JSONArray();points=new JSONArray();
                        lastError="Your access is no longer valid. Ask your admin for an active code, then activate it here.";
                        stopService(new Intent(this,TunnelService.class));
                    } else if(quiet)lastError="Account refresh failed: "+(error.getMessage()==null?"check your internet connection.":error.getMessage());
                    else message(error.getMessage()==null?"Connection failed.":error.getMessage());
                });
            } finally { handler.post(()->{if(quiet)refreshing=false;else busy=false;if(visible)render();}); }
        });
    }
    void chooseCarrier() { if(profiles==null)profiles=new JSONArray();
        if(account==null&&!hasSavedProfile())for(int i=0;i<profiles.length();i++) {
            JSONObject saved=profiles.optJSONObject(i);
            if(saved!=null&&vault.bootstrap(saved.optString("id"))!=null) {carrier=saved.optString("carrier","MTN");selectedProfile=saved.optString("id");break;}
        }
if(carrierProfiles().length()==0&&profiles.length()>0)carrier=profiles.optJSONObject(0).optString("carrier","MTN"); }
    void refresh() { final String token=vault.token(), endpoint=vault.endpoint(); runNetwork(()->{JSONObject a=api.request("/v1/status",null,true);JSONArray p=api.request("/v1/profiles",null,true).getJSONArray("profiles");if(token.equals(vault.token())&&endpoint.equals(vault.endpoint()))vault.catalog(p);JSONArray history=tab.equals("Usage")?api.request("/v1/usage?hours="+graphHours,null,true).getJSONArray("points"):null;handler.post(()->{if(!token.equals(vault.token())||!endpoint.equals(vault.endpoint()))return;account=a;profiles=p;if(history!=null)points=history;chooseCarrier();render();});},true); }
    void loadGraph() { if(vault.token().isEmpty())return;runNetwork(()->{JSONArray data=api.request("/v1/usage?hours="+graphHours,null,true).getJSONArray("points");handler.post(()->{points=data;render();});}); }
    void message(String value) { if(!isFinishing())new AlertDialog.Builder(this).setMessage(value).setPositiveButton("OK",null).show(); }
    String bytes(long value) { if(value>=1e9)return String.format(Locale.US,"%.2f GB",value/1e9);if(value>=1e6)return String.format(Locale.US,"%.1f MB",value/1e6);if(value>=1000)return String.format(Locale.US,"%.1f KB",value/1000.0);return value+" B"; }
    String expiry(JSONObject a) { if(a.isNull("expires"))return "On first activation";SimpleDateFormat f=new SimpleDateFormat("dd MMM yyyy, HH:mm 'SAST'",Locale.UK);f.setTimeZone(TimeZone.getTimeZone("Africa/Johannesburg"));return f.format(new Date(a.optLong("expires")*1000)); }
    final class UsageGraph extends View {
        final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        UsageGraph(){super(MainActivity.this);setMinimumHeight(dp(190));setBackground(shape(PANEL,LINE,20));setContentDescription("Server traffic history, upload and download, last "+graphHours+" hours");}
        @Override protected void onDraw(Canvas c){super.onDraw(c);float w=getWidth(),h=getHeight(),pad=dp(25);paint.setStrokeWidth(dp(1));paint.setColor(LINE);for(int i=1;i<=4;i++)c.drawLine(pad,h*i/5,w-pad,h*i/5,paint);long max=1;for(int i=0;i<points.length();i++){JSONObject p=points.optJSONObject(i);max=Math.max(max,p.optLong("up")+p.optLong("down"));}if(points.length()==0){paint.setColor(MUTED);paint.setTextSize(dp(13));c.drawText("No recorded traffic in this period",pad,h/2,paint);}else{float bar=Math.min(dp(18),(w-pad*2)/Math.max(1,points.length()));for(int i=0;i<points.length();i++){JSONObject p=points.optJSONObject(i);float x=pad+i*(w-pad*2)/points.length(),up=(h-pad*2)*p.optLong("up")/max,down=(h-pad*2)*p.optLong("down")/max;paint.setColor(CYAN);c.drawRect(x,h-pad-up,x+bar,h-pad,paint);paint.setColor(MINT);c.drawRect(x,h-pad-up-down,x+bar,h-pad-up,paint);}}paint.setColor(CYAN);paint.setTextSize(dp(11));c.drawText("Upload",pad,h-dp(8),paint);paint.setColor(MINT);c.drawText("Download",w/2,h-dp(8),paint);}
    }
    final class Backdrop extends android.graphics.drawable.Drawable {
        final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        @Override public void draw(Canvas c){int w=getBounds().width(),h=getBounds().height();c.drawColor(BG);paint.setShader(new RadialGradient(w*.75f,h*.15f,Math.max(w,1),new int[]{0xff104359,BG},null,Shader.TileMode.CLAMP));c.drawRect(0,0,w,h,paint);paint.setShader(null);paint.setColor(0xff12334c);paint.setStrokeWidth(1);for(int i=-5;i<8;i++)c.drawLine(w/2f,h*.65f,w/2f+i*w/3f,h,paint);for(int i=0;i<7;i++)c.drawLine(0,h*(.70f+i*.05f),w,h*(.70f+i*.05f),paint);}
        @Override public void setAlpha(int a){}@Override public void setColorFilter(android.graphics.ColorFilter f){}@Override public int getOpacity(){return android.graphics.PixelFormat.OPAQUE;}
    }
}



