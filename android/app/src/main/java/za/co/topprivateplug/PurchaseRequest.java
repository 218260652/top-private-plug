package za.co.topprivateplug;

import java.net.URLEncoder;

/** Opens a customer-authored request; never confirms payment or sends a message. */
final class PurchaseRequest {
    static final String PHONE = "27703841868";
    static final String DISPLAY_PHONE = "+27 70 384 1868";

    static String message(boolean topUp, String selection, String carrier, String accountId) {
        if (selection == null || selection.length() > 100) throw new IllegalArgumentException("Invalid plan selection");
        if (!"MTN".equals(carrier) && !"Telkom".equals(carrier) && !"Cell C".equals(carrier)) carrier = "Not selected";
        String result = "Hi, I would like to " + (topUp ? "top up or renew my" : "buy") + " Top private Plug access.\n"
            + "Request: " + selection + "\nNetwork: " + carrier;
        if (accountId != null && accountId.matches("[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"))
            result += "\nAccount reference: " + accountId;
        return result + "\nPlease confirm available data bundles, price and payment instructions.";
    }

    static String supportUrl(String carrier,String accountId) {
        String text="Hi, I need help with Top private Plug.\nNetwork: "+("MTN".equals(carrier)||"Telkom".equals(carrier)||"Cell C".equals(carrier)?carrier:"Not selected");
        if(accountId!=null&&accountId.matches("[a-fA-F0-9-]{36}"))text+="\nAccount reference: "+accountId;
        try{return "https://wa.me/"+PHONE+"?text="+URLEncoder.encode(text,"UTF-8").replace("+","%20");}catch(java.io.UnsupportedEncodingException error){throw new IllegalStateException(error);}
    }
    static String url(boolean topUp, String selection, String carrier, String accountId) {
        try {
            return "https://wa.me/" + PHONE + "?text=" + URLEncoder.encode(message(topUp, selection, carrier, accountId), "UTF-8").replace("+", "%20");
        } catch (java.io.UnsupportedEncodingException error) { throw new IllegalStateException(error); }
    }
}

