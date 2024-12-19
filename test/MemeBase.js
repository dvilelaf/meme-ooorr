/*global describe, context, beforeEach, it*/
const { expect } = require("chai");
const { ethers } = require("hardhat");
const helpers = require("@nomicfoundation/hardhat-network-helpers");

// This works on a fork only!
const main = async () => {
    const fs = require("fs");
    const globalsFile = "globals.json";
    let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    const parsedData = JSON.parse(dataFromJSON);

    const AddressZero = ethers.constants.AddressZero;
    const HashZero = ethers.constants.HashZero;
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const defaultDeposit = parsedData.minNativeTokenValue;
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    const nonce = 1;

    signers = await ethers.getSigners();
    deployer = signers[0];

    // BalancerPriceOracle
    const BalancerPriceOracle = await ethers.getContractFactory("BalancerPriceOracle");
    const balancerPriceOracle = await BalancerPriceOracle.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.maxOracleSlippage, parsedData.minUpdateTimePeriod, parsedData.balancerVaultAddress,
        parsedData.balancerPoolId);
    await balancerPriceOracle.deployed();

    // BuyBackBurnerBalancer implementation and proxy
    const BuyBackBurnerBalancer = await ethers.getContractFactory("BuyBackBurnerBalancer");
    const buyBackBurnerImplementation = await BuyBackBurnerBalancer.deploy();
    await buyBackBurnerImplementation.deployed();

    // Initialize buyBackBurner
    const proxyPayload = ethers.utils.defaultAbiCoder.encode(["address[]", "bytes32", "uint256"],
         [[parsedData.olasAddress, parsedData.wethAddress, balancerPriceOracle.address,
         parsedData.balancerVaultAddress], parsedData.balancerPoolId, parsedData.maxBuyBackSlippage]);
    const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", [proxyPayload]);
    const BuyBackBurnerProxy = await ethers.getContractFactory("BuyBackBurnerProxy");
    const buyBackBurnerProxy = await BuyBackBurnerProxy.deploy(buyBackBurnerImplementation.address, proxyData);
    await buyBackBurnerProxy.deployed();

    const buyBackBurner = await ethers.getContractAt("BuyBackBurnerBalancer", buyBackBurnerProxy.address);

    // MemeBase
    const MemeBase = await ethers.getContractFactory("MemeBase");
    const memeBase = await MemeBase.deploy(parsedData.wethAddress, parsedData.uniV3positionManagerAddress,
         buyBackBurner.address, parsedData.minNativeTokenValue, [], []);
    await memeBase.deployed();

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});

    // Heart a new token by other accounts
    await memeBase.connect(signers[1]).heartThisMeme(nonce, {value: defaultDeposit});
    await memeBase.connect(signers[2]).heartThisMeme(nonce, {value: defaultDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await memeBase.unleashThisMeme(nonce);

    const memeToken = await memeBase.memeTokens(0);
    console.log("New meme contract:", memeToken);

    // Deployer has already collected
    await expect(
        memeBase.collectThisMeme(memeToken)
    ).to.be.reverted;

    // Collect by the first signer
    await memeBase.connect(signers[1]).collectThisMeme(memeToken);

    // Wait for 24 more hours
    await helpers.time.increase(oneDay + 10);

    // Second signer cannot collect
    await expect(
        memeBase.connect(signers[2]).collectThisMeme(memeToken)
    ).to.be.reverted;

    // Purge remaining allocation
    await memeBase.purgeThisMeme(memeToken);

    // Wait for 10 more seconds
    await helpers.time.increase(10);

    // Swap to OLAS
    const olasAmount = await memeBase.scheduledForAscendance();
    if (olasAmount.gt(0)) {
        await memeBase.scheduleForAscendance();
    }

    // Collect fees
    await memeBase.collectFees([memeToken]);

    // Get meme token info
    //const memeInfo = await memeBase.memeSummons(nonce);
    //console.log(memeInfo);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
