# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import time
import typing
import bittensor as bt

import template
from template.base.miner import BaseMinerNeuron
from template.protocol import (
    STUB_RESULT_VIDEO_URL,
    is_allowed_task,
    normalize_task,
)


class Miner(BaseMinerNeuron):
    """
    Stub miner: pretends to run a VLA; always returns the same demo video URL for allowed tasks.
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)

    async def forward(
        self, synapse: template.protocol.VLASynapse
    ) -> template.protocol.VLASynapse:
        task = normalize_task(synapse.task)
        if not is_allowed_task(task):
            synapse.video_url = None
            bt.logging.warning(f"Unsupported VLA task {synapse.task!r}")
            return synapse
        synapse.video_url = STUB_RESULT_VIDEO_URL
        bt.logging.info(f"VLA stub: task={task!r} -> {synapse.video_url}")
        return synapse

    async def blacklist(
        self, synapse: template.protocol.VLASynapse
    ) -> typing.Tuple[bool, str]:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return True, "Missing dendrite or hotkey"

        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        if self.config.blacklist.force_validator_permit:
            if not self.metagraph.validator_permit[uid]:
                bt.logging.warning(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"

        bt.logging.trace(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, "Hotkey recognized!"

    async def priority(self, synapse: template.protocol.VLASynapse) -> float:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return 0.0

        caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        priority = float(self.metagraph.S[caller_uid])
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}"
        )
        return priority


if __name__ == "__main__":
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)
