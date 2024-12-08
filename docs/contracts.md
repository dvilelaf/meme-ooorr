> :warning: **Warning** <br />
> All commands are assumed to be run from root!

# Contract Development

## Prerequisites
- This repository follows the standard [`Hardhat`](https://hardhat.org/tutorial/) development process.
- The code is written on Solidity starting from version `0.8.28`.
- The standard versions of Node.js along with Yarn are required to proceed further (confirmed to work with Yarn `1.22.19`, npx/npm `10.9.0` and node `v20.14.0`).

## Install the dependencies
The project has submodules to get the dependencies. Make sure you run `git clone --recursive` or init the submodules yourself.
The dependency list is managed by the `package.json` file, and the setup parameters are stored in the `hardhat.config.js` file.
Simply run the following command to install the project:
```
yarn install
```

## Core components
The contracts, packages, scripts and tests are located in the following folders respectively:
```
contracts
packages
scripts
test
```

## Compile the code and run
Compile the code:
```
npx hardhat compile
```
Run the tests:
```
npx hardhat test
```

### Test on branch

First, install test setup

```bash
curl -L https://foundry.paradigm.xyz | bash
```

Run forked test chain
```bash
export ANVIL_IP_ADDR=0.0.0.0
anvil --fork-url https://soft-sly-slug.base-mainnet.quiknode.pro/f13d998d9d68685faeee903499e15b4b386a8b1c/ --port 9000 --chain-id 8543 --no-storage-caching --steps-tracing
```

Copy configs

```bash
cp scripts/deployment/globals_base_mainnet.json globals.json
```

On separate terminal run test
```bash
npx hardhat run test/MemeBase.js --network localFork
```

# Acknowledgements
The registries contracts were inspired and based on the following sources:
- [Rari-Capital](https://github.com/Rari-Capital/solmate). Last known audited version: `eaa7041378f9a6c12f943de08a6c41b31a9870fc`;