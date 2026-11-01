package za.co.hostlab;
import java.net.InetAddress;
/** Public endpoint filter; no DNS calls. */
public final class EndpointRules {
 private EndpointRules(){}
 public static boolean validPath(String path){return path!=null&&path.length()<=1024&&path.startsWith("/")&&!path.startsWith("//")&&!path.chars().anyMatch(ch->ch<=32||ch>=127||ch==35||ch==92);}
 public static boolean isPublic(InetAddress address){
  if(address.isAnyLocalAddress()||address.isLoopbackAddress()||address.isLinkLocalAddress()||address.isSiteLocalAddress()||address.isMulticastAddress())return false;
  byte[] b=address.getAddress();
  if(b.length==4){int x=b[0]&255,y=b[1]&255,z=b[2]&255;
   return !(x==0||x==10||x==127||x>=224||x==169&&y==254||x==172&&y>=16&&y<=31||x==192&&y==168||x==100&&y>=64&&y<=127||x==198&&(y==18||y==19)||x==192&&y==0&&(z==0||z==2)||x==192&&y==88&&z==99||x==198&&y==51&&z==100||x==203&&y==0&&z==113);
  }
  if((b[0]&0xe0)!=0x20)return false;
  int a=b[0]&255,c=b[1]&255,d=b[2]&255,e=b[3]&255;
  if(a==0x20&&c==0x01&&d==0x0d&&e==0xb8)return false;
  if(a==0x3f&&c==0xff&&(d&0xf0)==0)return false;
  if(a==0x20&&c==0x01&&d==0&&((e&0xf0)==0x10||(e&0xf0)==0x20))return false;
  return !(a==0x20&&c==0x01&&d==0&&e==2&&b[4]==0&&b[5]==0);
 }
}
