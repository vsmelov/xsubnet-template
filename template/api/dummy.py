import bittensor as bt
from typing import List, Union, Any
from template.protocol import VLASynapse
from bittensor.subnets import SubnetsAPI


class DummyAPI(SubnetsAPI):
    def __init__(self, wallet: "bt.wallet"):
        super().__init__(wallet)
        self.netuid = 33
        self.name = "dummy"

    def prepare_synapse(self, task: str) -> VLASynapse:
        return VLASynapse(task=task)

    def process_responses(
        self, responses: List[Union["bt.Synapse", Any]]
    ) -> List[str]:
        outputs = []
        for response in responses:
            if response.dendrite.status_code != 200:
                continue
            outputs.append(response.video_url)
        return outputs
