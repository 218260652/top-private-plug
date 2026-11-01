import java.net.InetAddress;
import za.co.hostlab.EndpointRules;
public class EndpointRulesTest {
 public static void main(String[] args)throws Exception {
  String[] rejected={"127.0.0.1","10.1.2.3","192.168.1.1","100.64.0.1","172.16.0.1","169.254.3.4","192.0.2.1","198.51.100.1","203.0.113.1","::1","fc00::1","fe80::1","2001:db8::1","3fff::1"};
  for(String s:rejected)if(EndpointRules.isPublic(InetAddress.getByName(s)))throw new AssertionError("Accepted special-use address: "+s);
  String[] accepted={"1.1.1.1","8.8.8.8","198.51.99.1","203.0.112.1","2001:4860:4860::8888","2606:4700:4700::1111"};
  for(String s:accepted)if(!EndpointRules.isPublic(InetAddress.getByName(s)))throw new AssertionError("Rejected public address: "+s);
  System.out.println("20 address-boundary checks passed.");
 }
}
