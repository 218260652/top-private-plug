# 0.1.15 pilot: still Home and bounded recovery

Home retains the existing Earth backdrop but has no separate hero/foreground Earth, header pulse, moving lights, rotating ring or touch ripple. The power icon and its static glow remain. Usage and other tabs retain their existing motion preferences.

A single user Connect session allows five automatic recovery attempts after transient TCP/DNS/timeouts, proxy 429/503, selected temporary API failures or an unexpected engine stop. Delays grow from 2 to 32 seconds; proxy failures wait at least 30 seconds. A previous authorized lease adds a 35-second minimum to avoid overlapping leases if disconnect reporting fails. The app displays Reconnecting with an attempt count and Cancel instead of requiring a user-managed cooldown. This cannot override supplier capacity or limits.

Transient heartbeat failures retry within the existing 30-second authorization deadline; failures never extend that deadline. Authorization denials and certificate trust failures remain terminal. STOP, Android revocation, service destruction, logout and origin/token changes cancel pending recovery. Transport cleanup completes and the old worker exits before another attempt starts. No automatic restart after a process kill is promised.

Verification: Java policy/cancellation regression harnesses, backend tests, native Android compilation and emulator Home snapshots/assertions. Physical MTN/Telkom recovery and speed still require a phone test.
