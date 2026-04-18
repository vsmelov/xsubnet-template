# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import json
import random
import time
import bittensor as bt

from template.protocol import ALLOWED_TASKS, VLASynapse
from template.validator.reward import get_rewards
from template.utils.uids import get_random_uids


async def forward(self):
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    task = random.choice(ALLOWED_TASKS)
    synapse = VLASynapse(task=task)

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=synapse,
        deserialize=True,
    )

    str_responses: list = []
    for r in responses:
        if r is None:
            str_responses.append(None)
        else:
            str_responses.append(str(r).strip() if str(r).strip() else None)

    bt.logging.info(f"VLA task {task!r}, responses: {str_responses}")

    rewards = get_rewards(self, responses=str_responses)

    scoreboard = {
        "task": task,
        "uids": [int(u) for u in miner_uids],
        "video_urls": str_responses,
        "rewards": [float(x) for x in rewards.tolist()],
    }
    bt.logging.info("VLA_SCOREBOARD " + json.dumps(scoreboard))

    self.update_scores(rewards, miner_uids)
    time.sleep(float(self.config.neuron.forward_sleep))
