"""One Singapore launch attempt per run, with durable GitHub state.

Never stores the API signing key. A successful HTTP launch is not RUNNING.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

REGION = "ap-singapore-1"
SHAPE = "VM.Standard.A1.Flex"
NAME = "top-private-plug-vps"
STATE_BRANCH = "oracle-provisioner-state"
STATE_PATH = "oracle-provisioner-state.json"
CAMPAIGN_SECONDS = 72 * 3600
TOKEN_SECONDS = 22 * 3600


class Stop(Exception):
    pass


class GitHubState:
    """Contents API SHA checks fail closed if another writer changed state."""
    def __init__(self, repository, token, default_branch):
        self.base = "https://api.github.com/repos/" + repository
        self.token, self.default_branch, self.sha = token, default_branch, None

    def api(self, method, path, body=None, missing_ok=False):
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            # Response bodies can include user-controlled content; do not log them.
            raise Stop("GitHub state API failed (HTTP %s); no further launch." % error.code) from None

    def load(self):
        blob = self.api("GET", "/contents/" + STATE_PATH + "?ref=" + STATE_BRANCH,
                        missing_ok=True)
        if blob is None:
            return None
        self.sha = blob["sha"]
        return json.loads(base64.b64decode(blob["content"]))

    def save(self, state):
        ref = self.api("GET", "/git/ref/heads/" + STATE_BRANCH, missing_ok=True)
        if ref is None:
            head = self.api("GET", "/git/ref/heads/" + self.default_branch)
            self.api("POST", "/git/refs", {
                "ref": "refs/heads/" + STATE_BRANCH, "sha": head["object"]["sha"]})
        body = {"message": "Record Oracle provisioning outcome [skip ci]",
                "branch": STATE_BRANCH,
                "content": base64.b64encode(json.dumps(state, sort_keys=True).encode()).decode()}
        if self.sha:
            body["sha"] = self.sha
        result = self.api("PUT", "/contents/" + STATE_PATH, body)
        self.sha = result["content"]["sha"]

    def disable_workflow(self):
        self.api("PUT", "/actions/workflows/oracle-provision.yml/disable")

    def workflow_enabled(self):
        workflow = self.api("GET", "/actions/workflows/oracle-provision.yml")
        return workflow["state"] == "active"


def request_details(config, discovered, public_key):
    return {
        "availability_domain": discovered["ad"],
        "compartment_id": config["tenancy"],
        "display_name": NAME,
        "shape": SHAPE,
        "shape_config": {"ocpus": 1, "memory_in_gbs": 6},
        "source_details": {"source_type": "image", "image_id": discovered["image"],
                           "boot_volume_size_in_gbs": 50},
        "create_vnic_details": {"subnet_id": discovered["subnet"], "assign_public_ip": True},
        "metadata": {"ssh_authorized_keys": public_key.strip()},
        "is_pv_encryption_in_transit_enabled": True,
    }


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def find_existing(instances, state):
    matches = [v for v in instances if v["name"].rstrip(".") == NAME]
    if state:
        matches += [v for v in instances if v.get("request") == state["token"]
                    and v not in matches]
    if len(matches) > 1:
        raise Stop("Multiple matching instances exist; inspect Oracle before continuing.")
    return matches[0] if matches else None


def run_once(cloud, store, config, public_key, apply=False, now=None):
    now = time.time() if now is None else now
    state = store.load()
    if state and state.get("account") != fingerprint(config):
        raise Stop("Saved state belongs to different account settings.")
    # A saved accepted ID is a permanent stop on launches, even if deleted later.
    if state and state.get("instance_id"):
        observed = cloud.status(state["instance_id"])
        if apply:
            state["observed"] = observed["status"]
            store.save(state)
        return observed
    if state and state.get("blocked"):
        raise Stop("Saved request is blocked: " + state["blocked"])
    if state and now - state["campaign_started"] >= CAMPAIGN_SECONDS:
        return {"status": "CAMPAIGN_EXPIRED", "message": "72-hour campaign ended; no new launch."}

    discovered = cloud.discover(config)
    instances = cloud.inventory(config)
    existing = find_existing(instances, state)
    if existing:
        if existing["state"] in ("TERMINATED", "TERMINATING"):
            raise Stop("A matching terminated/terminating instance exists; manual review required.")
        if existing["shape"] != SHAPE:
            raise Stop("A matching instance has an unexpected shape.")
        if apply:
            state = state or {"account": fingerprint(config), "token": str(uuid.uuid4()),
                              "campaign_started": now}
            state["instance_id"] = existing["id"]
            store.save(state)
        return cloud.status(existing["id"])

    details = request_details(config, discovered, public_key)
    if not apply:
        return {"status": "CHECK_PASSED", "message": "Authentication, subnet, image, home region and resource budget verified. No launch requested."}

    if state is None:
        state = {"account": fingerprint(config), "token": str(uuid.uuid4()),
                 "created": now, "campaign_started": now, "details": details,
                 "safe_to_rotate": True, "throttles": 0, "next_allowed": 0}
        store.save(state)
    # Preserve the exact image and body throughout a request's retry window.
    old = state["details"]
    if (old["metadata"] != details["metadata"] or
            old["create_vnic_details"] != details["create_vnic_details"] or
            old["availability_domain"] != details["availability_domain"]):
        raise Stop("SSH key, subnet or availability domain changed during saved request.")
    if now < state.get("next_allowed", 0):
        return {"status": "BACKOFF", "message": "Cooling down after a prior API error; no launch."}
    if now - state["created"] >= TOKEN_SECONDS:
        if not state["safe_to_rotate"]:
            raise Stop("Old request outcome is uncertain. Do not reset state; inspect Oracle.")
        state.update(token=str(uuid.uuid4()), created=now, details=details)
    if state.get("attempts", 0) >= 864:
        raise Stop("Campaign attempt ceiling reached.")
    body = copy.deepcopy(state["details"])
    body["freeform_tags"] = {"vpn_retry_request": state["token"]}
    state["safe_to_rotate"] = False
    state["attempts"] = state.get("attempts", 0) + 1
    # This durable write MUST complete before Oracle sees a launch request.
    store.save(state)
    try:
        accepted = cloud.launch(body, state["token"])
    except Exception as error:
        status = getattr(error, "status", None)
        message = str(getattr(error, "message", "")).lower()
        capacity = status == 500 and "out of host capacity" in message
        if status == 429 or capacity:
            state["safe_to_rotate"] = True
            state["throttles"] = state["throttles"] + 1 if status == 429 else 0
            delay = min(1800, 300 * 2 ** min(state["throttles"], 3))
            state["next_allowed"] = now + delay
            store.save(state)
            return {"status": "THROTTLED" if status == 429 else "NO_CAPACITY",
                    "message": "No instance accepted. Next launch no sooner than %s seconds." % delay}
        if status is not None and 400 <= status < 500:
            state["blocked"] = "Oracle rejected the request (HTTP %s)." % status
            store.save(state)
            raise Stop(state["blocked"]) from None
        # Network timeouts, cancellation, generic 5xx: retain original token/body.
        # A later run inventories instances and replays ONLY that same request.
        store.save(state)
        raise Stop("Launch outcome uncertain; saved token retained. No new request identity.") from None
    state["instance_id"] = accepted["id"]
    store.save(state)
    return {"status": "ACCEPTED", "instance_id": accepted["id"],
            "message": "Launch accepted. Future runs only monitor this instance."}


class Oracle:
    def __init__(self, config, private_key):
        import oci
        self.oci = oci
        credentials = {**config, "key_content": private_key}
        oci.config.validate_config(credentials)
        self.compute = oci.core.ComputeClient(credentials, timeout=(10, 60))
        self.network = oci.core.VirtualNetworkClient(credentials, timeout=(10, 60))
        self.identity = oci.identity.IdentityClient(credentials, timeout=(10, 60))
        self.storage = oci.core.BlockstorageClient(credentials, timeout=(10, 60))
        self.all = oci.pagination.list_call_get_all_results

    def discover(self, config):
        if config["region"] != REGION:
            raise Stop("Only Singapore is allowed by this configuration.")
        subscriptions = self.identity.list_region_subscriptions(config["tenancy"]).data
        if not any(s.region_name == REGION and s.is_home_region for s in subscriptions):
            raise Stop("Singapore is not this tenancy's home region.")
        ads = self.identity.list_availability_domains(config["tenancy"]).data
        if len(ads) != 1:
            raise Stop("Expected exactly one Singapore availability domain.")
        subnets = self.all(self.network.list_subnets, compartment_id=config["tenancy"]).data
        matches = []
        for s in subnets:
            if s.display_name != "public subnet-vpn-vcn" or s.lifecycle_state != "AVAILABLE":
                continue
            if s.prohibit_public_ip_on_vnic is not False:
                continue
            vcn = self.network.get_vcn(s.vcn_id).data
            if vcn.display_name == "vpn-vcn":
                matches.append(s)
        if len(matches) != 1:
            raise Stop("Cannot identify exactly one public subnet in vpn-vcn.")
        route = self.network.get_route_table(matches[0].route_table_id).data
        gateways = [r.network_entity_id for r in route.route_rules
                    if r.destination == "0.0.0.0/0" and ".internetgateway." in r.network_entity_id]
        if not any(self.network.get_internet_gateway(g).data.is_enabled for g in gateways):
            raise Stop("Public subnet lacks an enabled default-route internet gateway.")
        images = self.all(self.compute.list_images, compartment_id=config["tenancy"], shape=SHAPE).data
        images = [i for i in images if i.lifecycle_state == "AVAILABLE"
                  and all(w in i.display_name.lower() for w in ("ubuntu", "24.04", "minimal", "aarch64"))]
        if not images:
            raise Stop("Compatible Ubuntu 24.04 Minimal ARM image not found.")
        return {"ad": ads[0].name, "subnet": matches[0].id,
                "image": max(images, key=lambda i: i.time_created).id}

    def inventory(self, config):
        root = config["tenancy"]
        compartments = self.all(self.identity.list_compartments, compartment_id=root,
                                compartment_id_in_subtree=True, access_level="ANY").data
        ids = [root] + [c.id for c in compartments if c.lifecycle_state == "ACTIVE"]
        ads = self.identity.list_availability_domains(root).data
        instances, volumes = [], []
        cpu = ram = 0
        for cid in ids:
            for v in self.all(self.compute.list_instances, compartment_id=cid).data:
                if v.lifecycle_state not in ("TERMINATED", "TERMINATING") and v.shape == SHAPE:
                    if v.shape_config is None:
                        raise Stop("Cannot determine existing A1 resource usage.")
                    cpu += v.shape_config.ocpus
                    ram += v.shape_config.memory_in_gbs
                if cid == root:
                    instances.append({"id": v.id, "name": v.display_name, "state": v.lifecycle_state,
                                      "shape": v.shape,
                                      "request": (v.freeform_tags or {}).get("vpn_retry_request")})
            volumes += self.all(self.storage.list_volumes, compartment_id=cid).data
            for ad in ads:
                volumes += self.all(self.storage.list_boot_volumes, compartment_id=cid,
                                    availability_domain=ad.name).data
        # Existing desired instances are adopted/monitored rather than counted twice.
        desired = any(v["name"].rstrip(".") == NAME for v in instances)
        if not desired and (cpu + 1 > 2 or ram + 6 > 12):
            raise Stop("Creating this VM would exceed the configured 2-OCPU / 12-GB A1 budget.")
        used = sum(v.size_in_gbs for v in volumes if v.lifecycle_state != "TERMINATED")
        if not desired and used + 50 > 200:
            raise Stop("Creating the boot disk would exceed the configured 200-GB volume budget.")
        return instances

    def launch(self, body, token):
        m = self.oci.core.models
        data = copy.deepcopy(body)
        data["shape_config"] = m.LaunchInstanceShapeConfigDetails(**data["shape_config"])
        data["source_details"] = m.InstanceSourceViaImageDetails(**data["source_details"])
        data["create_vnic_details"] = m.CreateVnicDetails(**data["create_vnic_details"])
        result = self.compute.launch_instance(m.LaunchInstanceDetails(**data), opc_retry_token=token,
                                            retry_strategy=self.oci.retry.NoneRetryStrategy())
        return {"id": result.data.id}

    def status(self, instance_id):
        instance = self.compute.get_instance(instance_id).data
        result = {"status": instance.lifecycle_state, "instance_id": instance_id}
        if instance.lifecycle_state == "RUNNING":
            attachments = self.all(self.compute.list_vnic_attachments,
                                   compartment_id=instance.compartment_id, instance_id=instance_id).data
            for a in attachments:
                if a.lifecycle_state == "ATTACHED":
                    ip = self.network.get_vnic(a.vnic_id).data.public_ip
                    if ip:
                        result["public_ip"] = ip
        return result


def report(outcome):
    print(json.dumps(outcome, sort_keys=True), flush=True)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Oracle Singapore provisioning\n\n")
            for key, value in outcome.items():
                f.write("- **%s:** %s\n" % (key, str(value).replace("\n", " ")))
            f.write("\nOnly RUNNING confirms a running VM. CHECK_PASSED creates nothing.\n")


def watch_worker(cloud, store, config, public_key, *, max_seconds=345 * 60,
                 clock=time.time, sleep=time.sleep, emit=report, progress=print):
    """Retry inside one bounded job; no cron or recursive workflow is required."""
    deadline = clock() + max_seconds
    cycle = 0
    retryable = {"NO_CAPACITY", "THROTTLED", "BACKOFF", "ACCEPTED",
                 "PROVISIONING", "STARTING"}
    while clock() < deadline:
        if not store.workflow_enabled():
            return {"status": "PAUSED", "message": "Workflow disabled; background retries stopped."}
        cycle += 1
        outcome = run_once(cloud, store, config, public_key, apply=True, now=clock())
        emit({**outcome, "worker_cycle": cycle})
        if outcome["status"] not in retryable:
            return outcome
        state = store.load()
        # Never relaunch after acceptance. Pending instances only need monitoring.
        if state.get("instance_id"):
            wake_at = clock() + 60
        else:
            wake_at = max(clock() + 1, state.get("next_allowed", clock() + 300))
        while clock() < min(wake_at, deadline):
            remaining = min(wake_at, deadline) - clock()
            progress("Heartbeat: background job active; next check in %d seconds." % remaining,
                     flush=True)
            sleep(min(60, remaining))
            if not store.workflow_enabled():
                return {"status": "PAUSED", "message": "Workflow disabled; background retries stopped."}
    return {"status": "WATCH_WINDOW_ENDED",
            "message": "Bounded background session finished. Saved state retained; manual restart required."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(__file__).with_name("settings.json").read_text())
    try:
        if args.watch and not args.apply:
            raise Stop("--watch requires --apply.")
        if args.apply and os.getenv("OCI_PROVISIONING_ENABLED") != "true":
            raise Stop("Enable OCI_PROVISIONING_ENABLED only after stopping the Termux retry process.")
        required = ("OCI_PRIVATE_KEY", "OCI_PUBLIC_SSH_KEY", "GH_STATE_TOKEN", "GITHUB_REPOSITORY", "OCI_DEFAULT_BRANCH")
        if any(not os.getenv(k, "").strip() for k in required):
            raise Stop("Required GitHub Secrets or workflow settings are missing.")
        public_key = os.environ["OCI_PUBLIC_SSH_KEY"].strip()
        if not public_key.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
            raise Stop("OCI_PUBLIC_SSH_KEY must contain an SSH public key, not an API key or private key.")
        store = GitHubState(os.environ["GITHUB_REPOSITORY"], os.environ["GH_STATE_TOKEN"],
                            os.environ["OCI_DEFAULT_BRANCH"])
        cloud = Oracle(config, os.environ["OCI_PRIVATE_KEY"])
        if args.watch:
            outcome = watch_worker(cloud, store, config, public_key)
        else:
            outcome = run_once(cloud, store, config, public_key, apply=args.apply)
        report(outcome)
        if args.apply and outcome["status"] in ("RUNNING", "CAMPAIGN_EXPIRED"):
            try:
                store.disable_workflow()
                print("Provisioning workflow disabled automatically.")
            except Stop:
                print("Auto-disable failed. Saved state still prevents new launches; disable this workflow manually.")
        # Capacity failures are explicit failures, never a green VM-success signal.
        return 0 if outcome["status"] in ("RUNNING", "CHECK_PASSED") else 75
    except Stop as error:
        report({"status": "STOPPED", "message": str(error)})
        return 2
    except Exception as error:
        # SDK exception reprs can contain authentication material. Log the type only.
        report({"status": "ERROR", "message": type(error).__name__ + "; inspect settings/Oracle. State retained."})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
