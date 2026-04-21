# Drone Navigation Assets Setup (Weights + UE)

This subnet repository intentionally does **not** store heavy runtime assets in git.
Use this guide to prepare the required local assets for miner/validator execution.
For validator stack, `docker-compose.validator.yml` now includes `assets-init` auto-bootstrap service.

## Required runtime assets

1. OpenFly model weights directory:
   - expected path: `models/openfly-agent-7b`
   - override via env: `OPENFLY_MODEL`

2. Unreal Engine City Sample environment:
   - expected path inside OpenFly repo: `OpenFly-Platform/envs/ue/env_ue_smallcity/`
   - must contain:
     - `CitySample.sh`
     - `City_UE52/Binaries/Linux/CitySample`
     - `City_UE52/Binaries/Linux/unrealcv.ini`

## Repository layout in this migration branch

- `xsubnet-template/` is the subnet root.
- `xsubnet-template/OpenFly-Platform/` is a nested git submodule (source + UE runner code).
- Runtime assets (weights, built UE env) should be mounted/linked on host and ignored by git.

## Bootstrap steps

From `xsubnet-template` root:

```bash
git submodule update --init --recursive
```

Then inside nested OpenFly submodule:

```bash
cd OpenFly-Platform
# fetch/update model-independent code
git checkout main
git pull --ff-only
```

## Auto-download mode (validator compose)

`docker-compose.validator.yml` can bootstrap missing assets automatically:

- model from HF repo `IPEC-COMMUNITY/openfly-agent-7b` into `./models/openfly-agent-7b`
- UE env from:
  - `OPENFLY_UE_ARCHIVE_URL` (if set), or
  - dataset fallback `IPEC-COMMUNITY/OpenFly_DataGen` + `OPENFLY_UE_DATASET_SUBDIR=ue/env_ue_smallcity`

Control flags in `.env`:

- `OPENFLY_ASSET_AUTO_DOWNLOAD=1|0`
- `OPENFLY_MODEL_REPO`
- `OPENFLY_UE_ARCHIVE_URL`
- `OPENFLY_UE_DATASET_REPO`
- `OPENFLY_UE_DATASET_SUBDIR`
- `HF_TOKEN` (for private/gated assets)

## Where to fetch binaries from

- Model weights (`openfly-agent-7b`) and built UE env (`env_ue_smallcity`) are distributed outside git
  (internal artifact storage / team package mirror).
- Keep an operator-facing pointer in deployment env docs (Terraform/Ansible/compose env file) so machine bootstrap is reproducible.

## Validation checks

Run these checks on each machine:

```bash
test -d models/openfly-agent-7b
test -f OpenFly-Platform/envs/ue/env_ue_smallcity/CitySample.sh
test -f OpenFly-Platform/envs/ue/env_ue_smallcity/City_UE52/Binaries/Linux/CitySample
test -f OpenFly-Platform/envs/ue/env_ue_smallcity/City_UE52/Binaries/Linux/unrealcv.ini
```

If any check fails, miner runtime will start but cannot produce real navigation rollouts.
