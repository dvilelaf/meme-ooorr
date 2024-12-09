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

    const badName = "";
    const badSymbol = "";
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const smallDeposit = ethers.utils.parseEther("1");
    const defaultDeposit = ethers.utils.parseEther("1500");
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    const gasLimit = 10000000;
    const fee = 10000;
    // Nonce 1 is reserved for the campaign token
    // Nonce 2 is the first new meme token
    const nonce0 = 1;
    const nonce1 = 2;
    const nonce2 = 3;

    const signers = await ethers.getSigners();
    const deployer = signers[0];

    console.log("Balance of deployer:", await ethers.provider.getBalance(deployer.address));
    console.log("Balance of signer 1:", await ethers.provider.getBalance(signers[1].address));
    console.log("Balance of signer 2", await ethers.provider.getBalance(signers[2].address));

    console.log("Getting launch campaign data");
    const campaignFile = "scripts/deployment/memebase_campaign.json";
    dataFromJSON = fs.readFileSync(campaignFile, "utf8");
    const campaignData = JSON.parse(dataFromJSON);
    console.log("Number of entries:", campaignData.length);
    
    const accounts = new Array();
    const amounts = new Array();
    for (let i = 0; i < campaignData.length; i++) {
        accounts.push(campaignData[i]["hearter"]);
        amounts.push(campaignData[i]["amount"].toString());
    }

    // BalancerPriceOracle
    const BalancerPriceOracle = await ethers.getContractFactory("BalancerPriceOracle");
    const balancerPriceOracle = await BalancerPriceOracle.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.maxOracleSlippage, parsedData.minUpdateTimePeriod, parsedData.balancerVaultAddress,
        parsedData.balancerPoolId);
    await balancerPriceOracle.deployed();

    // BuyBackBurnerBase implementation and proxy
    const BuyBackBurnerBase = await ethers.getContractFactory("BuyBackBurnerBase");
    const buyBackBurnerImplementation = await BuyBackBurnerBase.deploy();
    await buyBackBurnerImplementation.deployed();

    // Initialize buyBackBurner
    const proxyPayload = ethers.utils.defaultAbiCoder.encode(["address[]", "bytes32", "uint256", "uint256"],
         [[parsedData.olasAddress, parsedData.wethAddress, balancerPriceOracle.address, parsedData.l2TokenBridgeAddress,
         parsedData.balancerVaultAddress], parsedData.balancerPoolId, parsedData.maxBuyBackSlippage,
         parsedData.minBridgedAmount]);
    const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", [proxyPayload]);
    const BuyBackBurnerProxy = await ethers.getContractFactory("BuyBackBurnerProxy");
    const buyBackBurnerProxy = await BuyBackBurnerProxy.deploy(buyBackBurnerImplementation.address, proxyData);
    await buyBackBurnerProxy.deployed();

    const buyBackBurner = await ethers.getContractAt("BuyBackBurnerBase", buyBackBurnerProxy.address);

    const MemeBase = await ethers.getContractFactory("MemeBase");
    const memeBase = await MemeBase.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, buyBackBurner.address, parsedData.minNativeTokenValue,
        accounts, amounts);
    await memeBase.deployed();

    const wethABI = fs.readFileSync("abis/misc/weth.json", "utf8");
    const weth = new ethers.Contract(parsedData.wethAddress, wethABI, ethers.provider);

    let baseBalance = await weth.balanceOf(memeBase.address);
    expect(baseBalance).to.equal(0);
 
    // Summon a new meme token - negative cases
    const minNativeTokenValue = await memeBase.minNativeTokenValue();
    const MIN_TOTAL_SUPPLY = await memeBase.MIN_TOTAL_SUPPLY();
    const uint128MaxPlusOne = BigInt(2) ** BigInt(128);
    await expect(
        memeBase.summonThisMeme(badName, badSymbol, totalSupply, {value: minNativeTokenValue})
    ).to.be.revertedWith("Name and symbol must not be empty");
    await expect(
        memeBase.summonThisMeme(name, badSymbol, totalSupply, {value: minNativeTokenValue})
    ).to.be.revertedWith("Name and symbol must not be empty");
    await expect(
        memeBase.summonThisMeme(name, symbol, totalSupply, {value: minNativeTokenValue.sub(1)})
    ).to.be.revertedWith("Minimum native token value is required to summon");
    await expect(
        memeBase.summonThisMeme(name, symbol, MIN_TOTAL_SUPPLY.sub(1), {value: minNativeTokenValue})
    ).to.be.revertedWith("Minimum total supply is not met");
    await expect(
        memeBase.summonThisMeme(name, symbol, uint128MaxPlusOne, {value: minNativeTokenValue})
    ).to.be.revertedWith("Maximum total supply overflow");

    // Summon a new meme token - positive cases
    await expect(
        memeBase.summonThisMeme(name, symbol, totalSupply, {value: smallDeposit})
    ).to.emit(memeBase, "Summoned")
    .withArgs(deployer.address, nonce1, smallDeposit)
    .and.to.emit(memeBase, "Hearted")
    .withArgs(deployer.address, nonce1, smallDeposit);

    let totalDeposit = smallDeposit;
    let memeSummon = await memeBase.memeSummons(nonce1);
    expect(memeSummon.name).to.equal(name);
    expect(memeSummon.symbol).to.equal(symbol);
    expect(memeSummon.totalSupply).to.equal(totalSupply);
    expect(memeSummon.nativeTokenContributed).to.equal(smallDeposit);
    const memeHearterValue = await memeBase.memeHearters(nonce1, deployer.address);
    expect(memeHearterValue).to.equal(smallDeposit);
    let accountActivity = await memeBase.mapAccountActivities(deployer.address);
    expect(accountActivity).to.equal(1);

    // Heart a new token by other accounts - negative case
    await expect(
        memeBase.connect(signers[1]).heartThisMeme(nonce1, {value: 0})
    ).to.be.revertedWith("Native token amount must be greater than zero");
    await expect(
        memeBase.connect(signers[1]).heartThisMeme(nonce2, {value: smallDeposit})
    ).to.be.revertedWith("Meme not yet summoned");
    // Check that launch campaign meme cannot be hearted (as a pseudo test)
    await expect(
        memeBase.connect(signers[1]).heartThisMeme(nonce0, {value: smallDeposit})
    ).to.be.revertedWith("Meme already unleashed");
    // Check that launch campaign meme cannot be collected
    await expect(
        memeBase.connect(signers[1]).collectThisMeme("0xFD49CbaE7bD16743bF9Fbb97bdFB30158e0b857e")
    ).to.be.revertedWith("Meme not unleashed");
    // // Check that launch campaign meme cannot be purged
    await expect(
        memeBase.connect(signers[1]).purgeThisMeme("0xFD49CbaE7bD16743bF9Fbb97bdFB30158e0b857e")
    ).to.be.revertedWith("Meme not unleashed");

    // Heart a new token by other accounts - positive cases
    await expect(
        memeBase.connect(signers[1]).heartThisMeme(nonce1, {value: smallDeposit})
    ).to.emit(memeBase, "Hearted")
    .withArgs(signers[1].address, nonce1, smallDeposit);

    totalDeposit = totalDeposit.add(smallDeposit)
    memeSummon = await memeBase.memeSummons(nonce1);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(2));
    accountActivity = await memeBase.mapAccountActivities(signers[1].address);
    expect(accountActivity).to.equal(1);
    await expect(
        memeBase.connect(signers[2]).heartThisMeme(nonce1, {value: smallDeposit})
    ).to.emit(memeBase, "Hearted")
    .withArgs(signers[2].address, nonce1, smallDeposit);

    totalDeposit = totalDeposit.add(smallDeposit)
    memeSummon = await memeBase.memeSummons(nonce1);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(3));
    accountActivity = await memeBase.mapAccountActivities(signers[2].address);
    expect(accountActivity).to.equal(1);

    await expect(
        memeBase.unleashThisMeme(nonce1)
    ).to.be.revertedWith("Cannot unleash yet");

    // nothing should be scheduled for ascendance yet
    let scheduledForAscendance = await memeBase.scheduledForAscendance();
    expect(scheduledForAscendance).to.equal(0);

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Update oracle price
    await buyBackBurner.updateOraclePrice();

    // native token balance should be equal to contributions
    let balanceNow = ethers.BigNumber.from(smallDeposit).mul(3);
    baseBalance = await ethers.provider.getBalance(memeBase.address);
    expect(baseBalance).to.equal(balanceNow);

    // Unleash the meme token - positive and negative cases
    await expect(
        memeBase.unleashThisMeme(nonce2)
    ).to.be.revertedWith("Meme not yet summoned");
    await expect(
        memeBase.unleashThisMeme(nonce1, { gasLimit })
    ).to.emit(memeBase, "Unleashed")
    // .withArgs(deployer.address, null, null, null, 0)
    .and.to.emit(memeBase, "Collected");
    // .withArgs(deployer.address, null, null);
    await expect(
        memeBase.unleashThisMeme(nonce1)
    ).to.be.revertedWith("Meme already unleashed");

    accountActivity = await memeBase.mapAccountActivities(deployer.address);
    expect(accountActivity).to.equal(2);

    // Get first token address
    const memeToken = await memeBase.memeTokens(0);
    console.log("First new meme token contract:", memeToken);

    memeSummon = await memeBase.memeSummons(nonce1);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(3));

    // Schedule for ascendance (~90% of it went to LP)
    scheduledForAscendance = await memeBase.scheduledForAscendance();
    expect(scheduledForAscendance).to.gte(ethers.BigNumber.from(smallDeposit).mul(3).div(10));

    // Wrapped mative token balance (~90% of it went to LP)
    baseBalance = await weth.balanceOf(memeBase.address);
    expect(baseBalance).to.gte(scheduledForAscendance);

    // Pure native token balance (everything should have been wrapped by now)
    baseBalance = await ethers.provider.getBalance(memeBase.address);
    expect(baseBalance).to.equal(0);

    // Increase time to for 24 hours+
    await expect(
        memeBase.purgeThisMeme(memeToken)
    ).to.be.revertedWith("Purge only allowed from 24 hours after unleash");
    await helpers.time.increase(oneDay + 10);

    // Purge remaining allocation - positive and negative case
    await memeBase.purgeThisMeme(memeToken);

    let memeInstance = await ethers.getContractAt("Meme", memeToken);
    // Meme balance now must be zero
    baseBalance = await memeInstance.balanceOf(memeBase.address);
    expect(baseBalance).to.equal(0);

    // Test failing schedule for ascendance
    await expect(
        memeBase.scheduleForAscendance()
    ).to.be.revertedWith("Not enough to cover launch campaign")

    //// Second test unleashing of a meme

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});

    // Heart a new token by other accounts
    await memeBase.connect(signers[1]).heartThisMeme(nonce2, {value: defaultDeposit});
    await memeBase.connect(signers[2]).heartThisMeme(nonce2, {value: defaultDeposit});

    // Update total deposit
    totalDeposit = totalDeposit.add(defaultDeposit.mul(3));

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await expect(
        memeBase.unleashThisMeme(nonce2, { gasLimit })
    ).to.emit(memeBase, "Unleashed").and.to.emit(memeBase, "Unleashed");

    // Get campaign token
    const memeTokenTwo = await memeBase.memeTokens(1);
    console.log("Second new meme contract:", memeTokenTwo);

    const LIQUIDITY_AGNT = await memeBase.LIQUIDITY_AGNT();
    scheduledForAscendance = await memeBase.scheduledForAscendance();
    const scheduledPart1 = (smallDeposit.mul(3)).div(10);
    const scheduledPart2 = (defaultDeposit.mul(3)).div(10);
    let expectedScheduledForAscendance = scheduledPart1.add(scheduledPart2);
    // due to rounding will have higher amount than expected
    expect(scheduledForAscendance).to.gte(expectedScheduledForAscendance);

    // Deployer has already collected
    await expect(
        memeBase.collectThisMeme(memeTokenTwo)
    ).to.be.reverted;

    // Collect by the first signer
    await memeBase.connect(signers[1]).collectThisMeme(memeTokenTwo);

    // Wait for 24 more hours
    await helpers.time.increase(oneDay + 10);

    // Second signer cannot collect
    await expect(
        memeBase.connect(signers[2]).collectThisMeme(memeTokenTwo)
    ).to.be.revertedWith("Collect only allowed until 24 hours after unleash");

    // Purge remaining allocation
    await memeBase.purgeThisMeme(memeTokenTwo);

    // Wait for 10 more seconds
    await helpers.time.increase(10);

    // Collect fees
    scheduledForAscendance = await memeBase.scheduledForAscendance();
    await memeBase.collectFees([memeToken, memeTokenTwo], { gasLimit });
    let newScheduledForAscendance = await memeBase.scheduledForAscendance();
    // since no fees to collect, expect identical
    expect(newScheduledForAscendance).to.equal(scheduledForAscendance);

    // Send to burner
    await expect(
        memeBase.scheduleForAscendance({ gasLimit })
    ).to.emit(memeBase, "Unleashed")
    .and.to.emit(memeBase, "OLASJourneyToAscendance")
    // Get meme token
    const campaignToken = await memeBase.memeTokens(2);
    console.log("Campaign token contract:", campaignToken);
    scheduledForAscendance = await memeBase.scheduledForAscendance();
    expect(scheduledForAscendance).to.equal(0);

    // Check the contract balances - must be no native and wrapped token left after all the unleashes
    baseBalance = await ethers.provider.getBalance(memeBase.address);
    expect(baseBalance).to.equal(0);

    // Check the wrapped native token contract balance
    baseBalance = await weth.balanceOf(memeBase.address);
    expect(baseBalance).to.equal(0);

    // Check the number of meme tokens
    const numTokens = await memeBase.numTokens();
    expect(numTokens).to.equal(3);

    // Swap tokens
    const factoryABI = fs.readFileSync("abis/misc/factory.json", "utf8");
    const factory = new ethers.Contract(parsedData.factoryAddress, factoryABI, ethers.provider);
    const quoterABI = fs.readFileSync("abis/misc/quoter.json", "utf8");
    const quoter = new ethers.Contract(parsedData.quoterAddress, quoterABI, ethers.provider);
    const routerABI = fs.readFileSync("abis/misc/swaprouter.json", "utf8");
    const router = new ethers.Contract(parsedData.routerV3Address, routerABI, ethers.provider);
    const poolAddress = await factory.getPool(weth.address, memeToken, fee);
    const poolABI = fs.readFileSync("abis/misc/pool.json", "utf8");
    const pool = new ethers.Contract(poolAddress, poolABI, ethers.provider);

    //let slot0 = await pool.slot0();
    //console.log("0. slot0:", slot0);
    //let observations0 = await pool.observations(0);
    //console.log("0. observations0:", observations0);

    const memeTokenInstance = await ethers.getContractAt("Meme", memeToken);
    const memeBalance = await memeTokenInstance.balanceOf(deployer.address);
    const amount = memeBalance.div(3);
    // Approve tokens
    await memeTokenInstance.approve(parsedData.routerV3Address, amount);

    const quote = {
        tokenIn: memeTokenInstance.address,
        tokenOut: weth.address,
        fee,
        recipient: deployer.address,
        deadline: Math.floor(new Date().getTime() / 1000 + 60 * 10),
        amountIn: amount,
        sqrtPriceLimitX96: 0,
    };

    // Get amount out
    let quotedAmountOut = await quoter.callStatic.quoteExactInputSingle(quote);
    // Amount our must be bigger
    expect(quotedAmountOut.amountOut).to.gt(0);

    let params = {
        tokenIn: memeTokenInstance.address,
        tokenOut: weth.address,
        fee,
        recipient: deployer.address,
        deadline: Math.floor(new Date().getTime() / 1000 + oneDay),
        amountIn: amount,
        amountOutMinimum: quotedAmountOut.amountOut,
        sqrtPriceLimitX96: 0,
    };

    // Swap tokens
    await router.connect(deployer).exactInputSingle(params);

    //slot0 = await pool.slot0();
    //console.log("1. slot0:", slot0);
    //observations0 = await pool.observations(0);
    //console.log("1. observations0:", observations0);

    // Wait for 10 seconds
    await helpers.time.increase(10);

    // Approve tokens
    await memeTokenInstance.approve(parsedData.routerV3Address, amount);
    // Get amount out for another swap
    quotedAmountOut = await quoter.callStatic.quoteExactInputSingle(quote);
    // Amount our must be bigger
    expect(quotedAmountOut.amountOut).to.gt(0);

    params = {
        tokenIn: memeTokenInstance.address,
        tokenOut: weth.address,
        fee,
        recipient: deployer.address,
        deadline: Math.floor(new Date().getTime() / 1000 + oneDay),
        amountIn: amount,
        amountOutMinimum: quotedAmountOut.amountOut,
        sqrtPriceLimitX96: 0,
    };

    // Perform another swap
    await router.connect(deployer).exactInputSingle(params);

    //slot0 = await pool.slot0();
    //console.log("2. slot0:", slot0);
    //observations0 = await pool.observations(0);
    //console.log("2. observations0:", observations0);

    // Wait for 10 seconds
    await helpers.time.increase(10);

    // Collect fees
    await expect(
        memeBase.collectFees([memeToken], { gasLimit })
    ).to.emit(memeBase, "FeesCollected")

    // Update oracle price
    await buyBackBurner.updateOraclePrice();

    // TODO: fail to do swaps right away
    // Swap native token for OLAS
    //await buyBackBurner.buyBack(ethers.utils.parseEther("5"));

    // Wait for 10 seconds more in order not to engage with oracle in the same timestamp
    await helpers.time.increase(10);

    // TODO: fail to do huge swaps
    // Swap native token for OLAS
    //await buyBackBurner.buyBack(0);

    // TODO: fail to do swaps breaching the after-swap limit (find value)
    // Swap native token for OLAS
    //await buyBackBurner.buyBack(ethers.utils.parseEther("10"));

    // TODO Error to bridge when there's not enough value to bridge
    // Bridge OLAS to burn
    //await buyBackBurner.bridgeAndBurn(0, "0x");

    // Swap native token for OLAS
    await buyBackBurner.buyBack(ethers.utils.parseEther("5"));

    // Bridge OLAS to burn
    await buyBackBurner.bridgeAndBurn(0, "0x");
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
