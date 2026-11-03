package za.co.topprivateplug;

import android.graphics.*;
import android.view.View;
import java.util.Locale;
import org.json.JSONObject;

/** Small, lifecycle-bound canvas animations. No network or synthetic usage data. */
final class PremiumArt extends View {
    long sampleAt;
    void sampleChanged(){sampleAt=android.os.SystemClock.uptimeMillis();invalidate();}
    final MainActivity a; final String mode; final Paint p=new Paint(3);
    PremiumArt(MainActivity a,String mode,int height){super(a);this.a=a;this.mode=mode;setMinimumHeight(a.dp(height));setContentDescription(mode.equals("remaining")?"Remaining account data":"VPN "+mode);}
    float d(float n){return a.dp(n);}
    boolean motionEnabled(){return false;}
    void line(Canvas c,int color,float width){p.reset();p.setAntiAlias(true);p.setColor(color);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(d(width));p.setStrokeCap(Paint.Cap.ROUND);}
    void label(Canvas c,String s,float x,float y,int size,int color,boolean bold){p.reset();p.setAntiAlias(true);p.setColor(color);p.setTextSize(d(size));p.setTypeface(bold?Typeface.create("sans-serif-medium",0):Typeface.create("sans-serif",0));p.setTextAlign(Paint.Align.CENTER);c.drawText(s,x,y,p);}
    @Override protected void onDraw(Canvas c){
        super.onDraw(c);float w=getWidth(),h=getHeight(),cx=w/2,cy=h/2;
        float angle=motionEnabled()?(android.os.SystemClock.uptimeMillis()%6000)*.06f:0;
        if(mode.equals("hero")){
            if(a.planet!=null){p.reset();p.setFilterBitmap(true);float drift=motionEnabled()?(float)Math.sin(angle*Math.PI/180)*d(4):0;c.drawBitmap(a.planet,new Rect(0,(int)(a.planet.getHeight()*.10),a.planet.getWidth(),(int)(a.planet.getHeight()*.49)),new RectF(-d(5)+drift,0,w+d(5)+drift,h),p);}
            p.setShader(new LinearGradient(0,h*.6f,0,h,0x00030d1c,a.BG,Shader.TileMode.CLAMP));c.drawRect(0,h*.6f,w,h,p);p.setShader(null);
            if(a.vault.token().isEmpty()){float size=Math.min(h*.60f,d(94));a.drawIcon(c,"shield",cx-size/2,cy-size/2,size,a.CYAN);}
        } else if(mode.equals("power")||mode.equals("remaining")){
            boolean gauge=mode.equals("remaining"),connected="Connected".equals(TunnelService.state),connecting="Connecting".equals(TunnelService.state);
            float r=Math.min(w,h)*.39f;int color=gauge?a.CYAN:connected?a.MINT:a.CYAN;
            if(!gauge){p.reset();p.setAntiAlias(true);p.setShader(new RadialGradient(cx,cy,r*1.3f,new int[]{color&0x16ffffff,color&0x33ffffff,0x00000000},new float[]{0,.74f,1},Shader.TileMode.CLAMP));c.drawCircle(cx,cy,r*1.3f,p);p.setShader(null);}
            line(c,color,1);p.setAlpha(28);c.drawCircle(cx,cy,r+d(12),p);p.setStrokeWidth(d(12));p.setAlpha(18);c.drawCircle(cx,cy,r,p);
            line(c,a.LINE,gauge?13:3);c.drawCircle(cx,cy,r,p);
            RectF arc=new RectF(cx-r,cy-r,cx+r,cy+r);
            if(gauge){long total=a.account==null?0:a.account.optLong("quota"),remaining=a.account==null?0:a.account.optLong("remaining_bytes");float fraction=Math.max(0,Math.min(1,(float)remaining/Math.max(1,total)));line(c,color,13);p.setShader(new SweepGradient(cx,cy,new int[]{a.CYAN,0xff346dff,0xff9c43ff,a.CYAN},null));c.drawArc(arc,-90,360*fraction,false,p);p.setShader(null);label(c,a.account==null?"—":a.bytes(remaining),cx,cy-d(1),a.account!=null&&a.bytes(remaining).length()>9?16:21,a.TEXT,true);label(c,"remaining",cx,cy+d(21),13,a.MUTED,false);}
            else {line(c,color,3);c.drawCircle(cx,cy,r,p);a.drawIcon(c,connecting?"shield":"power",cx-d(26),cy-d(26),d(52),color);}
            line(c,color,4);p.setShadowLayer(d(9),0,0,color);c.drawArc(arc,angle,connecting?95:18,false,p);p.clearShadowLayer();
        } else if(mode.startsWith("icon:")){a.drawIcon(c,mode.substring(5),cx-d(16),cy-d(16),d(32),a.CYAN);}
        else if(mode.equals("chart"))drawHistory(c,w,h,angle);
        else if(mode.equals("spark")){
            line(c,a.DOWNLOAD,2);int n=a.liveSamples.size();if(n>1){Path path=new Path();float max=1;for(float v:a.liveSamples)max=Math.max(max,v);for(int i=0;i<n;i++){float x=w*i/(n-1),y=h-d(6)-(h-d(14))*(a.liveSamples.get(i)+(i>0?(a.liveSamples.get(i-1)-a.liveSamples.get(i))*(1-Math.min(1,(android.os.SystemClock.uptimeMillis()-sampleAt)/250f)):0))/max;if(i==0)path.moveTo(x,y);else path.lineTo(x,y);}c.drawPath(path,p);}else label(c,"Live traffic appears when connected",w/2,h/2,11,a.MUTED,false);
        }
        if(mode.equals("spark")&&!a.prefs.getBoolean("reduce_motion",false)&&android.os.SystemClock.uptimeMillis()-sampleAt<250)postInvalidateOnAnimation();
        if(motionEnabled())postInvalidateDelayed(40);
    }
    void drawHistory(Canvas c,float w,float h,float angle){
        float l=d(46),r=w-d(12),top=d(14),bottom=h-d(36);long max=1;int count=a.points.length();
        for(int i=0;i<count;i++){JSONObject v=a.points.optJSONObject(i);max=Math.max(max,Math.max(v.optLong("up"),v.optLong("down")));}
        for(int i=0;i<4;i++){float y=top+(bottom-top)*i/3;line(c,a.LINE,.6f);c.drawLine(l,y,r,y,p);label(c,a.bytes((long)(max*(3-i)/3.0)),d(21),y+d(4),9,a.MUTED,false);}
        if(count==0){label(c,"No recorded usage in this period",(l+r)/2,(top+bottom)/2,12,a.MUTED,false);return;}
        long first=a.points.optJSONObject(0).optLong("at"),last=a.points.optJSONObject(count-1).optLong("at");
        for(String key:new String[]{"up","down"}){Path path=new Path();int color=key.equals("up")?a.UPLOAD:a.DOWNLOAD;float lastX=l;
            for(int i=0;i<count;i++){JSONObject v=a.points.optJSONObject(i);float x=l+(r-l)*(last==first?.5f:(float)(v.optLong("at")-first)/(last-first)),y=bottom-(bottom-top)*v.optLong(key)/max;if(i==0)path.moveTo(x,y);else path.lineTo(x,y);lastX=x;}
            Path area=new Path(path);area.lineTo(lastX,bottom);area.lineTo(count==1?(l+r)/2:l,bottom);area.close();p.reset();p.setAntiAlias(true);p.setShader(new LinearGradient(0,top,0,bottom,color,0x00102040,Shader.TileMode.CLAMP));p.setAlpha(85);c.drawPath(area,p);line(c,color,2);c.drawPath(path,p);
            JSONObject v=a.points.optJSONObject(count-1);float y=bottom-(bottom-top)*v.optLong(key)/max;p.setStyle(Paint.Style.FILL);p.setAlpha(180+(int)(60*Math.sin(angle*Math.PI/180)));c.drawCircle(lastX,y,d(3),p);
        }
        java.text.SimpleDateFormat f=new java.text.SimpleDateFormat(a.graphHours==168?"dd MMM":"HH:mm",Locale.UK);f.setTimeZone(java.util.TimeZone.getTimeZone("Africa/Johannesburg"));label(c,f.format(new java.util.Date(first*1000)),l+d(12),h-d(12),10,a.MUTED,false);label(c,f.format(new java.util.Date(last*1000)),r-d(17),h-d(12),10,a.MUTED,false);
    }
}



