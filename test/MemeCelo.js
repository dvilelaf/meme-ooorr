/*global describe, context, beforeEach, it*/
const { expect } = require("chai");
const { ethers } = require("hardhat");
const helpers = require("@nomicfoundation/hardhat-network-helpers");

// This works on a fork only!
const main = async () => {
    const fs = require("fs");
    const globalsFile = "globals.json";
    const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    const parsedData = JSON.parse(dataFromJSON);

    const AddressZero = ethers.constants.AddressZero;
    const HashZero = ethers.constants.HashZero;
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const defaultDeposit = parsedData.minNativeTokenValue;//ethers.utils.parseEther("1");
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    const nonce = 1;

    signers = await ethers.getSigners();
    deployer = signers[0];

    // UniswapPriceOracle
    const UniswapPriceOracle = await ethers.getContractFactory("UniswapPriceOracle");
    const uniswapPriceOracle = await UniswapPriceOracle.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.maxOracleSlippage, parsedData.minUpdateTimePeriod, parsedData.routerV2Address);
    await uniswapPriceOracle.deployed();

    // BuyBackBurnerCelo implementation and proxy
    const BuyBackBurnerCelo = await ethers.getContractFactory("BuyBackBurnerCelo");
    const buyBackBurnerImplementation = await BuyBackBurnerCelo.deploy();
    await buyBackBurnerImplementation.deployed();

    // Initialize buyBackBurner
    const proxyPayload = ethers.utils.defaultAbiCoder.encode(["address[]", "uint256", "uint256"],
         [[parsedData.olasAddress, parsedData.wethAddress, uniswapPriceOracle.address, parsedData.l2TokenBridgeAddress,
         parsedData.routerV2Address], parsedData.maxBuyBackSlippage, parsedData.minBridgedAmount]);
    const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", [proxyPayload]);
    const BuyBackBurnerProxy = await ethers.getContractFactory("BuyBackBurnerProxy");
    const buyBackBurnerProxy = await BuyBackBurnerProxy.deploy(buyBackBurnerImplementation.address, proxyData);
    await buyBackBurnerProxy.deployed();

    const buyBackBurner = await ethers.getContractAt("BuyBackBurnerCelo", buyBackBurnerProxy.address);

    // MemeBase
    const MemeBase = await ethers.getContractFactory("MemeBase");
    const memeBase = await MemeBase.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, buyBackBurner.address, parsedData.minNativeTokenValue, [], []);
    await memeBase.deployed();

    const MemeCelo = await ethers.getContractFactory("MemeCelo");
    const memeCelo = await MemeCelo.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, buyBackBurner.address, parsedData.minNativeTokenValue);
    await memeCelo.deployed();

    // Summon a new meme token
    await memeCelo.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});

    // Heart a new token by other accounts
    await memeCelo.connect(signers[1]).heartThisMeme(nonce, {value: defaultDeposit});
    await memeCelo.connect(signers[2]).heartThisMeme(nonce, {value: defaultDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 100);

    // Unleash the meme token
    await memeCelo.unleashThisMeme(nonce);

    const memeToken = await memeCelo.memeTokens(0);
    console.log("New meme contract:", memeToken);

    // Collect by the first signer
    await memeCelo.connect(signers[1]).collectThisMeme(memeToken);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
