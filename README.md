# Konnex Drone Navigation Subnet

Konnex drone-navigation runtime package with:
- `subnet-miner`
- `subnet-validator`
- UnrealEngine sidecar (`openfly-ue`)
- one-shot assets bootstrap (`assets-init`)

## Environment (set this first)

Create `.env` from the template (this file is **only for this repo**; it does not replace `.env` in the parent `drone-navigation` tree):

```bash
cd xsubnet-template
cp .env.example .env
```

**Everyone must set (chain + identities):**
- `SUBTENSOR_CHAIN_ENDPOINT` — WebSocket RPC (e.g. `ws://127.0.0.1:9944` for localnet).
- `NETUID` — subnet id you are registered on.
- `MINER_WALLET_NAME`, `MINER_WALLET_HOTKEY`, `MINER_AXON_PORT` — miner axon identity.
- `VALIDATOR_WALLET_NAME`, `VALIDATOR_WALLET_HOTKEY`, `VALIDATOR_AXON_PORT` — validator axon identity.

**Wallets (project-local, no JSON paths in `.env`):** `MINER_*` / `VALIDATOR_*` are the **coldkey name** and **hotkey name** from `btcli` (e.g. `btcli wallet new_coldkey --wallet.name miner`). The SDK loads `coldkey` / `hotkeys/` files from a wallet **tree** on disk; you only pass those logical names in `.env`, not paths to `keyfile.json`.

This template keeps keys next to the repo under **`./wallets/`** (listed in **`.gitignore`** — never commit it). Docker Compose bind-mounts **`./wallets` → `/root/.bittensor/wallets`** inside miner and validator containers. Create/populate that directory on the host first, for example:

```bash
cd xsubnet-template
mkdir -p wallets
export BT_WALLET_PATH="$(pwd)/wallets"
btcli wallet new_coldkey --wallet.name miner
# …repeat for validator, or copy an existing tree: rsync -a ~/.bittensor/wallets/<name>/ ./wallets/<name>/
```

For **host-run** `python neurons/…` or **`offchain_validator_smoke.py`**, set the same `BT_WALLET_PATH` (or symlink `./wallets` to your usual location) so the SDK sees the same files as Docker.

**Security (same as any bind mount):** keys under `./wallets` are visible to any code in the container with that mount; treat `./wallets` like a **secret directory** on disk. For **mainnet / serious stake**, prefer a **hotkey-only** host, **coldkey offline**, separate keys for labs vs production, trusted images, and optionally a **read-only** mount (`:ro`) in a compose override if signing still works.

**HF / assets (when you use auto-download):**
- `HF_TOKEN` — **required** if Hugging Face assets are gated (UE zip / weights). Same role as `HUGGINGFACE_HUB_TOKEN`.
- `OPENFLY_ASSET_AUTO_DOWNLOAD` — `1` (default): `assets-init` downloads model + UE before UE starts; `0`: you place `models/` and `OpenFly-Platform/envs/ue/...` yourself.
- `OPENFLY_UE_ARCHIVE_URL` — optional; if set, UE is taken from this URL instead of the HF dataset.
- `OPENFLY_UE_DATASET_REPO`, `OPENFLY_UE_DATASET_SUBDIR` — only matter when `OPENFLY_UE_ARCHIVE_URL` is empty; defaults match OpenFly_DataGen layout.

**Miner policy (`neurons/miner.py`):**
- `OPENFLY_SUBNET_MINER_MODEL` — `openai` (default) or `openfly`.
  - **`openai`** — three sampled Chat Completions “competition” winners (same temperatures as before). Set **`OPENAI_API_TOKEN`** in `.env`. Without it the miner falls back to a small heuristic.
  - **`openfly`** — one call to your **OpenFly / VLM HTTP service** (the slim miner image has no PyTorch). Set `OPENFLY_SUBNET_MINER_OPENFLY_URL` to a POST endpoint. JSON body: `instruction`, `synthetic_context_json`, `frame_jpeg_b64` (strings; empty string if absent). JSON response: `action_id` (int), optional `confidence`, `explain`; you may wrap the object in `{ "result": { ... } }`. Optional: `OPENFLY_SUBNET_MINER_OPENFLY_TIMEOUT` (seconds, default 120). If the URL is empty, the miner uses the same heuristic as a stub until you configure the sidecar.
- When `OPENFLY_SUBNET_MINER_MODEL=openai`: optional `OPENAI_API_BASE`, `OPENFLY_SUBNET_MINER_OPENAI_MODEL` / `OPENAI_GPT_POLICY_MODEL`.

**Validator note:** the stock validator `forward` in this template does **not** call OpenAI or the OpenFly HTTP policy; only the miner does today.

## Quick Start

```bash
cd xsubnet-template
mkdir -p wallets logs/openfly-compose-tmp logs/ue-dashboard logs
chmod 1777 logs/openfly-compose-tmp
git submodule update --init --recursive
```

Start miner:

```bash
docker compose -f docker-compose.miner.yml up -d --build
```

Start validator + UE:

```bash
docker compose -f docker-compose.validator.yml up -d --build
```

Check status:

```bash
docker compose -f docker-compose.validator.yml logs assets-init --tail 120
docker compose -f docker-compose.validator.yml logs openfly-ue --tail 120
docker compose -f docker-compose.validator.yml logs subnet-validator --tail 120
docker compose -f docker-compose.miner.yml logs subnet-miner --tail 120
```

## Offchain smoke (validator → miners, no weights)

This is **not** a separate chain mode: the script uses your **normal** subtensor RPC and metagraph, sends the same kind of `DroneNavSynapse` a validator would send, and prints rewards — **without** `set_weights` or running the full validator neuron.

**Prerequisites:** subtensor reachable; **miner** registered on `NETUID`, axon serving (e.g. `docker compose -f docker-compose.miner.yml`); **validator** cold/hotkey exists on disk (`--wallet-name` / `--wallet-hotkey` are those **names**, same as in `.env`). Miner UID(s) must exist on the metagraph (`btcli subnet list` / wallet overview).

From the repo host (needs local `bittensor` + this package on `PYTHONPATH`; or run inside a dev container with the same deps):

```bash
cd xsubnet-template
export BT_WALLET_PATH="$(pwd)/wallets"
PYTHONPATH=. python scripts/offchain_validator_smoke.py \
  --netuid 1 --miner-uids 0 --rounds 1 --timeout 30 \
  --wallet-name validator --wallet-hotkey default \
  --subtensor.chain_endpoint ws://127.0.0.1:9944
```

Useful flags: `--rounds`, `--sleep`, `--instruction "..."`, `--tag-offchain` (marks `synthetic_context_json` for miners that log it). `OPENAI_API_TOKEN` belongs in the **miner** `.env` / environment if you use `OPENFLY_SUBNET_MINER_MODEL=openai`; the smoke script host does not need it.

## Onchain Runtime

After wallet/hotkey registration on your target network:

```bash
docker compose -f docker-compose.miner.yml up -d --build
docker compose -f docker-compose.validator.yml up -d --build
```

## Reset OpenFly Submodule

```bash
cd xsubnet-template
git submodule deinit -f OpenFly-Platform
rm -rf OpenFly-Platform
git submodule update --init --recursive OpenFly-Platform
```
