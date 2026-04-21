#!/usr/bin/env python3
"""
Single DroneNavSynapse query to miner UID.
"""

from __future__ import annotations

import argparse
import asyncio

import bittensor as bt

from template.protocol import DroneNavSynapse


async def _run(args: argparse.Namespace) -> None:
    wallet = bt.Wallet(name=args.wallet_name, hotkey=args.hotkey)
    subtensor = bt.Subtensor(network=args.chain)
    mg = subtensor.metagraph(args.netuid)
    if args.miner_uid < 0 or args.miner_uid >= mg.n:
        raise SystemExit(f"miner-uid out of range 0..{mg.n - 1}")
    axon = mg.axons[args.miner_uid]
    dendrite = bt.Dendrite(wallet)
    synapse = DroneNavSynapse(
        instruction=args.instruction,
        task_id=args.task_id,
    )
    out = await dendrite(
        [axon], synapse=synapse, deserialize=False, timeout=args.timeout
    )
    print("axon:", axon)
    if out:
        item = out[0]
        print("action_id:", getattr(item, "action_id", None))
        print("confidence:", getattr(item, "confidence", None))
        print("miner_error:", getattr(item, "miner_error", None))
        print("response_json:", getattr(item, "miner_response_json", None))
    else:
        print("response:", out)


def main() -> None:
    p = argparse.ArgumentParser(description="Single DroneNavSynapse query to miner UID")
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument("--wallet-name", required=True, help="Coldkey name (must be registered)")
    p.add_argument("--hotkey", default="default")
    p.add_argument(
        "--subtensor.chain_endpoint",
        dest="chain",
        default="ws://127.0.0.1:9944",
        help="Inside Docker use ws://subtensor-localnet:9944",
    )
    p.add_argument("--miner-uid", type=int, required=True)
    p.add_argument(
        "--instruction",
        default="Proceed toward the most salient building ahead.",
    )
    p.add_argument("--task-id", default="manual-query")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
