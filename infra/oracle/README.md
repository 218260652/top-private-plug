# Singapore VM provisioner — bounded background worker

This is an independent infrastructure workflow; it does not modify the application.
It requests one on-demand `VM.Standard.A1.Flex` instance in the tenancy's Singapore
home region: 1 OCPU, 6 GB RAM, 50 GB boot disk, Ubuntu 24.04 Minimal ARM, public IP,
and automatic fault-domain placement. It discovers the existing public subnet in
`vpn-vcn`. This creates the VM only; VPN installation is a separate step.

## Activate from Termux

Stop the old phone retry process before enabling GitHub provisioning. These
commands run on the phone, where the existing keys are stored. They upload the
keys directly to GitHub Secrets, never to repository files or chat.

```sh
pkill -f '[p]ython.*oracle_retry.py'
pkg install gh -y
gh auth login --hostname github.com --git-protocol https --web
```

Sign in to GitHub as the repository owner when prompted. Then run:

```sh
gh secret set OCI_PRIVATE_KEY --repo 218260652/top-private-plug < ~/.oci/retry_api.pem
gh secret set OCI_PUBLIC_SSH_KEY --repo 218260652/top-private-plug < ~/.ssh/oracle_vpn.pub
gh workflow run oracle-provision.yml --repo 218260652/top-private-plug -f mode=check
```

Open Actions → **Oracle Singapore provisioner** and inspect the check's summary.
`CHECK_PASSED` verifies the credentials, network, compatible image, and configured
resource budget; it does not create anything. If it reports an existing VM, it
does not launch a replacement. After the check passes:

```sh
gh variable set OCI_PROVISIONING_ENABLED --repo 218260652/top-private-plug --body true
gh workflow run oracle-provision.yml --repo 218260652/top-private-plug -f mode=apply
```

The apply job now retries inside one running GitHub job. It does not depend on
cron schedules. A session lasts at most 345 minutes (5 hours 45 minutes), with a
355-minute job timeout. The phone can be turned off after GitHub has started.

The current job prints a heartbeat every minute and waits at least the saved
cooldown before another launch. Inspect the same run → **provision** →
**Check or watch Singapore provisioning** to see progress; attempts no longer
appear as separate runs. Capacity retries wait about five minutes; throttling
backs off up to 30 minutes. Once accepted, only that instance is monitored.

Changing this workflow file on main starts a session when the enable variable is
true. Ordinary application pushes do not start provisioning. To start another
session later, run the workflow with `mode=apply`. No automatic session chaining
is configured, so runner usage stays bounded.
A waiting runner also consumes minutes. Private-repository Actions usage consumes
the account's Actions allowance;
check billing settings before leaving it enabled. Resource budget checks do not
prove billing eligibility, monthly usage, or that every tenancy resource is free.

## Outcomes and controls

* `RUNNING`: the VM is running; summary includes its public IP when available.
  The workflow disables itself automatically. Keep the SSH private key on the phone.
* `ACCEPTED` / `PROVISIONING`: Oracle accepted the request. Later runs monitor that
  instance only. A launch response alone is not proof the VM is running.
* `NO_CAPACITY`: Oracle has no suitable host capacity. Wait for later attempts;
  this workflow cannot guarantee capacity.
* `THROTTLED` / `BACKOFF`: no immediate retry; cooldown grows up to 30 minutes.
* `STOPPED` / `ERROR`: read the summary before changing anything. Do not delete the
  state branch to restart an uncertain request.

Only a check that passed or a running VM makes the provisioning step green.
Capacity, cooldown, pending launches and expired campaigns return a nonzero status.
The summary explains the result. A red run during capacity shortages is expected.

The saved campaign still has a 72-hour hard limit and an additional 864-attempt
ceiling, but an individual background session stops after 345 minutes.
`WATCH_WINDOW_ENDED` means the session ended and needs a manual restart if wanted.
At campaign expiry the workflow disables itself. To stop immediately, cancel the
current run in Actions. Disabling the workflow also stops the worker at its next
heartbeat, within about a minute unless an API call is in progress. Setting
`OCI_PROVISIONING_ENABLED=false` prevents new sessions but does not change the
environment of an already running job; cancel that run separately.

## Durable safeguards

Single-workflow concurrency prevents overlapping GitHub jobs. State is committed
to `oracle-provisioner-state` before Oracle receives a request. Contents API SHA
checks prevent overwriting a concurrent state change. Retries retain the same
request token and exact payload. An uncertain outcome never permits automatic
token replacement. A saved accepted instance ID permanently prevents another
launch, even if that instance is later deleted.

Each attempt checks instances across accessible compartments and storage usage
against configured ceilings of 2 A1 OCPUs / 12 GB RAM and 200 GB boot/block storage.
An existing matching VM, including the phone script's name ending in a period,
is adopted instead of duplicated. Keep other creation scripts stopped: concurrency
controls apply only to this GitHub workflow, not other clients.

The state contains public SSH material and Oracle resource IDs, never the API
private key. `settings.json` contains account identifiers and API fingerprint.
If account settings or the SSH public key change, review saved state first.

## Development

```sh
python -m pip install -r infra/oracle/requirements.txt
python -m unittest discover -s infra/oracle -p 'test_*.py' -v
```

Tests use fake cloud responses and make no Oracle API calls. With the SDK installed,
they also validate actual Oracle launch-model construction.
