package za.co.topprivateplug;

/** Missing account data after process restart is not a rejected activation. */
final class AccessState {
    enum State { ACTIVATION_REQUIRED, CHECK_REQUIRED, ACTIVE, INACTIVE }
    static State resolve(boolean hasToken, boolean hasAccount, String status) {
        if (!hasToken) return State.ACTIVATION_REQUIRED;
        if (!hasAccount) return State.CHECK_REQUIRED;
        return "active".equals(status) ? State.ACTIVE : State.INACTIVE;
    }
}
