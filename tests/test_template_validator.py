# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 Opentensor Foundation

import unittest

import numpy as np

from template.protocol import ALLOWED_TASKS, VLASynapse, normalize_task_type
from template.validator.reward import get_rewards


class TemplateValidatorNeuronTestCase(unittest.TestCase):
    def test_normalize_task_type_accepts_primary_field(self):
        self.assertEqual(normalize_task_type("CloseDrawer"), "CloseDrawer")

    def test_deserialize_prefers_video_reference(self):
        synapse = VLASynapse(task_type="CloseDrawer", episode_video_ref="https://example/video.mp4")
        self.assertEqual(synapse.deserialize(), "https://example/video.mp4")

    def test_reward_prefers_explicit_scores(self):
        responses = [
            VLASynapse(task_type="CloseDrawer", score=0.8, video_url="https://example/a.mp4"),
            VLASynapse(task_type="CloseDrawer", score=0.2, video_url="https://example/b.mp4"),
        ]
        rewards = get_rewards(None, responses=responses)
        self.assertAlmostEqual(float(rewards[0]), 0.8, places=5)
        self.assertAlmostEqual(float(rewards[1]), 0.2, places=5)

    def test_reward_falls_back_to_artifact_presence(self):
        responses = [
            VLASynapse(task_type=ALLOWED_TASKS[0], video_url="https://example/a.mp4"),
            VLASynapse(task_type=ALLOWED_TASKS[1], video_url="https://example/b.mp4"),
        ]
        rewards = get_rewards(None, responses=responses)
        self.assertAlmostEqual(float(np.sum(rewards)), 1.0, places=5)
        self.assertTrue(np.all(rewards > 0))

    def test_reward_all_none(self):
        rewards = get_rewards(None, responses=[VLASynapse(), VLASynapse()])
        self.assertEqual(float(np.sum(rewards)), 0.0)
