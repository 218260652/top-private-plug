package za.co.topprivateplug;

/** Customer text is selected from fixed messages, never server/engine payloads. */
final class CustomerMessage {
    static String forStatus(int status) {
        switch(status) {
            case 401: return "Please activate your access again.";
            case 403: return "Your access needs attention. Check your plan or contact support.";
            case 409: return "This request conflicts with existing access or a connection. Check your code, or disconnect and retry.";
            case 426: return "Please install the latest Top private Plug update.";
            case 429: return "Please wait a moment before trying again.";
            default: return "We could not complete this request. Please retry or contact support.";
        }
    }
    static String connection() { return "Unable to connect right now. Please retry or contact support."; }
    static String balance() { return "Balance temporarily unavailable. Tap Refresh to try again."; }
}
