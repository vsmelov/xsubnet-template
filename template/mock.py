import time
import asyncio
import random
import bittensor as bt
from typing import List

from template.protocol import STUB_RESULT_VIDEO_URL, normalize_task, normalize_task_type


class MockWallet:
    def __init__(self, config=None):
        self.hotkey = bt.Keypair.create_from_uri("//subnet-vla-mock-hotkey")
        self.coldkey = bt.Keypair.create_from_uri("//subnet-vla-mock-coldkey")

    def __str__(self) -> str:
        return f"MockWallet({self.hotkey.ss58_address})"


class MockSubtensor(bt.MockSubtensor):
    def __init__(self, netuid, n=16, wallet=None, network="mock"):
        super().__init__(network=network)

        # SDK 9.7 MockSubtensor.subnet_exists() can return a truthy query wrapper
        # before the in-memory NetworksAdded map is initialized for this netuid.
        if netuid not in self.chain_state["SubtensorModule"]["NetworksAdded"]:
            self.create_subnet(netuid)

        if wallet is not None:
            self.force_register_neuron(
                netuid=netuid,
                hotkey=wallet.hotkey.ss58_address,
                coldkey=wallet.coldkey.ss58_address,
                balance=100000,
                stake=100000,
            )

        for i in range(1, n + 1):
            self.force_register_neuron(
                netuid=netuid,
                hotkey=f"miner-hotkey-{i}",
                coldkey="mock-coldkey",
                balance=100000,
                stake=100000,
            )


class MockMetagraph(bt.Metagraph):
    def __init__(self, netuid=1, network="mock", subtensor=None):
        super().__init__(netuid=netuid, network=network, sync=False)

        if subtensor is not None:
            self.subtensor = subtensor
        self.sync(subtensor=subtensor)

        for axon in self.axons:
            axon.ip = "127.0.0.0"
            axon.port = 8091

        bt.logging.info(f"Metagraph: {self}")
        bt.logging.info(f"Axons: {self.axons}")


class MockDendrite(bt.Dendrite):
    def __init__(self, wallet):
        super().__init__(wallet)

    async def forward(
        self,
        axons: List[bt.Axon],
        synapse: bt.Synapse = bt.Synapse(),
        timeout: float = 12,
        deserialize: bool = True,
        run_async: bool = True,
        streaming: bool = False,
    ):
        if streaming:
            raise NotImplementedError("Streaming not implemented yet.")

        async def query_all_axons(streaming: bool):
            async def single_axon_response(i, axon):
                start_time = time.time()
                s = synapse.copy()
                s = self.preprocess_synapse_for_request(axon, s, timeout)
                process_time = random.random()
                if process_time < timeout:
                    s.dendrite.process_time = str(time.time() - start_time)
                    task = normalize_task(getattr(s, "task", None))
                    task_type = normalize_task_type(getattr(s, "task_type", None), task)
                    if task_type:
                        s.video_url = STUB_RESULT_VIDEO_URL
                        s.episode_video_ref = STUB_RESULT_VIDEO_URL
                        s.artifact_manifest = {
                            "artifact_id": f"kitchen-mock-{i}",
                            "artifact_type": "episode_video",
                            "public_url": STUB_RESULT_VIDEO_URL,
                            "metadata": {"task_type": task_type},
                        }
                    else:
                        s.video_url = None
                        s.episode_video_ref = None
                        s.artifact_manifest = None
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                    synapse.dendrite.process_time = str(process_time)
                else:
                    s.video_url = None
                    s.episode_video_ref = None
                    s.artifact_manifest = None
                    s.dendrite.status_code = 408
                    s.dendrite.status_message = "Timeout"
                    synapse.dendrite.process_time = str(timeout)

                if deserialize:
                    return s.deserialize()
                return s

            return await asyncio.gather(
                *(
                    single_axon_response(i, target_axon)
                    for i, target_axon in enumerate(axons)
                )
            )

        return await query_all_axons(streaming)

    def __str__(self) -> str:
        return "MockDendrite({})".format(self.keypair.ss58_address)
