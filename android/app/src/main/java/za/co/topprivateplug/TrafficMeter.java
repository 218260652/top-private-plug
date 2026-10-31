package za.co.topprivateplug;

/** Average over actual counter updates, rather than treating batched stats as 1-second bursts. */
final class TrafficMeter {
    private long at=-1,up,down;
    double uploadMbps,downloadMbps;
    void sample(boolean connected,long uploaded,long downloaded,long now){
        if(!connected){at=-1;uploadMbps=downloadMbps=0;return;}
        if(at<0||uploaded<up||downloaded<down){at=now;up=uploaded;down=downloaded;uploadMbps=downloadMbps=0;return;}
        if(now>at&&(uploaded!=up||downloaded!=down)){
            uploadMbps=(uploaded-up)*.008/(now-at);downloadMbps=(downloaded-down)*.008/(now-at);
            at=now;up=uploaded;down=downloaded;
        }else if(now-at>12000)uploadMbps=downloadMbps=0;
    }
}
