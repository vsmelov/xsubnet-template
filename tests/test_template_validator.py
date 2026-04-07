# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 Opentensor Foundation

import sys
import unittest

import bittensor as bt
import numpy as np

from neurons.validator import Validator
from template.base.validator import BaseValidatorNeuron
from template.protocol import ALLOWED_TASKS, VLASynapse
from template.utils.uids import get_random_uids
from template.validator.reward import get_rewards


class TemplateValidatorNeuronTestCase(unittest.TestCase):
    def setUp(self):
        sys.argv = sys.argv[0] + ["--config", "tests/configs/validator.json"]

        config = BaseValidatorNeuron.config()
        config.wallet._mock = True
        config.metagraph._mock = True
        config.subtensor._mock = True
        self.neuron = Validator(config)
        self.miner_uids = get_random_uids(self, k=10)

    def test_run_single_step(self):
        pass

    def test_sync_error_if_not_registered(self):
        pass

    def test_forward(self):
        pass

    def test_dummy_responses(self):
        synapse = VLASynapse(task=ALLOWED_TASKS[0])
        responses = self.neuron.dendrite.query(
            axons=[
                self.neuron.metagraph.axons[uid] for uid in self.miner_uids
            ],
            synapse=synapse,
            deserialize=True,
        )
        for response in responses:
            self.assertIsInstance(response, str)
            self.assertTrue(len(response) > 0)

    def test_reward(self):
        synapse = VLASynapse(task="Clean-up the kitchen")
        responses = self.neuron.dendrite.query(
            axons=[
                self.neuron.metagraph.axons[uid] for uid in self.miner_uids
            ],
            synapse=synapse,
            deserialize=True,
        )
        str_r = [r if r else None for r in responses]
        rewards = get_rewards(self.neuron, responses=str_r)
        self.assertAlmostEqual(float(np.sum(rewards)), 1.0, places=5)
        self.assertTrue(np.all(rewards >= 0))

    def test_reward_all_none(self):
        rewards = get_rewards(self.neuron, responses=[None, None, None])
        self.assertEqual(float(np.sum(rewards)), 0.0)
