package za.co.topprivateplug;

import java.net.URI;

/** Reject arbitrary update sources before downloading any executable bytes. */
final class UpdatePolicy {
    // Must match versionCode/versionName in android/app/build.gradle and tools/build_android.py.
    static final int VERSION_CODE=101;
    static final String VERSION_NAME="1.0.1";
    static final String HOST="salvation-mahumane-vpn.ramashiaandrew3.chatgpt.site";
    static final String MANIFEST="https://"+HOST+"/updates/latest.json";
    static String manifestFor(String[] abis) {
        for(String abi:abis)if("arm64-v8a".equals(abi))return "https://"+HOST+"/updates/arm64-v8a.json";
        return "https://"+HOST+"/updates/armeabi-v7a.json";
    }
    static void validate(int code,String name,String url,String hash,long size)throws Exception{
        URI u=new URI(url);
        if(code<1||name==null||name.length()>60||!"https".equals(u.getScheme())||!HOST.equals(u.getHost())||u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||(u.getPort()!=-1&&u.getPort()!=443)
            ||!u.getPath().matches("/downloads/Salvation-Mahumane-VPN-[0-9]+\\.[0-9]+\\.[0-9]+-(arm64-v8a|armeabi-v7a)\\.apk")||hash==null||!hash.matches("[0-9a-f]{64}")||size<10000||size>100*1024*1024L)throw new Exception("The update information was rejected. Please contact support.");
    }
}

