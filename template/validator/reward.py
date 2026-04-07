# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 <your name>

import typing

import numpy as np
import bittensor as bt


def get_rewards(
    self,
    responses: typing.List[typing.Optional[str]],
) -> np.ndarray:
    """
    Nearly uniform random weights: base 1/n plus small jitter, then normalize.
    Miners with no video_url (None / empty) get 0.
    """
    n = len(responses)
    if n == 0:
        return np.array([], dtype=np.float32)

    valid = np.array(
        [r is not None and len(str(r).strip()) > 0 for r in responses],
        dtype=bool,
    )
    if not valid.any():
        bt.logging.warning("No valid miner video_url for reward.")
        return np.zeros(n, dtype=np.float32)

    rng = np.random.default_rng()
    w = np.ones(n, dtype=np.float64) / float(n)
    jitter = rng.uniform(-0.04, 0.04, size=n)
    w = w + jitter
    w = np.maximum(w, 1e-6)
    w[~valid] = 0.0
    s = float(w.sum())
    if s <= 0:
        return np.zeros(n, dtype=np.float32)
    return (w / s).astype(np.float32)
