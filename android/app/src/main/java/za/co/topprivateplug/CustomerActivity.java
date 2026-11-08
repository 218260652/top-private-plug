package za.co.topprivateplug;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.VpnService;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CustomerActivity extends Activity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Vault vault;
    private CustomerApi api;
    private JSONObject account;
    private JSONArray networks = new JSONArray();
    private LinearLayout root;
    private TextView message, tunnel;
    private ProgressBar progress;
    private Button connect, disconnect;
    private String carrier = "MTN";
    private String pendingCarrier;
    private String pendingCode;
    private boolean busy;
    private final Runnable ticker = new Runnable() {
        @Override public void run() { updateTunnel(); handler.postDelayed(this, 1000); }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        vault = new Vault(this);
        if (!vault.staging) { finish(); return; }
        api = new CustomerApi(vault);
        if (state != null) pendingCarrier = state.getString("pendingCarrier");
        if (vault.customerSession().has("marker")) {
            screen();
            submit(this::fetchAccount, this::render);
        } else render();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString("pendingCarrier", pendingCarrier);
    }

    @Override protected void onStart() { super.onStart(); handler.post(ticker); }
    @Override protected void onStop() { handler.removeCallbacks(ticker); super.onStop(); }
    @Override protected void onDestroy() { worker.shutdown(); super.onDestroy(); }

    private void screen() {
        connect = disconnect = null;
        tunnel = null;
        ScrollView scroll = new ScrollView(this);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        root.setPadding(padding, padding, padding, padding);
        scroll.addView(root);
        setContentView(scroll);
        label("TOP PRIVATE PLUG", 27);

        message = label("", 15);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        progress = new ProgressBar(this);
        progress.setVisibility(View.GONE);
        root.addView(progress);
    }

    private TextView label(String value, int size) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        root.addView(text);
        return text;
    }

    private EditText field(String hint, int type) {
        EditText edit = new EditText(this);
        edit.setSingleLine(true);
        edit.setHint(hint);
        edit.setInputType(type);
        root.addView(edit);
        return edit;
    }

    private EditText passwordField(String hint) {
        EditText edit = field(hint, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox reveal = new CheckBox(this);
        reveal.setText("Show password");
        reveal.setOnCheckedChangeListener((button, checked) -> {
            edit.setTransformationMethod(checked ? null : PasswordTransformationMethod.getInstance());
            edit.setSelection(edit.length());
        });
        root.addView(reveal);
        return edit;
    }

    private Button button(String caption, Runnable action) {
        Button button = new Button(this);
        button.setText(caption);
        button.setOnClickListener(view -> { if (!busy) action.run(); });
        root.addView(button);
        return button;
    }

    private void render() {
        screen();
        if (!vault.customerSession().has("marker")) {
            EditText name = field("Username", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            name.setAutofillHints(View.AUTOFILL_HINT_USERNAME);
            EditText password = passwordField("Password");
            password.setAutofillHints(View.AUTOFILL_HINT_PASSWORD);
            button("LOGIN", () -> {
                String username = name.getText().toString().trim();
                String value = password.getText().toString();
                password.setText("");
                submit(() -> { account = api.login(username, value); fetchAccount(); }, this::render);
            });
            label("Forgot your password? Contact your administrator for a temporary password.", 14);
            return;
        }
        if (account == null) {
            label("Check your subscription to continue.", 17);
            button("Refresh account", () -> submit(this::fetchAccount, this::render));
        } else if (account.optInt("must_change") != 0) {
            label("Choose a new password before connecting.", 17);
            EditText password = passwordField("New password (12 characters or more)");
            button("Change password", () -> {
                String value = password.getText().toString();
                password.setText("");
                submit(() -> { api.changePassword(value); fetchAccount(); }, this::render);
            });
        } else {
            label("Account: " + account.optString("username"), 18);
            label("Subscription: " + account.optString("status"), 16);
            label("Expires: " + DateFormat.getDateTimeInstance().format(new Date(account.optLong("expires") * 1000)), 16);
            tunnel = label("", 18);
            RadioGroup choices = new RadioGroup(this);
            for (int i = 0; i < networks.length(); i++) {
                JSONObject profile = networks.optJSONObject(i);
                String name = profile.optString("carrier");
                if (!"MTN".equals(name) && !"Telkom".equals(name) && !"Cell C".equals(name)) continue;
                boolean enabled = available(profile);
                RadioButton choice = new RadioButton(this);
                choice.setId(View.generateViewId());
                choice.setText(name + (enabled ? (profile.optInt("tested") != 0 ? " · verified" : " · carrier verification pending") : " · unavailable"));
                choices.addView(choice);
                if (carrier.equals(name)) choices.check(choice.getId());
                choice.setOnClickListener(view -> { carrier = name; updateTunnel(); });
            }
            root.addView(choices);
            connect = button("Connect", this::prepare);
            disconnect = button("Disconnect", this::stopTunnel);
            button("Refresh account", () -> submit(this::fetchAccount, this::render));
            updateTunnel();
        }
        button("Log out", () -> {
            stopTunnel();
            submit(api::logout, () -> { account = null; networks = new JSONArray(); render(); });
        });
    }

    private boolean available(JSONObject profile) {
        return profile.optInt("enabled") != 0 && profile.optInt("insecure") == 0;
    }

    private boolean selectedAvailable() {
        for (int i = 0; i < networks.length(); i++) {
            JSONObject profile = networks.optJSONObject(i);
            if (carrier.equals(profile.optString("carrier"))) return available(profile);
        }
        return false;
    }

    private void prepare() {
        if ("Cell C".equals(carrier)) {
            EditText code = new EditText(this);
            code.setHint("Cell C code");
            code.setSingleLine(true);
            code.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
            code.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
            new AlertDialog.Builder(this).setTitle("Unlock Cell C").setView(code)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Connect", (dialog, which) -> {
                    String value = code.getText().toString().trim();
                    code.setText("");
                    if (value.isEmpty()) { message.setText("Enter the Cell C code."); return; }
                    requestVpnPermission("Cell C", value);
                }).show();
            return;
        }
        requestVpnPermission(carrier, null);
    }

    private void requestVpnPermission(String network, String code) {
        pendingCarrier = network;
        pendingCode = code;
        Intent permission = VpnService.prepare(this);
        if (permission == null) startTunnel();
        else startActivityForResult(permission, 21);
    }

    private void startTunnel() {
        if (pendingCarrier == null || !vault.customerSession().has("marker")) return;
        if ("Cell C".equals(pendingCarrier) && pendingCode == null) {
            pendingCarrier = null;
            message.setText("Enter the Cell C code again.");
            return;
        }
        Intent tunnelIntent = new Intent(this, TunnelService.class).putExtra("profile_id", pendingCarrier);
        if (pendingCode != null) tunnelIntent.putExtra("carrier_code", pendingCode);
        pendingCarrier = null;
        pendingCode = null;
        startForegroundService(tunnelIntent);
    }

    private void stopTunnel() { stopService(new Intent(this, TunnelService.class)); }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 21) return;
        if (result == RESULT_OK) startTunnel();
        else { pendingCarrier = null; pendingCode = null; message.setText("VPN permission was declined."); }
    }

    private void updateTunnel() {
        if (tunnel == null) return;
        String state = TunnelService.state;
        boolean idle = "Disconnected".equals(state);
        long elapsed = "Connected".equals(state) ? Math.max(0, SystemClock.elapsedRealtime() - TunnelService.connectedAt) / 1000 : 0;
        tunnel.setText(state + " · " + String.format(Locale.ROOT, "%02d:%02d:%02d", elapsed / 3600, (elapsed / 60) % 60, elapsed % 60)
            + "\n" + TunnelService.detail + "\nSelected: " + carrier);
        connect.setEnabled(!busy && idle && selectedAvailable());
        disconnect.setEnabled(!busy && !idle);
    }

    private void fetchAccount() throws Exception {
        account = api.call("profile", null);
        if (account.optInt("must_change") == 0) networks = api.call("networks", null).getJSONArray("networks");
    }

    private interface Work { void run() throws Exception; }

    private void submit(Work work, Runnable success) {
        busy = true;
        message.setText("");
        progress.setVisibility(View.VISIBLE);
        updateTunnel();
        worker.execute(() -> {
            String error = null;
            try { work.run(); }
            catch (Exception failure) { error = failure.getMessage() == null ? "The service request failed. Try again." : failure.getMessage(); }
            final String result = error;
            handler.post(() -> {
                if (isDestroyed()) return;
                busy = false;
                progress.setVisibility(View.GONE);
                if (result == null) success.run();
                else {
                    if (!vault.customerSession().has("marker") || account != null) render();
                    else button("Retry account check", () -> submit(this::fetchAccount, this::render));
                    message.setText(result);
                }
                updateTunnel();
            });
        });
    }
}
