package za.co.topprivateplug;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.net.*;
import android.os.*;
import android.graphics.*;
import android.graphics.drawable.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.net.URI;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

public final class MainActivity extends Activity {
    int BG=0xff000000,PANEL=0xff101010,LINE=0xff303030,TEXT=0xfff5f5f5,MUTED=0xffb4b4b4;
    final int CYAN=0xffe6bf67,MINT=0xff85cf92,YELLOW=0xffffcb05,ORANGE=0xffea5b0c,TELKOM=0xff91e200;
    LinearLayout root,content,navigation; ScrollView scroll; Vault vault; Api api;
    JSONObject account; JSONArray profiles=new JSONArray(),points=new JSONArray();
    String tab="Home",carrier="MTN",selectedProfile="",lastError="",renderedTunnelState="",renderedTunnelDetail="",renderedTab="";
    boolean busy,refreshing,visible,renderedBalanceFresh; long accountSyncedAt; int graphHours=1; long nextAccountRefresh,metricAt,lastUp,lastDown;
    final TrafficMeter meter=new TrafficMeter();double uploadRate,downloadRate; final ArrayList<Float> liveSamples=new ArrayList<>();
    final ExecutorService network=Executors.newSingleThreadExecutor(),backgroundNetwork=Executors.newSingleThreadExecutor();
    final Handler handler=new Handler(Looper.getMainLooper()); SharedPreferences prefs; Bitmap planet; String activationDraft="";
    final ArrayList<TextView> liveLabels=new ArrayList<>(); UpdateController updates;
    final Runnable poll=new Runnable(){public void run(){if(!visible)return;long now=SystemClock.elapsedRealtime();
        boolean connected="Connected".equals(TunnelService.state);meter.sample(connected,TunnelService.uploaded,TunnelService.downloaded,now);uploadRate=meter.uploadMbps;downloadRate=meter.downloadMbps;
        if(connected){liveSamples.add((float)(uploadRate+downloadRate));if(liveSamples.size()>45)liveSamples.remove(0);}
        if(!busy&&!refreshing&&!vault.token().isEmpty()&&now>=nextAccountRefresh&&("Connected".equals(TunnelService.state)||("Disconnected".equals(TunnelService.state)&&NetworkState.usable(MainActivity.this)))){nextAccountRefresh=now+10000;refresh();}
        if(renderedBalanceFresh!=balanceFresh()||!renderedTunnelState.equals(TunnelService.state)||!renderedTunnelDetail.equals(TunnelService.detail))render();else updateLiveLabels();
        handler.postDelayed(this,1000);
    }};
    @Override public void onCreate(Bundle state){super.onCreate(state);prefs=getSharedPreferences("appearance",MODE_PRIVATE);vault=new Vault(this);api=new Api(vault);profiles=vault.catalog();chooseCarrier();
        root=new LinearLayout(this);root.setOrientation(1);root.setPadding(dp(16),dp(10),dp(16),dp(8));
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);root.setOnApplyWindowInsetsListener((v,insets)->{root.setPadding(dp(16),insets.getSystemWindowInsetTop()+dp(8),dp(16),insets.getSystemWindowInsetBottom()+dp(8));return insets;});setContentView(root);root.requestApplyInsets();
        updates=new UpdateController(this);if(getIntent().getBooleanExtra("show_updates",false))tab="Notifications";render();
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(intent.getBooleanExtra("show_updates",false)){tab="Notifications";render();}}
    @Override protected void onResume(){super.onResume();visible=true;handler.removeCallbacks(poll);handler.post(poll);render();if(updates!=null)updates.check(false);}
    @Override protected void onPause(){visible=false;handler.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);network.shutdownNow();backgroundNetwork.shutdownNow();if(updates!=null)updates.close();super.onDestroy();}
    @Override public void onBackPressed(){if(!tab.equals("Home")){tab="Home";render();}else super.onBackPressed();}
    int dp(float n){return (int)(n*getResources().getDisplayMetrics().density+.5f);}
    boolean light(){return false;}
    void palette(){BG=vault.token().isEmpty()?0xff050505:0xff03121e;PANEL=0xe60b1218;LINE=0xff9a8248;TEXT=0xfff5f5f5;MUTED=0xffb9bdc2;}
    GradientDrawable shape(int color,int border,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));if(border!=0)d.setStroke(dp(1),border);return d;}
    TextView text(String s,int size,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextColor(color);t.setTextSize(size);t.setLineSpacing(dp(2),1);t.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",0));return t;}
    void add(LinearLayout parent,View child,int margin){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(margin);parent.addView(child,p);}
    LinearLayout column(){LinearLayout v=new LinearLayout(this);v.setOrientation(1);return v;}
    LinearLayout panel(LinearLayout parent,int border){LinearLayout c=column();c.setPadding(dp(16),dp(17),dp(16),dp(17));c.setBackground(shape(PANEL,border,22));add(parent,c,14);return c;}
    LinearLayout card(){return panel(content,LINE);}
    void center(LinearLayout parent,String s,int size,int color,int bottom){TextView t=text(s,size,color,true);t.setGravity(Gravity.CENTER);add(parent,t,bottom);}
    boolean stillHome(){return tab.equals("Home");}
    Drawable feedback(Drawable background,int color){return stillHome()?background:new RippleDrawable(android.content.res.ColorStateList.valueOf(color),background,null);}
    void art(LinearLayout parent,String mode,int height){if(mode.equals("hero"))return;PremiumArt v=new PremiumArt(this,mode,height);parent.addView(v,new LinearLayout.LayoutParams(-1,dp(height)));}
    Button button(String label,boolean primary,View.OnClickListener click){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextSize(14);b.setTypeface(Typeface.create("sans-serif-medium",0));b.setTextColor(primary?0xff001329:TEXT);b.setMinHeight(dp(52));b.setPadding(dp(12),dp(8),dp(12),dp(8));
        GradientDrawable bg=primary?new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xffb58a28,0xfff2ce65,0xffbd902a}):shape(PANEL,LINE,15);bg.setCornerRadius(dp(28));bg.setStroke(dp(1),primary?0xffc9a74e:LINE);
        b.setBackground(feedback(bg,0x6600d5ff));b.setOnClickListener(click);b.setEnabled(!busy);return b;}
    void row(LinearLayout parent,String icon,String title,String subtitle,int color,Runnable action){LinearLayout r=new LinearLayout(this);r.setGravity(Gravity.CENTER_VERTICAL);r.setPadding(dp(11),dp(11),dp(12),dp(11));r.setBackground(feedback(shape(PANEL,LINE,17),0x4400d5ff));
        View glyph=new View(this){Paint p=new Paint(3);@Override protected void onDraw(Canvas c){drawIcon(c,icon,dp(10),dp(10),dp(28),color);}};glyph.setBackground(shape(light()?0xffddecf9:0xff181818,color,13));r.addView(glyph,new LinearLayout.LayoutParams(dp(48),dp(48)));
        LinearLayout labels=column();labels.setPadding(dp(12),0,dp(6),0);add(labels,text(title,16,TEXT,true),3);if(!subtitle.isEmpty())add(labels,text(subtitle,12,MUTED,false),0);r.addView(labels,new LinearLayout.LayoutParams(0,-2,1));TextView arrow=text("›",27,MUTED,false);r.addView(arrow);r.setContentDescription(title+". "+subtitle);r.setOnClickListener(v->action.run());r.setEnabled(!busy);add(parent,r,11);}
    void render(){if(isFinishing()||root==null)return;palette();renderedBalanceFresh=balanceFresh();int y=scroll==null||!tab.equals(renderedTab)?0:scroll.getScrollY();renderedTab=tab;renderedTunnelState=TunnelService.state;renderedTunnelDetail=TunnelService.detail;liveLabels.clear();root.removeAllViews();root.setBackground(new Backdrop());getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);getWindow().getDecorView().setSystemUiVisibility(light()?View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR:0);
        boolean activating=vault.token().isEmpty()&&tab.equals("Home");
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(0,dp(14),0,dp(12));
        if(activating){LinearLayout brand=column();center(brand,"SALVATION·MAHUMANE VPN",24,CYAN,7);center(brand,"P R I V A T E  V P N",12,CYAN,6);header.addView(brand,new LinearLayout.LayoutParams(-1,-2));}
        else{TextView menu=text("☰",22,MUTED,false);menu.setGravity(Gravity.CENTER);menu.setContentDescription("Open navigation menu");menu.setOnClickListener(v->showMenu());header.addView(menu,new LinearLayout.LayoutParams(dp(32),dp(48)));
            ImageView logo=new ImageView(this);logo.setImageResource(R.drawable.ic_launcher);logo.setContentDescription("Salvation Mahumane VPN logo");header.addView(logo,new LinearLayout.LayoutParams(dp(46),dp(46)));
            LinearLayout brand=column();brand.setPadding(dp(7),0,0,0);TextView name=text("SALVATION MAHUMANE VPN",16,TEXT,true);name.setMaxLines(1);name.setAutoSizeTextTypeUniformWithConfiguration(10,16,1,android.util.TypedValue.COMPLEX_UNIT_SP);add(brand,name,3);center(brand,"PRIVATE VPN",10,CYAN,0);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
            TextView more=text("⋮",25,MUTED,true);more.setGravity(Gravity.CENTER);more.setContentDescription("More options");more.setOnClickListener(v->showMenu());header.addView(more,new LinearLayout.LayoutParams(dp(28),dp(48)));}
        add(root,header,6);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);scroll.setVerticalScrollBarEnabled(false);content=column();scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(!lastError.isEmpty()&&!vault.token().isEmpty())row(content,"info","Account update",lastError,CYAN,()->refresh());
        switch(tab){case "Usage":usage();break;case "Plans":plans();break;case "Settings":settings();break;case "Account":accountPage();break;case "Notifications":notificationPage();break;case "Service settings":servicePage();break;case "Privacy & security":privacyPage();break;case "Support & help":supportPage();break;case "About":aboutPage();break;default:home();}
        scroll.post(()->scroll.scrollTo(0,y));updateLiveLabels();}
    void showMenu(){final String[] pages={"Home","Usage","Plans","Account","Settings","Notifications","Service settings","Support & help"};new AlertDialog.Builder(this).setTitle("Salvation Mahumane VPN").setItems(pages,(d,n)->{tab=pages[n];render();if(tab.equals("Usage"))loadGraph();}).setNegativeButton("Close",null).show();}
    void title(String heading,String subtitle){add(content,text(heading,29,TEXT,true),5);if(!subtitle.isEmpty())add(content,text(subtitle,14,MUTED,false),13);}
    void country(){LinearLayout box=column();box.setPadding(dp(12),dp(12),dp(12),dp(12));box.setBackground(shape(PANEL,LINE,24));TextView t=text(vault.token().isEmpty()?"●  South Africa":"🇿🇦 South Africa",18,vault.token().isEmpty()?CYAN:TEXT,vault.token().isEmpty());t.setGravity(vault.token().isEmpty()?Gravity.CENTER:Gravity.LEFT);add(box,t,0);add(content,box,13);}
    int networkColor(String n){return n.equals("MTN")?YELLOW:n.equals("Cell C")?ORANGE:TELKOM;}
    ImageView networkLogo(String n){ImageView image=new ImageView(this);image.setImageResource(n.equals("MTN")?R.drawable.network_mtn:n.equals("Cell C")?R.drawable.network_cellc:R.drawable.network_telkom);image.setScaleType(ImageView.ScaleType.FIT_CENTER);image.setContentDescription(n+" logo");image.setPadding(dp(7),dp(3),dp(7),dp(3));image.setBackground(shape(n.equals("MTN")?YELLOW:0xff101010,0,8));return image;}
    void carriers(){LinearLayout options=new LinearLayout(this);for(String n:new String[]{"MTN","Telkom","Cell C"}){int accent=networkColor(n);boolean selected=n.equals(carrier);LinearLayout item=column();item.setGravity(Gravity.CENTER);item.setPadding(dp(7),dp(8),dp(7),dp(6));item.setBackground(feedback(shape(PANEL,selected?accent:LINE,16),accent&0x66ffffff));item.addView(networkLogo(n),new LinearLayout.LayoutParams(-1,dp(36)));TextView label=text(n,12,light()?TEXT:accent,true);label.setGravity(Gravity.CENTER);add(item,label,0);item.setSelected(selected);item.setContentDescription(n+(selected?", selected":", select network"));item.setFocusable(true);item.setEnabled(!busy);item.setOnClickListener(v->{if(!"Disconnected".equals(TunnelService.state)){message("Disconnect before changing the network.");return;}carrier=n;selectedProfile="";render();});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(79),1);lp.setMargins(dp(4),dp(6),dp(4),dp(10));options.addView(item,lp);}add(content,options,0);}
    void home(){country();if(vault.token().isEmpty()){activation();return;}
        LinearLayout networks=new LinearLayout(this);networks.setGravity(Gravity.CENTER_VERTICAL);networks.setBackground(shape(0xfff4f5ff,0,19));networks.setClipToOutline(true);
        ImageView mtn=networkLogo("MTN");mtn.setBackgroundColor(YELLOW);mtn.setPadding(dp(35),dp(9),dp(35),dp(9));networks.addView(mtn,new LinearLayout.LayoutParams(0,dp(57),1));TextView plus=text("+",21,0xff000000,true);networks.addView(plus);TextView telkom=text("Telkom",27,0xff00a9ce,true);telkom.setGravity(Gravity.CENTER);networks.addView(telkom,new LinearLayout.LayoutParams(0,dp(57),1));networks.setContentDescription("MTN and Telkom. Tap to choose your assigned network.");networks.setOnClickListener(v->selectNetwork());add(content,networks,14);
        LinearLayout metrics=new LinearLayout(this);metrics.setPadding(dp(8),dp(13),dp(8),dp(13));metrics.setBackground(shape(PANEL,LINE,23));
        for(String key:new String[]{"uploaded","downloaded","latency"}){LinearLayout cell=column();center(cell,key.toUpperCase(Locale.ROOT),10,MUTED,3);TextView value=text("—",18,TEXT,true);value.setTag(key);value.setGravity(Gravity.CENTER);liveLabels.add(value);add(cell,value,0);metrics.addView(cell,new LinearLayout.LayoutParams(0,-2,1));}add(content,metrics,14);
        LinearLayout access=panel(content,CYAN);add(access,text(account==null?"Access saved":account.optString("kind").equals("trial")?"Free Trial":"Paid Access",23,TEXT,true),3);
        String status=account==null?"CHECKING ACCOUNT":account.optString("status","unknown").toUpperCase(Locale.ROOT);add(access,text(status,15,status.equals("ACTIVE")?MINT:CYAN,false),13);
        add(access,text("Expires: "+(account==null?"Checking…":expiry(account)),15,TEXT,false),2);add(access,text("Account: "+(account==null?"Checking…":account.optString("label",account.optString("id","—"))),14,MUTED,false),0);
        boolean connected="Connected".equals(TunnelService.state),connecting=!connected&&!"Disconnected".equals(TunnelService.state);
        Button connect=button(connected?"DISCONNECT":connecting?"CANCEL":"CONNECT",true,v->toggle());connect.setTextSize(16);add(content,connect,10);
        TextView state=text("",16,connected?MINT:MUTED,false);state.setTag("connection");state.setGravity(Gravity.CENTER);liveLabels.add(state);add(content,state,23);
        if(!TunnelService.detail.isEmpty()&&!connected)center(content,TunnelService.detail,12,MUTED,10);
        String groupUrl=getString(R.string.whatsapp_group_url);Button group=button(groupUrl.isEmpty()?"WhatsApp support":"Join WhatsApp Group  ↗",false,v->openUrl(groupUrl.isEmpty()?PurchaseRequest.supportUrl(carrier,account==null?null:account.optString("id",null)):groupUrl));group.setTextColor(CYAN);add(content,group,2);center(content,groupUrl.isEmpty()?"Account and connection help":"VPN news and updates",12,TEXT,0);
        View space=new View(this);content.addView(space,new LinearLayout.LayoutParams(-1,dp(150)));
    }
    void selectNetwork(){if(!"Disconnected".equals(TunnelService.state)){message("Disconnect before changing the network.");return;}String[] options={"MTN","Telkom","Cell C"};new AlertDialog.Builder(this).setTitle("Network").setSingleChoiceItems(options,Arrays.asList(options).indexOf(carrier),(d,n)->{carrier=options[n];selectedProfile="";d.dismiss();render();}).setNegativeButton("Cancel",null).show();}
    void connectionSteps(LinearLayout c){add(c,text("Establishing your secure connection…",13,MUTED,false),10);}
    void activation(){View globeSpace=new View(this);content.addView(globeSpace,new LinearLayout.LayoutParams(-1,dp(64)));LinearLayout c=panel(content,CYAN);c.setPadding(dp(22),dp(27),dp(22),dp(25));
        center(c,"Activate MTN/TELKOM /",23,CYAN,16);TextView intro=text("Enter a paid or trial code. Your network is detected automatically.",16,CYAN,false);intro.setGravity(Gravity.CENTER);add(c,intro,23);
        EditText code=new EditText(this);code.setSingleLine(true);code.setHint("Enter activation or trial code");code.setText(activationDraft);code.setTextColor(CYAN);code.setHintTextColor(0xffcbb77e);code.setTextSize(17);code.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);code.setPadding(dp(15),dp(20),dp(15),dp(20));code.setBackground(shape(0xff090a0b,LINE,19));code.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){activationDraft=s.toString();}public void afterTextChanged(android.text.Editable value){}});add(c,code,20);
        Button activate=button(busy?"ACTIVATING…":"ACTIVATE",true,v->{String value=code.getText().toString().trim();if(value.isEmpty()){code.setError("Enter your code");return;}if(vault.endpoint().isEmpty()){endpointDialog();return;}activateCode(value);});activate.setTextSize(20);activate.setMinHeight(dp(65));add(c,activate,13);
        Button cancel=button("Cancel activation",false,v->{if(busy){message("Activation is in progress. Please wait for the result.");return;}activationDraft="";code.setText("");});cancel.setBackgroundColor(Color.TRANSPARENT);cancel.setTextColor(CYAN);add(c,cancel,12);
        if(!lastError.isEmpty())center(c,"Could not finish activation. Your code is retained; tap ACTIVATE to try again.",14,CYAN,0);
        center(content,"Cell C: first activation needs mobile data or Wi-Fi. After activation, your saved Cell C plan reconnects until expiry.",13,CYAN,15);
    }
    void activateCode(String code){runNetwork(()->{JSONObject a=api.activate(code);JSONObject p=api.request("/v1/profiles",null,true);vault.catalog(p.getJSONArray("profiles"));api.prepareProfiles(p.getJSONArray("profiles"));handler.post(()->{lastError="";account=a;accountSyncedAt=SystemClock.elapsedRealtime();profiles=p.optJSONArray("profiles");chooseCarrier();tab="Home";render();activationSuccess();});});}
    void activationSuccess(){LinearLayout box=column();box.setPadding(dp(22),dp(20),dp(22),dp(20));box.setBackground(shape(PANEL,CYAN,22));center(box,"✓",70,MINT,8);center(box,"Access activated!",24,TEXT,12);TextView body=text("The server has recorded your start time. You can now connect to the VPN.",15,MUTED,false);body.setGravity(Gravity.CENTER);add(box,body,20);AlertDialog dialog=new AlertDialog.Builder(this).setView(box).create();add(box,button("OK",true,v->dialog.dismiss()),0);dialog.show();if(dialog.getWindow()!=null)dialog.getWindow().setBackgroundDrawableResource(android.R.color.transparent);}
    boolean balanceFresh(){return account!=null && accountSyncedAt>0 && SystemClock.elapsedRealtime()-accountSyncedAt<30000;}
    void planCard(){LinearLayout c=card();add(c,text("Your access",16,TEXT,true),9);if(account==null){add(c,text("Activate your access to see its limits.",14,MUTED,false),0);return;}String status=account.optString("status","unknown");add(c,text(status.equals("active")?"● ACTIVE":status.toUpperCase(Locale.ROOT),12,status.equals("active")?MINT:YELLOW,true),10);
        if(!balanceFresh()){add(c,text("Balance temporarily unavailable",21,TEXT,true),8);add(c,text("Refresh your account to see your latest usage and remaining data.",13,MUTED,false),12);add(c,button("Refresh",true,v->refresh()),10);row(c,"chat","Contact support","Help with your account",MINT,()->openUrl(PurchaseRequest.supportUrl(carrier,null)));return;}
        if(tab.equals("Usage")){LinearLayout details=new LinearLayout(this);PremiumArt gauge=new PremiumArt(this,"remaining",180);details.addView(gauge,new LinearLayout.LayoutParams(0,dp(180),1));LinearLayout nums=column();nums.setPadding(dp(10),dp(25),0,0);add(nums,text("Used  "+bytes(account.optLong("used")),13,CYAN,true),15);add(nums,text("Total plan\n"+bytes(account.optLong("quota")),14,MUTED,true),0);details.addView(nums,new LinearLayout.LayoutParams(0,-2,1));add(c,details,7);}else{add(c,text(bytes(account.optLong("remaining_bytes"))+" remaining",23,TEXT,true),10);ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);progress.setProgress((int)Math.max(0,Math.min(1000,1000.0*account.optLong("remaining_bytes")/Math.max(1,account.optLong("quota")))));progress.setProgressTintList(android.content.res.ColorStateList.valueOf(CYAN));add(c,progress,8);}
        add(c,text(bytes(account.optLong("used"))+" used of "+bytes(account.optLong("quota"))+" • upload + download",11,MUTED,false),13);add(c,text("Expires: "+expiry(account)+"\nNetwork: "+carrier,12,MUTED,false),14);row(c,"chat","Top up via WhatsApp","Choose data, price and validity",MINT,()->{tab="Plans";render();});}
    void liveCard(){LinearLayout c=card();add(c,text("Live usage   ● LIVE",18,TEXT,true),13);TextView counters=text("",17,CYAN,true);counters.setTag("counters");liveLabels.add(counters);add(c,counters,4);art(c,"spark",42);TextView session=text("",12,MUTED,false);session.setTag("session");liveLabels.add(session);add(c,session,0);}
    void updateLiveLabels(){for(TextView t:liveLabels){String tag=String.valueOf(t.getTag());if(tag.equals("uploaded"))t.setText(bytes(TunnelService.uploaded));else if(tag.equals("downloaded"))t.setText(bytes(TunnelService.downloaded));else if(tag.equals("latency"))t.setText(TunnelService.latency<0?"—":TunnelService.latency+" ms");else if(tag.equals("connection"))t.setText(TunnelService.state+("Connected".equals(TunnelService.state)?" · "+sessionTime():""));else if(tag.equals("rates"))t.setText(sessionTime()+"    ↓ "+String.format(Locale.US,"%.2f Mbps",downloadRate)+"    ↑ "+String.format(Locale.US,"%.2f Mbps",uploadRate));else if(tag.equals("counters"))t.setText("↑ "+bytes(TunnelService.uploaded)+" uploaded\n↓ "+bytes(TunnelService.downloaded)+" downloaded");else t.setText("◷ "+sessionTime()+"    •    "+(TunnelService.latency<0?"Latency —":TunnelService.latency+" ms")+"    •    "+carrier);}}
    String sessionTime(){long s=TunnelService.connectedAt>0&&"Connected".equals(TunnelService.state)?(SystemClock.elapsedRealtime()-TunnelService.connectedAt)/1000:0;return String.format(Locale.US,"%02d:%02d:%02d",s/3600,(s/60)%60,s%60);}
    void usage(){title("Usage","Real-time data usage and account overview.");if(vault.token().isEmpty()){activation();return;}planCard();liveCard();LinearLayout c=card();add(c,text("Data usage history",19,TEXT,true),13);LinearLayout ranges=new LinearLayout(this);for(int hours:new int[]{1,6,24,168}){Button b=button(hours==168?"7D":hours+"H",graphHours==hours,v->{graphHours=hours;loadGraph();});LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(44),1);p.setMargins(dp(2),0,dp(2),0);ranges.addView(b,p);}add(c,ranges,6);art(c,"chart",195);add(c,text("● Upload    ● Download\n7D shows the server history synced on this phone.",11,MUTED,false),0);row(content,"speed","Speed test (fast.com)","Open the test in your browser",MINT,()->openUrl("https://fast.com/"));}
    void plans(){title("Choose Your Plan","Fast. Secure. Affordable.");carriers();for(String net:new String[]{"MTN","Telkom"}){int accent=networkColor(net);LinearLayout c=panel(content,accent);c.addView(networkLogo(net),new LinearLayout.LayoutParams(dp(106),dp(44)));add(c,text(net+" Plans",23,accent,true),5);add(c,text("Choose a data allowance and validity",12,MUTED,false),13);for(int r=0;r<2;r++){LinearLayout line=new LinearLayout(this);for(int col=0;col<2;col++){int index=r*2+col;PlanCatalog.Plan plan=PlanCatalog.PLANS[index];LinearLayout pc=column();pc.setPadding(dp(12),dp(14),dp(12),dp(12));pc.setBackground(shape(PANEL,accent,17));add(pc,text(plan.gigabytes+" GB",20,TEXT,true),7);add(pc,text("R"+plan.rand,29,accent,true),3);add(pc,text(plan.days+" days",12,MUTED,false),14);Button get=button("Get Plan",false,v->requestPlan(net,index));get.setTextColor(0xff001329);get.setBackground(new RippleDrawable(android.content.res.ColorStateList.valueOf(0x66ffffff),shape(accent,accent,15),null));add(pc,get,0);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.setMargins(dp(3),0,dp(3),dp(9));line.addView(pc,lp);}add(c,line,0);}}
        LinearLayout cell=panel(content,ORANGE);cell.addView(networkLogo("Cell C"),new LinearLayout.LayoutParams(dp(106),dp(44)));add(cell,text("Cell C Plans",23,ORANGE,true),5);add(cell,text("Contact your admin for Cell C bundles, prices and validity.",12,MUTED,false),13);add(cell,button("Request Cell C plan",false,v->openUrl(PurchaseRequest.url(account!=null,"Cell C VLESS bundles and pricing","Cell C",account==null?null:account.optString("id",null)))),0);
        row(content,"clock","Have a trial code?","Tap here to activate your code",CYAN,()->codeDialog(true));}
    void requestPlan(String net,int index){PlanCatalog.Plan p=PlanCatalog.PLANS[index];openUrl(PurchaseRequest.url(account!=null,p.gigabytes+" GB • R"+p.rand+" • "+p.days+" days",net,account==null?null:account.optString("id",null)));}
    void settings(){title("Settings","Manage your account and app preferences.");row(content,"account","Account","View your account details",CYAN,()->page("Account"));row(content,"bell","Notifications","Updates and account alerts",YELLOW,()->page("Notifications"));row(content,"speed","Speed test (fast.com)","Check your internet speed",MINT,()->openUrl("https://fast.com/"));row(content,"settings","Service settings","Network and connection settings",CYAN,()->page("Service settings"));row(content,"shield","Privacy & security","Your data and connection security",0xffab65ff,()->page("Privacy & security"));row(content,"help","Support & help","Get help or contact support",CYAN,()->page("Support & help"));row(content,"info","About","App information and version",CYAN,()->page("About"));LinearLayout c=card();add(c,text("Appearance",17,TEXT,true),8);add(c,text("Salvation black and gold",14,CYAN,false),0);}

    void page(String name){tab=name;render();}
    void accountPage(){title("Account","Your access and account details.");if(vault.token().isEmpty()){activation();return;}planCard();LinearLayout c=card();add(c,text("Account reference\n"+(account==null?"Check your account first":account.optString("id","—")),13,MUTED,false),12);add(c,button("Refresh account",false,v->refresh()),9);add(c,button("Activate another code",false,v->codeDialog(false)),9);add(c,button("Log out",false,v->new AlertDialog.Builder(this).setTitle("Log out?").setMessage("This disconnects the VPN and removes saved access from this phone. Your subscription expiry is unchanged. Keep your activation code to sign in again.").setNegativeButton("Cancel",null).setPositiveButton("Log out",(d,n)->logout()).show()),0);}
    void logout(){if(busy||refreshing){message("Wait for the account request to finish, then log out.");return;}stopService(new Intent(this,TunnelService.class));try{vault.token("");}catch(Exception error){message("Could not remove saved access. Please retry.");return;}account=null;profiles=new JSONArray();points=new JSONArray();selectedProfile="";lastError="";liveSamples.clear();tab="Home";render();}
    void notificationPage(){title("Notifications","App updates and account alerts.");LinearLayout c=card();add(c,text(updates.status,16,TEXT,true),9);if(updates.available())add(c,button(updates.downloading?"Downloading update…":"New update · "+updates.versionName,true,v->updates.download()),10);if(updates.ready())add(c,button("Install downloaded update",true,v->updates.install()),10);add(c,button("Check for updates",false,v->updates.check(true)),0);if(balanceFresh()){LinearLayout alerts=card();add(alerts,text("Account status · "+account.optString("status","unknown"),16,TEXT,true),7);add(alerts,text(bytes(account.optLong("remaining_bytes"))+" remaining\nExpires: "+expiry(account),13,MUTED,false),0);}settingSwitch("Update notifications","Show an alert when a new release is found","notify_updates",true);settingSwitch("Account alerts","Low data and approaching expiry","notify_account",true);row(content,"bell","Android notification settings","Connection notification and permission controls",YELLOW,()->{Intent i=new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName());startActivity(i);});}
    void settingSwitch(String label,String detail,String key,boolean defaultValue){LinearLayout c=card();add(c,text(label,16,TEXT,true),5);add(c,text(detail,12,MUTED,false),8);Switch sw=new Switch(this);sw.setText("Enabled");sw.setTextColor(TEXT);sw.setChecked(prefs.getBoolean(key,defaultValue));sw.setOnCheckedChangeListener((b,on)->prefs.edit().putBoolean(key,on).apply());add(c,sw,0);}
    void servicePage(){title("Service settings","Manage saved network configurations.");carriers();savedProfileStatus(content);}
    void privacyPage(){title("Privacy & security","Understand your connection and privacy.");LinearLayout c=card();add(c,text("Device keys are stored in Android Keystore. Saved access and connection profiles are encrypted on your phone. The service records account status, activation time and upload/download totals. The app does not request contacts, location or media access.\n\nCertificate verification depends on the assigned VPN profile. Profiles with verification disabled show a test warning on Home.\n\nUpdates are checked against the expected package name, file checksum and your installed signing certificate before Android's installer opens.\n\nThe VPN starts only after fresh account approval. Always-on VPN and a kill switch are not included in this pilot.",14,MUTED,false),0);settingSwitch("Reduce motion","Pause decorative glows and planet movement","reduce_motion",false);row(content,"shield","Android VPN settings","Manage system VPN preferences",CYAN,()->startActivity(new Intent(android.provider.Settings.ACTION_VPN_SETTINGS)));}
    void supportPage(){title("Support & help","Help with your access and connection.");row(content,"chat","WhatsApp support",PurchaseRequest.DISPLAY_PHONE,MINT,()->openUrl(PurchaseRequest.supportUrl(carrier,account==null?null:account.optString("id",null))));LinearLayout c=card();add(c,text("Connection help",19,TEXT,true),10);add(c,text("Save your assigned profile once on Wi-Fi. Then switch to mobile data and connect.\n\nIf your connection is interrupted, allow automatic reconnect to finish or try again shortly.\n\nIf access cannot be verified, contact WhatsApp support. Avoid uninstalling or clearing app data while troubleshooting.",14,MUTED,false),0);}
    void aboutPage(){title("About","Salvation Mahumane VPN VPN");LinearLayout c=card();add(c,text("Salvation Mahumane VPN\nVersion "+UpdatePolicy.VERSION_NAME,22,TEXT,true),13);add(c,text("An Android client for your admin's assigned VLESS and Trojan profiles. Network compatibility depends on your assigned profile and carrier. This app does not supply a mobile data bundle.\n\nAndroidLibXrayLite · LGPL-3.0\nXray-core · MPL-2.0",14,MUTED,false),16);add(c,button("Open-source licences",false,v->showLicenses()),0);}
    void accountRecovery(){LinearLayout c=card();add(c,text("Access saved",21,TEXT,true),9);add(c,text("Your login is saved. Connect using a saved profile or refresh your account on Wi-Fi.",14,MUTED,false),13);if(hasSavedProfile())add(c,button("Connect using saved profile",true,v->toggle()),10);add(c,button("Retry account check",false,v->refresh()),9);}
    AccessState.State accessState(){return AccessState.resolve(!vault.token().isEmpty(),account!=null,account==null?"":account.optString("status"));}
    void openUrl(String url){try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE));}catch(ActivityNotFoundException e){message("Install a browser or WhatsApp to open this link.");}}
    void addReportButton(LinearLayout parent) {
        Button report=button("Help with connection",false,v->showConnectionReport());
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
        final String report="Salvation Mahumane VPN support\nNetwork: "+carrier+"\nConnection: "+TunnelService.state+"\nVersion: "+UpdatePolicy.VERSION_NAME;
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
    void savedProfileStatus(LinearLayout parent) {
        boolean ready=hasSavedProfile();
        add(parent,text(ready?"Connection settings saved for "+carrier+". Tap Connect to test this network.":"No saved connection for "+carrier+". Use Wi-Fi once to save connection settings.",12,ready?MINT:0xffffcc88,false),10);
        Button save=button(refreshing?"Saving / checking…":"Refresh connection settings on Wi-Fi",false,v->refresh(true));
        save.setEnabled(!busy&&!refreshing&&"Disconnected".equals(TunnelService.state));add(parent,save,12);
    }
    boolean hasSavedProfile() {
        JSONArray available=carrierProfiles();
        for(int i=0;i<available.length();i++) if(vault.bootstrap(available.optJSONObject(i).optString("id"))!=null) return true;
        return false;
    }
    void toggle() {
        if("Disconnecting".equals(TunnelService.state)){message("The tunnel is closing. Please wait before reconnecting.");return;}
        if(!"Disconnected".equals(TunnelService.state)){startService(new Intent(this,TunnelService.class).setAction("STOP"));handler.postDelayed(this::render,300);return;}
        if(busy)return;
        if(refreshing){message("Wait for connection settings to finish saving, then connect.");return;}
        if(!hasSavedProfile()&&!NetworkState.usable(this)){message("No saved connection settings for "+carrier+". Turn on Wi-Fi, tap Refresh connection settings, and wait for Connection settings saved. Then test mobile data again.");return;}
        AccessState.State access=accessState();
        if(access==AccessState.State.ACTIVATION_REQUIRED){codeDialog(false);return;}
        if(access==AccessState.State.CHECK_REQUIRED && !hasSavedProfile()){
            if(!refreshing)refresh();
            message("Your activation is saved. We need to reach the account service before connecting. Check your internet or try Wi-Fi, then retry the account check.");return;
        }
        if(access==AccessState.State.INACTIVE && !hasSavedProfile()){message("The service last reported your account as "+account.optString("status","unavailable")+". Retry the account check or contact your admin.");return;}
        JSONArray available=carrierProfiles();if(available.length()==0){message("No assigned profile for "+carrier+".");return;}
        boolean found=false;for(int i=0;i<available.length();i++)if(available.optJSONObject(i).optString("id").equals(selectedProfile))found=true;
        if(!found || (!NetworkState.usable(this) && vault.bootstrap(selectedProfile)==null)) {
            selectedProfile=available.optJSONObject(0).optString("id");
            for(int i=0;i<available.length();i++) if(vault.bootstrap(available.optJSONObject(i).optString("id"))!=null) {selectedProfile=available.optJSONObject(i).optString("id");break;}
        }
        new AlertDialog.Builder(this).setTitle("Connect to Salvation Mahumane VPN?").setMessage("Your internet traffic will pass through your service's VPN server. Upload and download both count toward your allowance.")
            .setPositiveButton("Continue",(d,n)->{Intent permission=VpnService.prepare(this);if(permission==null)startTunnel();else startActivityForResult(permission,77);}).setNegativeButton("Cancel",null).show();
    }
    @Override protected void onActivityResult(int request,int result,Intent data) { super.onActivityResult(request,result,data);if(request==77&&result==RESULT_OK)startTunnel(); }
    void startTunnel() {
        if(busy||refreshing){message("Wait for connection settings to finish saving, then connect.");return;}
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},78);
        startForegroundService(new Intent(this,TunnelService.class).putExtra("profile_id",selectedProfile));handler.postDelayed(this::render,400);
    }
    void codeDialog(boolean trial) {
        if(!"Disconnected".equals(TunnelService.state)){message("Disconnect before activating another code.");return;}
        if(vault.endpoint().isEmpty()){endpointDialog();return;}
        EditText input=new EditText(this);input.setSingleLine(true);input.setHint("TPP-…");input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);input.setPadding(dp(24),dp(16),dp(24),dp(16));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(trial?"Enter trial code":"Enter activation code").setView(input).setPositiveButton("Activate",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String code=input.getText().toString().trim();if(code.isEmpty()){input.setError("Enter your code");return;}dialog.dismiss();runNetwork(()->{JSONObject a=api.activate(code);JSONObject p=api.request("/v1/profiles",null,true);vault.catalog(p.getJSONArray("profiles"));api.prepareProfiles(p.getJSONArray("profiles"));handler.post(()->{lastError="";account=a;accountSyncedAt=SystemClock.elapsedRealtime();profiles=p.optJSONArray("profiles");chooseCarrier();tab="Home";render();activationSuccess();});});}));dialog.show();
    }
    void endpointDialog() {
        EditText input=new EditText(this);input.setSingleLine(true);input.setText(vault.endpoint());input.setHint("https://admin.your-domain.co.za");input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);input.setPadding(dp(24),dp(16),dp(24),dp(16));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Service address").setMessage("Use the HTTPS address supplied by your VPN admin. Changing it clears your local access login.").setView(input).setPositiveButton("Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try{String value=input.getText().toString().trim().replaceAll("/+$","");URI uri=new URI(value);if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||(!uri.getPath().isEmpty()&&!uri.getPath().equals("/")))throw new Exception();stopService(new Intent(this,TunnelService.class));vault.endpoint(value);account=null;profiles=new JSONArray();dialog.dismiss();render();}catch(Exception error){input.setError("Enter an HTTPS origin without a path, username or query.");}}));dialog.show();
    }
    interface Work { void run() throws Exception; }
    void runNetwork(Work work) { runNetwork(work,false); }
    void runNetwork(Work work,boolean quiet) {
        if (busy || refreshing) return;
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
                    } else if(quiet){lastError=balanceFresh()?"Connection settings could not refresh. Try again shortly.":CustomerMessage.balance();}
                    else {lastError=error instanceof Api.HttpError?CustomerMessage.forStatus(((Api.HttpError)error).status):CustomerMessage.connection();message(lastError);}
                });
            } finally { handler.post(()->{if(quiet)refreshing=false;else busy=false;if(visible)render();}); }
        });
    }
    void chooseCarrier() { try{android.telephony.TelephonyManager tm=getSystemService(android.telephony.TelephonyManager.class);String op=tm==null?"":tm.getNetworkOperator();if(op.equals("65510"))carrier="MTN";else if(op.equals("65502"))carrier="Telkom";else if(op.equals("65507"))carrier="Cell C";}catch(Exception ignored){} if(profiles==null)profiles=new JSONArray();
        if(account==null&&!hasSavedProfile())for(int i=0;i<profiles.length();i++) {
            JSONObject saved=profiles.optJSONObject(i);
            if(saved!=null&&vault.bootstrap(saved.optString("id"))!=null) {carrier=saved.optString("carrier","MTN");selectedProfile=saved.optString("id");break;}
        }
if(carrierProfiles().length()==0&&profiles.length()>0)carrier=profiles.optJSONObject(0).optString("carrier","MTN"); }
    void refresh() { refresh(false); }
    void refresh(boolean replaceSaved) {
        if(!"Disconnected".equals(TunnelService.state)&&!"Connected".equals(TunnelService.state))return;
        if("Disconnected".equals(TunnelService.state)&&!NetworkState.usable(this)) {
            lastError=hasSavedProfile()?"Mobile internet is unavailable. Tap Connect to verify through your saved profile.":"No saved connection settings for "+carrier+". Use Wi-Fi once and tap Refresh connection settings.";render();return;
        }
        final String token=vault.token(), endpoint=vault.endpoint(); runNetwork(()->{JSONObject a;try{a=api.request("/v1/status",null,true);}catch(Exception e){handler.post(()->{if(token.equals(vault.token())&&endpoint.equals(vault.endpoint()))accountSyncedAt=0;});throw e;}handler.post(()->{if(token.equals(vault.token())&&endpoint.equals(vault.endpoint())){account=a;accountSyncedAt=SystemClock.elapsedRealtime();render();}});JSONArray p=api.request("/v1/profiles",null,true).getJSONArray("profiles");if(token.equals(vault.token())&&endpoint.equals(vault.endpoint())){vault.catalog(p);if("Disconnected".equals(TunnelService.state))api.prepareProfiles(p,replaceSaved);}JSONArray history=tab.equals("Usage")?fetchHistory():null;handler.post(()->{if(!token.equals(vault.token())||!endpoint.equals(vault.endpoint()))return;updates.accountAlerts(a);profiles=p;if(history!=null)points=history;chooseCarrier();render();});},true); }
    void loadGraph() { if(vault.token().isEmpty())return;runNetwork(()->{JSONArray data=fetchHistory();handler.post(()->{points=data;render();});}); }
    void message(String value) { if(!isFinishing())new AlertDialog.Builder(this).setMessage(value).setPositiveButton("OK",null).show(); }
    String bytes(long value) { if(value>=1e9)return String.format(Locale.US,"%.2f GB",value/1e9);if(value>=1e6)return String.format(Locale.US,"%.1f MB",value/1e6);if(value>=1000)return String.format(Locale.US,"%.1f KB",value/1000.0);return value+" B"; }
    String expiry(JSONObject a) { if(a.isNull("expires"))return "On first activation";SimpleDateFormat f=new SimpleDateFormat("dd MMM yyyy HH:mm:ss",Locale.UK);f.setTimeZone(TimeZone.getTimeZone("Africa/Johannesburg"));return f.format(new Date(a.optLong("expires")*1000)); }
    JSONArray fetchHistory() throws Exception {
        String expectedToken=vault.token(),expectedOrigin=vault.endpoint();
        JSONArray fresh=api.request("/v1/usage?hours="+(graphHours==168?24:graphHours),null,true).getJSONArray("points");
        return vault.mergeHistory(fresh,graphHours,expectedToken,expectedOrigin);
    }
    void drawIcon(Canvas c,String kind,float x,float y,float size,int color){c.save();c.translate(x,y);c.scale(size/48,size/48);Paint p=new Paint(3);p.setColor(color);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(3);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);Path path=new Path();
        switch(kind){case "shield":path.moveTo(24,3);path.lineTo(42,11);path.lineTo(40,29);path.cubicTo(37,38,29,43,24,46);path.cubicTo(18,42,10,37,7,28);path.lineTo(6,11);path.close();c.drawPath(path,p);c.drawLine(19,14,19,24,p);c.drawLine(29,14,29,24,p);c.drawRoundRect(16,22,32,30,4,4,p);c.drawLine(24,30,24,37,p);break;
        case "home":path.moveTo(5,22);path.lineTo(24,6);path.lineTo(43,22);path.moveTo(11,19);path.lineTo(11,42);path.lineTo(20,42);path.lineTo(20,29);path.lineTo(28,29);path.lineTo(28,42);path.lineTo(37,42);path.lineTo(37,19);c.drawPath(path,p);break;
        case "usage":for(int i=0;i<3;i++){float top=i==0?25:i==1?9:18;c.drawRoundRect(7+i*13,top,14+i*13,41,2,2,p);}break;
        case "database":c.drawOval(7,5,41,17,p);c.drawLine(7,11,7,36,p);c.drawLine(41,11,41,36,p);c.drawArc(7,23,41,43,0,180,false,p);c.drawArc(7,12,41,30,0,180,false,p);break;
        case "account":c.drawCircle(24,14,8,p);c.drawArc(7,24,41,53,190,160,false,p);break;
        case "clock":c.drawCircle(24,24,19,p);c.drawLine(24,12,24,25,p);c.drawLine(24,25,33,31,p);break;
        case "bell":path.moveTo(11,31);path.lineTo(13,17);path.cubicTo(14,6,34,6,35,17);path.lineTo(37,31);path.lineTo(41,35);path.lineTo(7,35);path.close();c.drawPath(path,p);c.drawArc(19,35,29,44,0,180,false,p);break;
        case "power":c.drawArc(6,7,42,43,-45,270,false,p);c.drawLine(24,3,24,23,p);break;
        case "chat":c.drawCircle(24,23,18,p);c.drawLine(9,34,6,44,p);c.drawLine(6,44,18,39,p);path.moveTo(17,15);path.cubicTo(13,25,28,36,33,29);c.drawPath(path,p);break;
        case "globe":c.drawCircle(24,24,19,p);c.drawOval(15,5,33,43,p);c.drawLine(6,18,42,18,p);c.drawLine(6,30,42,30,p);break;
        case "speed":c.drawArc(5,7,43,45,150,240,false,p);c.drawLine(24,28,34,15,p);c.drawCircle(24,28,3,p);break;
        case "help":c.drawArc(6,5,42,42,180,180,false,p);c.drawRoundRect(4,23,12,37,3,3,p);c.drawRoundRect(36,23,44,37,3,3,p);c.drawLine(40,37,30,43,p);break;
        case "info":c.drawCircle(24,24,19,p);c.drawCircle(24,15,1,p);c.drawLine(24,23,24,34,p);break;
        default:c.drawCircle(24,24,10,p);c.drawCircle(24,24,19,p);for(int i=0;i<8;i++){double angle=Math.PI*i/4;c.drawLine(24+(float)Math.cos(angle)*18,24+(float)Math.sin(angle)*18,24+(float)Math.cos(angle)*23,24+(float)Math.sin(angle)*23,p);}break;
        }c.restore();}
    final class Backdrop extends Drawable {
        final Paint p=new Paint(3);final Runnable tick=()->invalidateSelf();
        @Override public void draw(Canvas c){c.drawColor(BG);float w=getBounds().width(),h=getBounds().height();c.save();c.scale(w/400f,h/850f);
            if(vault.token().isEmpty())drawGlobe(c);else{drawRibbon(c,620,90,0xff5d4514,0xffdbb33e);drawRibbon(c,735,-105,0xff9f7720,0xffecc958);}c.restore();}
        void drawRibbon(Canvas c,float y,float slope,int dark,int gold){Path ribbon=new Path();ribbon.moveTo(-45,y);ribbon.cubicTo(120,y+slope,230,y+125,445,y+slope);ribbon.lineTo(445,y+slope+68);ribbon.cubicTo(230,y+193,120,y+slope+68,-45,y+68);ribbon.close();p.setStyle(Paint.Style.FILL);p.setShader(new LinearGradient(0,0,400,0,new int[]{dark,gold,dark},null,Shader.TileMode.CLAMP));c.drawPath(ribbon,p);p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(1.5f);p.setColor(0xffbda04f);c.drawPath(ribbon,p);p.setStyle(Paint.Style.FILL);}
        void drawGlobe(Canvas c){p.setStyle(Paint.Style.FILL);p.setShader(new RadialGradient(200,430,310,new int[]{0xff282921,0xff10110f,0xff050505},null,Shader.TileMode.CLAMP));c.drawOval(-150,143,550,780,p);p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setColor(0xffb99a4e);p.setStrokeWidth(1.3f);c.drawOval(-150,143,550,780,p);p.setColor(0xff38382c);for(int i=1;i<6;i++)c.drawOval(-150+i*48,143,550-i*48,780,p);for(int i=0;i<5;i++)c.drawOval(-150,205+i*65,550,280+i*65,p);
            p.setStyle(Paint.Style.FILL);Drawable continents=getDrawable(R.drawable.planet_gold);continents.setBounds(0,0,400,850);continents.draw(c);}

        @Override public void setAlpha(int alpha){}@Override public void setColorFilter(ColorFilter filter){}@Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
}


