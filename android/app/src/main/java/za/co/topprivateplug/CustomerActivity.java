package za.co.topprivateplug;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.VpnService;
import android.net.Uri;
import android.content.ActivityNotFoundException;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.ImageView;
import android.widget.PopupMenu;
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
    private static final int CYAN = 0xff12e5f3, WHITE = 0xfff1f7ff, MUTED = 0xffadc4db;
    private static final String[] CARRIERS = {"MTN", "Cell C", "Telkom"};
    private final Button[] tiles = new Button[CARRIERS.length];
    private TextView message, tunnel, up, down, ping;
    private ProgressBar progress;
    private Button connect, disconnect;
    private String carrier = "MTN";
    private String pendingCarrier;
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
        JSONObject saved = vault.customerCache();
        if (saved.has("account")) {
            account = saved.optJSONObject("account");
            networks = saved.optJSONArray("networks");
            render();
        } else if (vault.customerSession().has("marker")) {
            screen();
            brand(false, true);
            label("Loading…", 17).setGravity(Gravity.CENTER);
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

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private GradientDrawable background(int top, int bottom, int radius, int stroke) {
        GradientDrawable drawable = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
            new int[]{top, bottom});
        drawable.setCornerRadius(dp(radius));
        if (stroke != 0) drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private void screen() {
        connect = disconnect = null;
        tunnel = up = down = ping = null;
        getWindow().setStatusBarColor(0xff05111f);
        getWindow().setNavigationBarColor(0xff05111f);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundResource(R.drawable.customer_waves);
        scroll.setClipToPadding(false);
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 35 && getApplicationInfo().targetSdkVersion >= 35)
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(16), dp(16), dp(24));
        scroll.addView(root);
        setContentView(scroll);
        message = label("", 14);
        message.setTextColor(MUTED);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        progress = new ProgressBar(this);
        progress.setIndeterminateTintList(ColorStateList.valueOf(CYAN));
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams spinner = new LinearLayout.LayoutParams(dp(36), dp(36));
        spinner.gravity = Gravity.CENTER_HORIZONTAL;
        root.addView(progress, spinner);
    }

    private TextView text(String value, int size) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(WHITE);
        return text;
    }

    private TextView label(String value, int size) {
        TextView text = text(value, size);
        root.addView(text);
        return text;
    }

    private void gap(int height) { root.addView(new View(this), new LinearLayout.LayoutParams(1, dp(height))); }

    private void brand(boolean compact, boolean loading) {
        if (!compact) gap(loading ? 80 : 12);
        ImageView shield = new ImageView(this);
        shield.setImageResource(R.drawable.customer_shield);
        shield.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        int size = dp(compact ? 40 : loading ? 118 : 92);
        if (!compact) {
            LinearLayout.LayoutParams icon = new LinearLayout.LayoutParams(size, size);
            icon.gravity = Gravity.CENTER_HORIZONTAL;
            root.addView(shield, icon);
            gap(7);
        }
        TextView title = text("Top Private Plug", compact ? 19 : 28);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        TextView tagline = text("PRIVATE VPN", compact ? 10 : 17);
        tagline.setTextColor(CYAN);
        tagline.setLetterSpacing(.10f);
        tagline.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        tagline.setGravity(Gravity.CENTER);
        if (compact) {
            LinearLayout bar = new LinearLayout(this);
            bar.setGravity(Gravity.CENTER_VERTICAL);
            Button menu = new Button(this);
            menu.setText("☰");
            menu.setContentDescription("Open menu");
            menu.setMinWidth(0);
            menu.setBackgroundColor(Color.TRANSPARENT);
            menu.setTextColor(WHITE);
            bar.addView(menu, new LinearLayout.LayoutParams(dp(43), dp(48)));
            bar.addView(shield, new LinearLayout.LayoutParams(size, size));
            LinearLayout name = new LinearLayout(this);
            name.setOrientation(LinearLayout.VERTICAL);
            name.addView(title);
            name.addView(tagline);
            bar.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
            Button more = new Button(this);
            more.setText("⋮");
            more.setContentDescription("Account options");
            more.setMinWidth(0);
            more.setBackgroundColor(Color.TRANSPARENT);
            more.setTextColor(WHITE);
            bar.addView(more, new LinearLayout.LayoutParams(dp(40), dp(48)));
            menu.setOnClickListener(v -> accountMenu(v));
            more.setOnClickListener(v -> accountMenu(v));
            root.addView(bar);
        } else {
            root.addView(title);
            root.addView(tagline);
            gap(loading ? 72 : 18);
        }
    }

    private void accountMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add("Refresh account").setOnMenuItemClickListener(item -> {
            if (!busy) submit(this::fetchAccount, this::render);
            return true;
        });
        menu.getMenu().add("Connection report").setOnMenuItemClickListener(item -> { showConnectionReport(); return true; });
        menu.getMenu().add("Support").setOnMenuItemClickListener(item -> { support(); return true; });
        menu.getMenu().add("Log out").setOnMenuItemClickListener(item -> {
            if (!busy) {
                stopTunnel();
                submit(api::logout, () -> { account = null; networks = new JSONArray(); render(); });
            }
            return true;
        });
        menu.show();
    }

    private void showConnectionReport() {
        String report = "Selected carrier: " + carrier + "\nState: " + TunnelService.state + "\n" + ConnectionReport.snapshot();
        TextView body = text(report, 13);
        body.setPadding(dp(16), dp(12), dp(16), dp(12));
        body.setTextIsSelectable(true);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(body);
        new AlertDialog.Builder(this).setTitle("Connection report").setView(scroll)
            .setPositiveButton("Close", null)
            .setNeutralButton("Share", (dialog, which) -> {
                Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, report);
                try { startActivity(Intent.createChooser(send, "Share connection report")); }
                catch (ActivityNotFoundException ignored) { message.setText("Select and copy the report text instead."); }
            }).show();
    }

    private void support() {
        new AlertDialog.Builder(this).setTitle("Support")
            .setMessage("Contact the administrator who gave you your VPN account for access or password help.")
            .setPositiveButton("OK", null).show();
    }

    private LinearLayout card(int padding) {
        LinearLayout parent = root;
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(padding), dp(padding), dp(padding), dp(padding));
        panel.setBackground(background(0xff08263d, 0xff051321, 20, 0xff1a6789));
        parent.addView(panel, new LinearLayout.LayoutParams(-1, -2));
        root = panel;
        return parent;
    }

    private EditText field(String hint, int type) {
        EditText edit = new EditText(this);
        edit.setSingleLine(true);
        edit.setHint(hint);
        edit.setTextColor(WHITE);
        edit.setHintTextColor(MUTED);
        edit.setTextSize(16);
        edit.setInputType(type);
        edit.setPadding(dp(14), 0, dp(14), 0);
        edit.setBackground(background(0xff071a2c, 0xff061320, 12, 0xff397d9c));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(49));
        params.bottomMargin = dp(10);
        root.addView(edit, params);
        return edit;
    }

    private EditText passwordField(String hint) {
        EditText edit = field(hint, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        CheckBox reveal = new CheckBox(this);
        reveal.setText("Show password");
        reveal.setTextColor(WHITE);
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
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(0xff031523);
        button.setBackground(background(0xff05eced, 0xff0675f9, 28, 0));
        button.setMinHeight(dp(50));
        button.setOnClickListener(view -> { if (!busy) action.run(); });
        root.addView(button, new LinearLayout.LayoutParams(-1, -2));
        return button;
    }

    private void render() {
        screen();
        boolean signedIn = vault.customerSession().has("marker");
        brand(signedIn, false);
        if (!signedIn) {
            LinearLayout page = card(18);
            label("Login to Your Account", 20).setGravity(Gravity.CENTER);
            gap(18);
            EditText name = field("Username", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            name.setAutofillHints(View.AUTOFILL_HINT_USERNAME);
            EditText password = passwordField("Password");
            password.setAutofillHints(View.AUTOFILL_HINT_PASSWORD);
            CheckBox remember = new CheckBox(this);
            remember.setText("Remember me");
            remember.setChecked(true);
            remember.setTextColor(WHITE);
            root.addView(remember);
            gap(9);
            button("→  LOGIN", () -> {
                String username = name.getText().toString().trim();
                String value = password.getText().toString();
                boolean persist = remember.isChecked();
                password.setText("");
                submit(() -> { account = api.login(username, value, persist); fetchAccount(); }, this::render);
            });
            gap(13);
            label("Don’t have an account?", 14).setGravity(Gravity.CENTER);
            TextView contact = label("Contact Support", 15);
            contact.setGravity(Gravity.CENTER);
            contact.setTextColor(CYAN);
            contact.setMinHeight(dp(44));
            contact.setOnClickListener(v -> support());
            root = page;
            return;
        }
        gap(12);
        if (account == null) {
            label("Check your subscription to continue.", 17);
            button("Refresh account", () -> submit(this::fetchAccount, this::render));
            return;
        }
        if (account.optInt("must_change") != 0) {
            label("Choose a new password before connecting.", 17);
            EditText password = passwordField("New password (12 characters or more)");
            button("Change password", () -> {
                String value = password.getText().toString();
                password.setText("");
                submit(() -> { api.changePassword(value); fetchAccount(); }, this::render);
            });
            return;
        }
        renderConnection();
    }

    private void renderConnection() {
        LinearLayout page = card(12);
        label("🇿🇦  South Africa", 17);
        root = page;
        gap(10);
        LinearLayout choices = new LinearLayout(this);
        for (int i = 0; i < CARRIERS.length; i++) {
            String name = CARRIERS[i];
            Button choice = new Button(this);
            choice.setAllCaps(false);
            choice.setTextSize(14);
            choice.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            choice.setText(name);
            choice.setMinWidth(0);
            choice.setPadding(dp(4), 0, dp(4), 0);
            LinearLayout.LayoutParams tile = new LinearLayout.LayoutParams(0, dp(56), 1);
            if (i > 0) tile.leftMargin = dp(7);
            choices.addView(choice, tile);
            tiles[i] = choice;
            choice.setOnClickListener(view -> { carrier = name; updateTunnel(); });
        }
        root.addView(choices);
        gap(12);
        page = card(12);
        LinearLayout stats = new LinearLayout(this);
        up = metric(stats, "UPLOADED");
        down = metric(stats, "DOWNLOADED");
        ping = metric(stats, "LATENCY");
        root.addView(stats);
        root = page;
        gap(12);
        page = card(15);
        label("trial".equals(account.optString("account_type")) ? "Free Trial" : "VPN Subscription", 21).setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        TextView status = label(account.optString("status").toUpperCase(Locale.ROOT), 14);
        status.setTextColor("active".equals(account.optString("status")) ? 0xff5eeb75 : 0xffffca78);
        gap(10);
        label("Expires: " + DateFormat.getDateTimeInstance().format(new Date(account.optLong("expires") * 1000)), 14);
        label("Account: " + account.optString("username"), 14).setTextColor(MUTED);
        root = page;
        gap(16);
        connect = button("CONNECT", this::prepare);
        disconnect = button("DISCONNECT", this::stopTunnel);
        disconnect.setOnClickListener(view -> stopTunnel());
        gap(10);
        tunnel = label("", 15);
        tunnel.setGravity(Gravity.CENTER);
        gap(18);
        Button follow = button("Follow Creator on Facebook  ↗", this::openCreator);
        follow.setTextColor(CYAN);
        follow.setContentDescription("Follow Creator on Facebook for updates");
        follow.setBackground(background(0xff0a263c, 0xff061624, 15, 0xff2380b0));
        label("VPN news and updates", 12).setGravity(Gravity.CENTER);
        updateTunnel();
    }

    private void openCreator() {
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.facebook.com/ramashia997"));
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException ignored) {
            message.setText("No browser is available to open Facebook.");
        }
    }

    private TextView metric(LinearLayout stats, String caption) {
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.VERTICAL);
        TextView name = text(caption, 10);
        name.setGravity(Gravity.CENTER);
        name.setTextColor(MUTED);
        item.addView(name);
        TextView value = text("—", 17);
        value.setGravity(Gravity.CENTER);
        value.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        item.addView(value);
        stats.addView(item, new LinearLayout.LayoutParams(0, -2, 1));
        return value;
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
                    String marker = vault.customerSession().optString("marker");
                    submit(() -> {
                        JSONObject result = api.connect("Cell C", value);
                        try {
                            vault.saveCustomerConnection(marker, "Cell C", result.getJSONObject("config"));
                        } finally {
                            api.call("disconnect", new JSONObject().put("lease", result.getString("lease")));
                        }
                    }, () -> requestVpnPermission("Cell C"));
                }).show();
            return;
        }
        if (!Vault.usesBundledProfile(carrier)) {
            message.setText("Use working internet and tap Refresh account to save this profile.");
            return;
        }
        requestVpnPermission(carrier);
    }

    private void requestVpnPermission(String network) {
        pendingCarrier = network;
        Intent permission = VpnService.prepare(this);
        if (permission == null) startTunnel();
        else startActivityForResult(permission, 21);
    }

    private void startTunnel() {
        if (pendingCarrier == null || !vault.customerSession().has("marker")) return;
        Intent tunnelIntent = new Intent(this, TunnelService.class).putExtra("profile_id", pendingCarrier);
        pendingCarrier = null;
        startForegroundService(tunnelIntent);
    }

    private void stopTunnel() {
        if (!"Disconnected".equals(TunnelService.state)) {
            startService(new Intent(this, TunnelService.class).setAction("STOP"));
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 21) return;
        if (result == RESULT_OK) startTunnel();
        else { pendingCarrier = null; message.setText("VPN permission was declined."); }
    }

    private void updateTunnel() {
        if (tunnel == null) return;
        String state = TunnelService.state;
        boolean idle = "Disconnected".equals(state);
        boolean active = "Connected".equals(state) || TunnelService.TUNNEL_RUNNING.equals(state);
        long elapsed = active ? Math.max(0, SystemClock.elapsedRealtime() - TunnelService.connectedAt) / 1000 : 0;
        tunnel.setText(state + " · " + String.format(Locale.ROOT, "%02d:%02d:%02d", elapsed / 3600, (elapsed / 60) % 60, elapsed % 60)
            + "\n" + TunnelService.detail + "\nSelected: " + carrier);
        up.setText(android.text.format.Formatter.formatShortFileSize(this, TunnelService.uploaded));
        down.setText(android.text.format.Formatter.formatShortFileSize(this, TunnelService.downloaded));
        ping.setText(TunnelService.latency >= 0 ? TunnelService.latency + " ms" : "—");
        tunnel.setTextColor("Connected".equals(state) ? 0xff68ec78 : MUTED);
        connect.setVisibility(idle ? View.VISIBLE : View.GONE);
        disconnect.setVisibility(idle ? View.GONE : View.VISIBLE);
        disconnect.setText("Disconnecting".equals(state) ? "DISCONNECTING…" : active ? "DISCONNECT" : "CANCEL");
        connect.setEnabled(!busy && selectedAvailable());
        connect.setAlpha(connect.isEnabled() ? 1f : .55f);
        if (idle && !selectedAvailable()) tunnel.append("\n" + carrier + " profile unavailable");
        disconnect.setEnabled(!"Disconnecting".equals(state));
        int[] colors = {0xffffda14, 0xffff7b22, 0xff119af7};
        for (int i = 0; i < CARRIERS.length; i++) {
            Button tile = tiles[i];
            boolean selected = CARRIERS[i].equals(carrier);
            if (tile.isSelected() != selected || !tile.isActivated()) {
                tile.setSelected(selected);
                tile.setActivated(true);
                tile.setBackground(background(0xff0a263c, 0xff041320, 14, selected ? colors[i] : 0xff1b506e));
                tile.setTextColor(colors[i]);
            }
            tile.setEnabled(idle && !busy);
        }
    }

    private void fetchAccount() throws Exception {
        String marker = vault.customerSession().optString("marker");
        account = api.call("profile", null);
        if (account.optInt("must_change") != 0) return;
        networks = api.call("networks", null).getJSONArray("networks");
        vault.saveCustomerCatalog(marker, account, networks, new JSONObject());
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
