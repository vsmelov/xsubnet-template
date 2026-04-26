#!/usr/bin/env python3
"""
Один запрос VLASynapse к майнеру по UID.

  docker compose ... run --rm -T --entrypoint python vla-miner scripts/query_miner.py \\
    --netuid 3 --wallet-name vla-val --miner-uid 1 \\
    --subtensor.chain_endpoint ws://subtensor-localnet:9944 \\
    --task-type CloseDrawer
"""

from __future__ import annotations

import argparse
import asyncio

import bittensor as bt

from template.protocol import VLASynapse


async def _run(args: argparse.Namespace) -> None:
    wallet = bt.Wallet(name=args.wallet_name, hotkey=args.hotkey, path=args.wallet_path)
    subtensor = bt.Subtensor(network=args.chain)
    mg = subtensor.metagraph(args.netuid)
    if args.miner_uid < 0 or args.miner_uid >= mg.n:
        raise SystemExit(f"miner-uid out of range 0..{mg.n - 1}")
    axon = mg.axons[args.miner_uid]
    dendrite = bt.Dendrite(wallet)
    synapse = VLASynapse(task_type=args.task_type, task=args.task_type)
    out = await dendrite(
        [axon], synapse=synapse, deserialize=True, timeout=args.timeout
    )
    print("axon:", axon)
    print("response:", out[0] if out else out)


def main() -> None:
    p = argparse.ArgumentParser(description="Single VLASynapse query to miner UID")
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument("--wallet-name", required=True)
    p.add_argument("--wallet-path", default="~/.bittensor")
    p.add_argument("--hotkey", default="default")
    p.add_argument(
        "--subtensor.chain_endpoint",
        dest="chain",
        default="ws://127.0.0.1:9944",
    )
    p.add_argument("--miner-uid", type=int, required=True)
    p.add_argument(
        "--task-type",
        default="CloseDrawer",
        help="One of ALLOWED_TASKS in template/protocol.py",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
