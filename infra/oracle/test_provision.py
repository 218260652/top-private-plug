import copy
import os
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import Mock

from provision import (CAMPAIGN_SECONDS, TOKEN_SECONDS, NAME, SHAPE, Oracle,
                       Stop, run_once, watch_worker)

CONFIG = {"tenancy": "test-tenancy", "region": "ap-singapore-1"}
KEY = "ssh-ed25519 AAAATEST test"


class Store:
    def __init__(self):
        self.state = None
        self.writes = 0
        self.enabled = True

    def workflow_enabled(self):
        return self.enabled

    def load(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.writes += 1
        self.state = copy.deepcopy(state)


class Cloud:
    def __init__(self):
        self.instances = []
        self.calls = []
        self.image = "image-1"
        self.error = None
        self.observed = "RUNNING"

    def discover(self, config):
        return {"ad": "singapore-ad-1", "subnet": "public-subnet", "image": self.image}

    def inventory(self, config):
        return self.instances

    def launch(self, body, token):
        self.calls.append((copy.deepcopy(body), token))
        if self.error:
            raise self.error
        return {"id": "instance-1"}

    def status(self, instance_id):
        return {"status": self.observed, "instance_id": instance_id}


def service_error(status, message):
    error = Exception("test")
    error.status, error.message = status, message
    return error


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.cloud, self.store = Cloud(), Store()

    def run_at(self, now=100, apply=True, key=KEY):
        return run_once(self.cloud, self.store, CONFIG, key, apply=apply, now=now)

    def capacity(self):
        self.cloud.error = service_error(500, "Out of host capacity.")
        return self.run_at()

    def test_check_never_launches_or_writes(self):
        self.assertEqual(self.run_at(apply=False)["status"], "CHECK_PASSED")
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(self.store.writes, 0)

    def test_acceptance_is_not_running_and_subsequent_runs_only_monitor(self):
        self.assertEqual(self.run_at()["status"], "ACCEPTED")
        self.cloud.observed = "PROVISIONING"
        self.assertEqual(self.run_at(500)["status"], "PROVISIONING")
        self.cloud.observed = "RUNNING"
        self.assertEqual(self.run_at(900)["status"], "RUNNING")
        self.assertEqual(len(self.cloud.calls), 1)

    def test_capacity_cools_down_and_pins_body_and_token(self):
        self.assertEqual(self.capacity()["status"], "NO_CAPACITY")
        first = self.cloud.calls[0]
        self.assertEqual(self.run_at(399)["status"], "BACKOFF")
        self.cloud.image = "new-image"
        self.run_at(400)
        self.assertEqual(self.cloud.calls[1], first)

    def test_throttle_exponential_cooldown(self):
        self.cloud.error = service_error(429, "Too many requests for the user")
        self.assertEqual(self.run_at()["status"], "THROTTLED")
        self.assertEqual(self.store.state["next_allowed"], 700)
        self.run_at(700)
        self.assertEqual(self.store.state["next_allowed"], 1900)
        self.run_at(1900)
        self.assertEqual(self.store.state["next_allowed"], 3700)

    def test_unknown_outcome_reuses_same_token(self):
        self.cloud.error = TimeoutError()
        with self.assertRaisesRegex(Stop, "uncertain"):
            self.run_at()
        first = self.cloud.calls[0]
        self.assertFalse(self.store.state["safe_to_rotate"])
        self.cloud.error = None
        self.run_at(500)
        self.assertEqual(first, self.cloud.calls[1])

    def test_uncertain_expired_token_never_rotates(self):
        self.cloud.error = TimeoutError()
        with self.assertRaises(Stop):
            self.run_at()
        with self.assertRaisesRegex(Stop, "uncertain"):
            self.run_at(100 + TOKEN_SECONDS)
        self.assertEqual(len(self.cloud.calls), 1)

    def test_definitive_capacity_failure_can_rotate_expired_token(self):
        self.capacity()
        first_token = self.cloud.calls[0][1]
        self.run_at(100 + TOKEN_SECONDS)
        self.assertNotEqual(first_token, self.cloud.calls[1][1])

    def test_campaign_stops_without_launch(self):
        self.capacity()
        self.assertEqual(self.run_at(100 + CAMPAIGN_SECONDS)["status"], "CAMPAIGN_EXPIRED")
        self.assertEqual(len(self.cloud.calls), 1)

    def test_adopts_phone_instance_with_trailing_period(self):
        self.cloud.instances = [{"name": NAME + ".", "id": "phone-instance",
                                 "state": "PROVISIONING", "shape": SHAPE}]
        self.assertEqual(self.run_at()["instance_id"], "phone-instance")
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(self.store.state["instance_id"], "phone-instance")

    def test_multiple_or_terminated_matches_stop(self):
        item = {"name": NAME, "id": "one", "state": "TERMINATED", "shape": SHAPE}
        self.cloud.instances = [item]
        with self.assertRaises(Stop):
            self.run_at()
        self.cloud.instances = [item, {**item, "id": "two"}]
        with self.assertRaises(Stop):
            self.run_at()
        self.assertEqual(self.cloud.calls, [])

    def test_state_write_failure_prevents_launch(self):
        self.store.save = Mock(side_effect=Stop("GitHub conflict"))
        with self.assertRaises(Stop):
            self.run_at()
        self.assertEqual(self.cloud.calls, [])

    def test_changed_key_stops_saved_request(self):
        self.capacity()
        with self.assertRaisesRegex(Stop, "changed"):
            self.run_at(500, key=KEY + " different")
        self.assertEqual(len(self.cloud.calls), 1)

    def test_non_capacity_500_is_uncertain_not_safe_to_rotate(self):
        self.cloud.error = service_error(500, "Internal server failure")
        with self.assertRaises(Stop):
            self.run_at()
        self.assertFalse(self.store.state["safe_to_rotate"])

    def test_unauthorized_request_permanently_blocks(self):
        self.cloud.error = service_error(401, "unauthorized")
        with self.assertRaises(Stop):
            self.run_at()
        with self.assertRaisesRegex(Stop, "blocked"):
            self.run_at(500)
        self.assertEqual(len(self.cloud.calls), 1)

    def test_persisted_accepted_id_never_relaunches_when_status_fails(self):
        self.run_at()
        self.cloud.status = Mock(side_effect=Exception("deleted or inaccessible"))
        with self.assertRaises(Exception):
            self.run_at(500)
        self.assertEqual(len(self.cloud.calls), 1)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.cloud, self.store = Cloud(), Store()
        self.now, self.events, self.sleeps = 100, [], []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def watch(self, seconds=1000, sleeper=None):
        return watch_worker(self.cloud, self.store, CONFIG, KEY, max_seconds=seconds,
                            clock=lambda: self.now, sleep=sleeper or self.sleep,
                            emit=self.events.append, progress=Mock())

    def test_capacity_retries_automatically_then_only_monitors_acceptance(self):
        original = self.cloud.launch

        def launch(body, token):
            if not self.cloud.calls:
                self.cloud.error = service_error(500, "Out of host capacity.")
            else:
                self.cloud.error = None
            return original(body, token)

        self.cloud.launch = launch
        result = self.watch()
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(len(self.cloud.calls), 2)
        self.assertEqual(self.cloud.calls[0], self.cloud.calls[1])
        self.assertGreaterEqual(sum(self.sleeps), 360)
        self.assertTrue(all(s <= 60 for s in self.sleeps))

    def test_worker_window_bounds_runtime(self):
        self.cloud.error = service_error(500, "Out of host capacity.")
        self.assertEqual(self.watch(650)["status"], "WATCH_WINDOW_ENDED")
        self.assertEqual(len(self.cloud.calls), 3)
        self.assertEqual(sum(self.sleeps), 650)

    def test_disabling_workflow_stops_during_cooldown(self):
        self.cloud.error = service_error(429, "throttled")

        def disable(seconds):
            self.sleep(seconds)
            self.store.enabled = False

        self.assertEqual(self.watch(sleeper=disable)["status"], "PAUSED")
        self.assertEqual(len(self.cloud.calls), 1)

    def test_unknown_launch_outcome_stops_worker(self):
        self.cloud.error = TimeoutError()
        with self.assertRaises(Stop):
            self.watch()
        self.assertEqual(len(self.cloud.calls), 1)
        self.assertEqual(self.sleeps, [])

    def test_existing_instance_never_launches_in_worker(self):
        self.cloud.instances = [{"name": NAME, "id": "existing", "state": "RUNNING",
                                 "shape": SHAPE}]
        self.assertEqual(self.watch()["status"], "RUNNING")
        self.assertEqual(self.cloud.calls, [])


class SDKContractTests(unittest.TestCase):
    def test_actual_oci_sdk_accepts_launch_models(self):
        try:
            import oci
        except ImportError:
            if os.getenv("GITHUB_ACTIONS") == "true":
                raise
            self.skipTest("Oracle SDK not installed locally; required in CI")
        cloud, store = Cloud(), Store()
        run_once(cloud, store, CONFIG, KEY, apply=True, now=100)
        body, token = cloud.calls[0]
        oracle = Oracle.__new__(Oracle)
        oracle.oci = oci
        oracle.compute = Mock()
        oracle.compute.launch_instance.return_value.data.id = "accepted"
        self.assertEqual(oracle.launch(body, token), {"id": "accepted"})
        args, kwargs = oracle.compute.launch_instance.call_args
        self.assertEqual(args[0].shape_config.ocpus, 1)
        self.assertEqual(args[0].source_details.boot_volume_size_in_gbs, 50)
        self.assertIsNone(args[0].fault_domain)
        self.assertEqual(kwargs["opc_retry_token"], token)


class InventoryBudgetTests(unittest.TestCase):
    def inventory(self, cpu=0, ram=0, storage=0):
        oracle = Oracle.__new__(Oracle)
        oracle.identity, oracle.compute, oracle.storage = Mock(), Mock(), Mock()
        oracle.identity.list_compartments.return_value = Obj(data=[])
        oracle.identity.list_availability_domains.return_value = Obj(data=[Obj(name="AD")])
        instances = [] if cpu == 0 else [Obj(
            id="other", display_name="unrelated", lifecycle_state="RUNNING", shape=SHAPE,
            shape_config=Obj(ocpus=cpu, memory_in_gbs=ram), freeform_tags={})]
        oracle.compute.list_instances.return_value = Obj(data=instances)
        oracle.storage.list_volumes.return_value = Obj(data=[])
        oracle.storage.list_boot_volumes.return_value = Obj(data=[
            Obj(size_in_gbs=storage, lifecycle_state="AVAILABLE")])
        oracle.all = lambda method, **kwargs: method(**kwargs)
        return oracle.inventory(CONFIG)

    def test_existing_one_ocpu_six_gb_permits_one_more(self):
        self.assertEqual(len(self.inventory(cpu=1, ram=6, storage=150)), 1)

    def test_cpu_and_memory_budget_fail_closed(self):
        with self.assertRaisesRegex(Stop, "A1 budget"):
            self.inventory(cpu=2, ram=6)
        with self.assertRaisesRegex(Stop, "A1 budget"):
            self.inventory(cpu=1, ram=12)

    def test_storage_budget_fail_closed(self):
        with self.assertRaisesRegex(Stop, "volume budget"):
            self.inventory(storage=151)


if __name__ == "__main__":
    unittest.main()
