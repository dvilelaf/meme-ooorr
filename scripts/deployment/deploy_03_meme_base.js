/*global process*/

const { ethers } = require("hardhat");
const { LedgerSigner } = require("@anders-t/ethers-ledger");

async function main() {
    const fs = require("fs");
    const globalsFile = "globals.json";
    let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    let parsedData = JSON.parse(dataFromJSON);
    const useLedger = parsedData.useLedger;
    const derivationPath = parsedData.derivationPath;
    const providerName = parsedData.providerName;
    const gasPriceInGwei = parsedData.gasPriceInGwei;

    let networkURL = parsedData.networkURL;
    if (providerName === "polygon") {
        if (!process.env.ALCHEMY_API_KEY_MATIC) {
            console.log("set ALCHEMY_API_KEY_MATIC env variable");
        }
        networkURL += process.env.ALCHEMY_API_KEY_MATIC;
    } else if (providerName === "polygonAmoy") {
        if (!process.env.ALCHEMY_API_KEY_AMOY) {
            console.log("set ALCHEMY_API_KEY_AMOY env variable");
            return;
        }
        networkURL += process.env.ALCHEMY_API_KEY_AMOY;
    }

    const provider = new ethers.providers.JsonRpcProvider(networkURL);
    const signers = await ethers.getSigners();

    let EOA;
    if (useLedger) {
        EOA = new LedgerSigner(provider, derivationPath);
    } else {
        EOA = signers[0];
    }
    // EOA address
    const deployer = await EOA.getAddress();
    console.log("EOA is:", deployer);

    console.log("Getting redemption data");
    const redemptionsFile = "scripts/deployment/memebase_redemption.json";
    dataFromJSON = fs.readFileSync(redemptionsFile, "utf8");
    const redemptionsData = JSON.parse(dataFromJSON);
    console.log("Number of entries:", redemptionsData.length);

    const accounts = new Array();
    const amounts = new Array();
    for (let i = 0; i < redemptionsData.length; i++) {
        accounts.push(redemptionsData[i]["hearter"]);
        amounts.push(redemptionsData[i]["amount"].toString());
    }

    // Transaction signing and execution
    console.log("3. EOA to deploy MemeBase");
    const gasPrice = ethers.utils.parseUnits(gasPriceInGwei, "gwei");
    const MemeBase = await ethers.getContractFactory("MemeBase");
    console.log("You are signing the following transaction: MemeBase.connect(EOA).deploy()");
    const memeBase = await MemeBase.connect(EOA).deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, parsedData.buyBackBurnerAddress, parsedData.minNativeTokenValue,
        accounts, amounts, { gasPrice });
    const result = await memeBase.deployed();

    // Transaction details
    console.log("Contract deployment: MemeBase");
    console.log("Contract address:", memeBase.address);
    console.log("Transaction:", result.deployTransaction.hash);

    // Wait for half a minute for the transaction completion
    await new Promise(r => setTimeout(r, 30000));

    // Writing updated parameters back to the JSON file
    parsedData.memeBaseAddress = memeBase.address;
    fs.writeFileSync(globalsFile, JSON.stringify(parsedData));

    // Contract verification
    if (parsedData.contractVerification) {
        const execSync = require("child_process").execSync;
        execSync("npx hardhat verify --constructor-args scripts/deployment/verify_03_meme_base.js --network " + providerName + " " + memeBase.address, { encoding: "utf-8" });
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
