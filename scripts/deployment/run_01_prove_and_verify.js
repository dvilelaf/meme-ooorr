/*global process*/

const { keccak256 } = require('@ethersproject/keccak256');
const { ethers } = require("hardhat");
const { LedgerSigner } = require("@anders-t/ethers-ledger");

const l2ToL1MessagePasserAbi = require('./../../abi/l2ToL1MessagePasser.json');
const l2OuputOracleAbi = require('./../../abi/l2OutputOracle.json');
const optimismPortalAbi = require('./../../abi/optimismPortal.json');

/// https://docs.base.org/docs/base-contracts/
const l2ToL1MessagePasser = '0x4200000000000000000000000000000000000016';
const disputeGameFactory = '0xd6E6dBf4F7EA0ac412fD8b65ED297e64BB7a06E1';
const l2OutputOracle = '0x56315b90c40730925ec5485cf004d835058518A0';
const optimismPortal = '0x49048044D57e1C92A77f79988d21Fa8fAF74E97e';

const getPortalContract = (signer) => {
  const portalContract = new ethers.Contract(
    optimismPortal,
    optimismPortalAbi,
    signer,
  );
  return portalContract;
};

const getOracleContract = (signer) => {
  const oracleContract = new ethers.Contract(
    l2OutputOracle,
    l2OuputOracleAbi,
    signer,
  );
  return oracleContract;
};

const getMessageContract = (signer) => {
  const messageContract = new ethers.Contract(
    l2ToL1MessagePasser,
    l2ToL1MessagePasserAbi,
    signer,
  );
  return messageContract;
};

const getWithdrawalMessage = async (messageContract, withdrawal, isToken) => {
  let messageLog = withdrawal.logs.find((log) => {
    if (log.address === l2ToL1MessagePasser) {
      const parsed = messageContract.interface.parseLog(log);
      console.log('parsed', parsed);
      return parsed.name === 'MessagePassed';
    }
    return false;
  });
  console.log('messageLog', messageLog);

  if (!messageLog) {
    messageLog = withdrawal.logs[0];
  }
  const parsedLog = messageContract.interface.parseLog(messageLog);

  const withdrawalMessage = {
    nonce: parsedLog.args.nonce,
    sender: parsedLog.args.sender,
    target: parsedLog.args.target,
    value: parsedLog.args.value,
    gasLimit: parsedLog.args.gasLimit,
    data: parsedLog.args.data,
  };
  console.log('withdrawalMessage', withdrawalMessage);
  return withdrawalMessage;
};

const hashWithdrawal = (withdrawalMessage) => {
  const types = [
    'uint256',
    'address',
    'address',
    'uint256',
    'uint256',
    'bytes',
  ];
  const encoded = defaultAbiCoder.encode(types, [
    withdrawalMessage.nonce,
    withdrawalMessage.sender,
    withdrawalMessage.target,
    withdrawalMessage.value,
    withdrawalMessage.gasLimit,
    withdrawalMessage.data,
  ]);
  return keccak256(encoded);
};

const makeStateTrieProof = async (provider, blockNumber, address, slot) => {
  const proof = await provider.send('eth_getProof', [
    address,
    [slot],
    blockNumber,
  ]);

  return {
    accountProof: proof.accountProof,
    storageProof: proof.storageProof[0].proof,
    storageValue: BigInt(proof.storageProof[0].value),
    storageRoot: proof.storageHash,
  };
};

async function main() {
    const fs = require("fs");
    const globalsFile = "globals.json";
    let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    let parsedData = JSON.parse(dataFromJSON);
    const useLedger = parsedData.useLedger;
    const derivationPath = parsedData.derivationPath;
    const providerName = parsedData.providerName;
    const tx = parsedData.tx;

    let networkURL = parsedData.networkURL;
    const provider = new ethers.providers.JsonRpcProvider(networkURL);
    const signers = await ethers.getSigners();

    let EOA;
    if (useLedger) {
        EOA = new LedgerSigner(provider, derivationPath);
    } else {
        EOA = signers[0];
    }
    // EOA address
    const address = await EOA.getAddress();
    console.log("EOA is:", address);

    const signer = EOA;

    const l1Signer = EOA;

    const oracleContract = getOracleContract(l1Signer);

    const messageContract = getMessageContract(signer);

    const portalContract = getPortalContract(l1Signer);

    const withdrawal = await signer.provider.getTransactionReceipt(tx);
    console.log('withdrawal receipt', withdrawal.blockNumber, withdrawal);

    // OK we fail here, because l2OutputOracle is no longer in use
    // it's been replaced by disputeGameFactoryProxy (https://etherscan.io/address/0x43edB88C4B80fDD2AdFF2412A7BebF9dF42cB40e)
    // https://docs.base.org/docs/base-contracts/
    // https://www.onesafe.io/blog/base-fault-proofs-crypto-security-banking-protocols#:~:text=Base%2C%20the%20Ethereum%20Layer%202,more%20secure%20and%20decentralized%20network.
    // no idea how the logic then continues from here ...
    const l2OutputIdx = await oracleContract.getL2OutputIndexAfter(
      withdrawal.blockNumber,
    );
    console.log('l2OutputIdx', l2OutputIdx);

    // const l2Output = await oracleContract.getL2Output(l2OutputIdx);
    // console.log('l2Output', l2Output);

    // const withdrawalMessage = await getWithdrawalMessage(
    //   messageContract,
    //   withdrawal,
    // );

    // const hashedWithdrawal = hashWithdrawal(withdrawalMessage);

    // const messageSlot = keccak256(
    //   defaultAbiCoder.encode(
    //     ['bytes32', 'uint256'],
    //     [hashedWithdrawal, HashZero],
    //   ),
    // );

    // const l2BlockNumber = '0x' + BigInt(l2Output[2]).toString(16);

    // const proof = await makeStateTrieProof(
    //   signer.provider,
    //   l2BlockNumber,
    //   l2ToL1MessagePasser,
    //   messageSlot,
    // );
    // console.log('proof', proof);

    // const block = await signer.provider.send('eth_getBlockByNumber', [
    //   l2BlockNumber,
    //   false,
    // ]);
    // console.log('block', block);

    // const outputProof = {
    //   version: HashZero,
    //   stateRoot: block.stateRoot,
    //   messagePasserStorageRoot: proof.storageRoot,
    //   latestBlockhash: block.hash,
    // };
    // console.log('outputProof', outputProof);

    // try {
    //   const proving = await portalContract.proveWithdrawalTransaction(
    //     withdrawalMessage,
    //     l2OutputIdx,
    //     outputProof,
    //     proof.storageProof,
    //   );
    //   console.log('proving', proving);
    //   const result = await proving.wait();
    //   console.log('proving result', result);
    // } catch (e) {
    //   console.log('withdrawal error', e);
    // }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
