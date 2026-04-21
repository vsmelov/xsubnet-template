#!/usr/bin/env python3
"""
Offchain smoke: same synthetic DroneNavSynapse as the validator, dendrite query to chosen miner UIDs — no set_weights, no axon.

Use after localnet / compose bring-up to verify validator wallet can reach miner axons.

Examples::

  cd xsubnet-template && PYTHONPATH=. python scripts/offchain_validator_smoke.py \\
    --netuid 1 --miner-uids 0 --rounds 3 --sleep 2 \\
    --wallet-name validator --wallet-hotkey default \\
    --subtensor.chain_endpoint ws://127.0.0.1:9944

Frequency of real validator synthetic rounds is ``--neuron.forward_sleep`` (default 3600s), not this script.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Repo root = parent of scripts/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def _run(args: argparse.Namespace) -> int:
    import bittensor as bt

    from template.validator.reward import get_rewards
    from template.validator.synthetic_context import (
        build_synthetic_drone_nav_synapse,
        mark_synapse_offchain_smoke,
    )

    wallet = bt.Wallet(name=args.wallet_name, hotkey=args.wallet_hotkey)
    subtensor = bt.Subtensor(network=args.chain)
    mg = subtensor.metagraph(args.netuid)
    dendrite = bt.Dendrite(wallet=wallet)

    uids = [int(x) for x in args.miner_uids]
    for u in uids:
        if u < 0 or u >= mg.n:
            print(f"error: miner uid {u} out of range 0..{mg.n - 1}", file=sys.stderr)
            return 2

    failures = 0
    for r in range(int(args.rounds)):
        synapse, synthetic_context = build_synthetic_drone_nav_synapse(
            validator_step=r,
            instruction=args.instruction or None,
            task_id=args.task_id if args.task_id else None,
        )
        if args.tag_offchain:
            mark_synapse_offchain_smoke(synapse)
            synthetic_context = json.loads(synapse.synthetic_context_json or "{}")

        instruction = str(synapse.instruction)
        axons = [mg.axons[u] for u in uids]
        print(
            f"\n--- smoke round {r + 1}/{args.rounds} task_id={synapse.task_id!r} "
            f"instruction={instruction[:120]!r} uids={uids} ---"
        )
        responses = await dendrite(
            axons=axons,
            synapse=synapse,
            deserialize=False,
            timeout=float(args.timeout),
        )

        class _FakeValidator:
            config = None

        fake = _FakeValidator()
        rewards, details = get_rewards(fake, instruction=instruction, responses=responses)

        for i, uid in enumerate(uids):
            resp = responses[i] if i < len(responses) else None
            err = getattr(resp, "miner_error", None) if resp is not None else "no_response"
            aid = getattr(resp, "action_id", None) if resp is not None else None
            conf = getattr(resp, "confidence", None) if resp is not None else None
            line = f"uid={uid} action_id={aid} confidence={conf} miner_error={err!r}"
            print(line)
            if err:
                failures += 1
            elif aid is None:
                failures += 1

        print("rewards:", rewards.tolist())
        print("verification:", json.dumps(details, ensure_ascii=False, default=str)[:2000])

        if r + 1 < int(args.rounds) and float(args.sleep) > 0:
            await asyncio.sleep(float(args.sleep))

    print(f"\noffchain_smoke: done rounds={args.rounds} failures={failures}")
    return 1 if failures else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netuid", type=int, required=True)
    p.add_argument("--wallet-name", required=True)
    p.add_argument("--wallet-hotkey", default="default")
    p.add_argument(
        "--subtensor.chain_endpoint",
        dest="chain",
        default="ws://127.0.0.1:9944",
    )
    p.add_argument(
        "--miner-uids",
        type=int,
        nargs="+",
        required=True,
        help="One or more miner UIDs to query (same dendrite batch as validator).",
    )
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--sleep", type=float, default=0.0, help="Pause between rounds (seconds).")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--instruction", default="", help="Override instruction (default: random synthetic).")
    p.add_argument("--task-id", default="", help="Override task id (default: auto).")
    p.add_argument(
        "--tag-offchain",
        action="store_true",
        help="Set synthetic_context_json.offchain_smoke=true for miners that inspect context.",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
