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

    const badName = "";
    const badSymbol = "";
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const smallDeposit = ethers.utils.parseEther("1");
    const defaultDeposit = ethers.utils.parseEther("1500");
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    const gasLimit = 10000000;
    const fee = 10000;
    const nonce0 = 1;
    const nonce1 = 2;

    const signers = await ethers.getSigners();
    const deployer = signers[0];

    console.log("deployer address:", deployer.address);
    console.log("Balance of deployer:", await ethers.provider.getBalance(deployer.address));
    console.log("signers[1] address:", signers[1].address);
    console.log("Balance of signer 1:", await ethers.provider.getBalance(signers[1].address));
    console.log("signers[2] address:", signers[2].address);
    console.log("Balance of signer 2", await ethers.provider.getBalance(signers[2].address));

    // UniswapPriceOracle
    const UniswapPriceOracle = await ethers.getContractFactory("UniswapPriceOracle");
    const uniswapPriceOracle = await UniswapPriceOracle.deploy(parsedData.wethAddress, parsedData.maxOracleSlippage,
        parsedData.pairAddress);
    await uniswapPriceOracle.deployed();

    // BuyBackBurnerUniswap implementation and proxy
    const BuyBackBurnerUniswap = await ethers.getContractFactory("BuyBackBurnerUniswap");
    const buyBackBurnerImplementation = await BuyBackBurnerUniswap.deploy();
    await buyBackBurnerImplementation.deployed();

    // Initialize buyBackBurner
    const proxyPayload = ethers.utils.defaultAbiCoder.encode(["address[]", "uint256"],
         [[parsedData.olasAddress, parsedData.wethAddress, uniswapPriceOracle.address,
         parsedData.routerV2Address], parsedData.maxBuyBackSlippage]);
    const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", [proxyPayload]);
    const BuyBackBurnerProxy = await ethers.getContractFactory("BuyBackBurnerProxy");
    const buyBackBurnerProxy = await BuyBackBurnerProxy.deploy(buyBackBurnerImplementation.address, proxyData);
    await buyBackBurnerProxy.deployed();

    const buyBackBurner = await ethers.getContractAt("BuyBackBurnerUniswap", buyBackBurnerProxy.address);

    const MemeEthereum = await ethers.getContractFactory("MemeEthereum");
    const memeEthereum = await MemeEthereum.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, buyBackBurner.address, parsedData.minNativeTokenValue);
    await memeEthereum.deployed();

    const wethABI = fs.readFileSync("abis/uniswap/weth.json", "utf8");
    const weth = new ethers.Contract(parsedData.wethAddress, wethABI, ethers.provider);

    let ethBalance = await weth.balanceOf(memeEthereum.address);
    expect(ethBalance).to.equal(0);

    // Summon a new meme token - negative cases
    const minNativeTokenValue = await memeEthereum.minNativeTokenValue();
    const MIN_TOTAL_SUPPLY = await memeEthereum.MIN_TOTAL_SUPPLY();
    const uint128MaxPlusOne = BigInt(2) ** BigInt(128);
    await expect(
        memeEthereum.summonThisMeme(badName, badSymbol, totalSupply, {value: minNativeTokenValue})
    ).to.be.revertedWith("Name and symbol must not be empty");
    await expect(
        memeEthereum.summonThisMeme(name, badSymbol, totalSupply, {value: minNativeTokenValue})
    ).to.be.revertedWith("Name and symbol must not be empty");
    await expect(
        memeEthereum.summonThisMeme(name, symbol, totalSupply, {value: minNativeTokenValue.sub(1)})
    ).to.be.revertedWith("Minimum native token value is required to summon");
    await expect(
        memeEthereum.summonThisMeme(name, symbol, MIN_TOTAL_SUPPLY.sub(1), {value: minNativeTokenValue})
    ).to.be.revertedWith("Minimum total supply is not met");
    await expect(
        memeEthereum.summonThisMeme(name, symbol, uint128MaxPlusOne, {value: minNativeTokenValue})
    ).to.be.revertedWith("Maximum total supply overflow");

    // Summon a new meme token - positive cases
    await expect(
        memeEthereum.summonThisMeme(name, symbol, totalSupply, {value: smallDeposit})
    ).to.emit(memeEthereum, "Summoned")
    .withArgs(deployer.address, nonce0, smallDeposit)
    .and.to.emit(memeEthereum, "Hearted")
    .withArgs(deployer.address, nonce0, smallDeposit);

    let totalDeposit = smallDeposit;
    let memeSummon = await memeEthereum.memeSummons(nonce0);
    expect(memeSummon.name).to.equal(name);
    expect(memeSummon.symbol).to.equal(symbol);
    expect(memeSummon.totalSupply).to.equal(totalSupply);
    expect(memeSummon.nativeTokenContributed).to.equal(smallDeposit);
    const memeHearterValue = await memeEthereum.memeHearters(nonce0, deployer.address);
    expect(memeHearterValue).to.equal(smallDeposit);
    let accountActivity = await memeEthereum.mapAccountActivities(deployer.address);
    expect(accountActivity).to.equal(1);

    // Heart a new token by other accounts - negative case
    await expect(
        memeEthereum.connect(signers[1]).heartThisMeme(nonce0, {value: 0})
    ).to.be.revertedWith("Native token amount must be greater than zero");
    await expect(
        memeEthereum.connect(signers[1]).heartThisMeme(nonce1, {value: smallDeposit})
    ).to.be.revertedWith("Meme not yet summoned");
    // Check that launch campaign meme cannot be collected
    await expect(
        memeEthereum.connect(signers[1]).collectThisMeme("0xFD49CbaE7bD16743bF9Fbb97bdFB30158e0b857e")
    ).to.be.revertedWith("Meme not unleashed");
    // // Check that launch campaign meme cannot be purged
    await expect(
        memeEthereum.connect(signers[1]).purgeThisMeme("0xFD49CbaE7bD16743bF9Fbb97bdFB30158e0b857e")
    ).to.be.revertedWith("Meme not unleashed");

    // Heart a new token by other accounts - positive cases
    await expect(
        memeEthereum.connect(signers[1]).heartThisMeme(nonce0, {value: smallDeposit})
    ).to.emit(memeEthereum, "Hearted")
    .withArgs(signers[1].address, nonce0, smallDeposit);

    totalDeposit = totalDeposit.add(smallDeposit)
    memeSummon = await memeEthereum.memeSummons(nonce0);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(2));
    accountActivity = await memeEthereum.mapAccountActivities(signers[1].address);
    expect(accountActivity).to.equal(1);
    await expect(
        memeEthereum.connect(signers[2]).heartThisMeme(nonce0, {value: smallDeposit})
    ).to.emit(memeEthereum, "Hearted")
    .withArgs(signers[2].address, nonce0, smallDeposit);

    totalDeposit = totalDeposit.add(smallDeposit)
    memeSummon = await memeEthereum.memeSummons(nonce0);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(3));
    accountActivity = await memeEthereum.mapAccountActivities(signers[2].address);
    expect(accountActivity).to.equal(1);

    await expect(
        memeEthereum.unleashThisMeme(nonce0)
    ).to.be.revertedWith("Cannot unleash yet");

    // nothing should be scheduled for ascendance yet
    let scheduledForAscendance = await memeEthereum.scheduledForAscendance();
    expect(scheduledForAscendance).to.equal(0);

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // native token balance should be equal to contributions
    let balanceNow = ethers.BigNumber.from(smallDeposit).mul(3);
    ethBalance = await ethers.provider.getBalance(memeEthereum.address);
    expect(ethBalance).to.equal(balanceNow);

    // Unleash the meme token - positive and negative cases
    await expect(
        memeEthereum.unleashThisMeme(nonce1)
    ).to.be.revertedWith("Meme not yet summoned");
    await expect(
        memeEthereum.unleashThisMeme(nonce0, { gasLimit })
    ).to.emit(memeEthereum, "Unleashed")
    // .withArgs(deployer.address, null, null, null, 0)
    .and.to.emit(memeEthereum, "Collected");
    // .withArgs(deployer.address, null, null);
    await expect(
        memeEthereum.unleashThisMeme(nonce0)
    ).to.be.revertedWith("Meme already unleashed");

    accountActivity = await memeEthereum.mapAccountActivities(deployer.address);
    expect(accountActivity).to.equal(2);

    // Get first token address
    const memeToken = await memeEthereum.memeTokens(0);
    console.log("First new meme token contract:", memeToken);

    // Try to collect fees right away when the TWAP data is still unavailable
    await expect(
        memeEthereum.collectFees([memeToken])
    ).to.be.revertedWith("OLD");

    memeSummon = await memeEthereum.memeSummons(nonce0);
    expect(memeSummon.nativeTokenContributed).to.equal(ethers.BigNumber.from(smallDeposit).mul(3));

    // Schedule for ascendance (~90% of it went to LP)
    scheduledForAscendance = await memeEthereum.scheduledForAscendance();
    expect(scheduledForAscendance).to.gte(ethers.BigNumber.from(smallDeposit).mul(3).div(10));

    // Wrapped mative token balance (~90% of it went to LP)
    ethBalance = await weth.balanceOf(memeEthereum.address);
    expect(ethBalance).to.gte(scheduledForAscendance);

    // Pure native token balance (everything should have been wrapped by now)
    ethBalance = await ethers.provider.getBalance(memeEthereum.address);
    expect(ethBalance).to.equal(0);

    // Increase time to for 24 hours+
    await expect(
        memeEthereum.purgeThisMeme(memeToken)
    ).to.be.revertedWith("Purge only allowed from 24 hours after unleash");
    await helpers.time.increase(oneDay + 10);

    // Purge remaining allocation - positive and negative case
    await memeEthereum.purgeThisMeme(memeToken);

    let memeInstance = await ethers.getContractAt("Meme", memeToken);
    // Meme balance now must be zero
    ethBalance = await memeInstance.balanceOf(memeEthereum.address);
    expect(ethBalance).to.equal(0);

    //// Second test unleashing of a meme

    // Summon a new meme token
    await memeEthereum.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});

    // Heart a new token by other accounts
    await memeEthereum.connect(signers[1]).heartThisMeme(nonce1, {value: defaultDeposit});
    await memeEthereum.connect(signers[2]).heartThisMeme(nonce1, {value: defaultDeposit});

    // Update total deposit
    totalDeposit = totalDeposit.add(defaultDeposit.mul(3));

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await expect(
        memeEthereum.unleashThisMeme(nonce1, { gasLimit })
    ).to.emit(memeEthereum, "Unleashed")
    .and.to.emit(memeEthereum, "Collected");

    // Get campaign token
    const memeTokenTwo = await memeEthereum.memeTokens(1);
    console.log("Second new meme contract:", memeTokenTwo);

    // Deployer has already collected
    await expect(
        memeEthereum.collectThisMeme(memeTokenTwo)
    ).to.be.revertedWith("No token allocation");

    // Collect by the first signer
    await memeEthereum.connect(signers[1]).collectThisMeme(memeTokenTwo);

    // Wait for 24 more hours
    await helpers.time.increase(oneDay + 10);

    // Second signer cannot collect
    await expect(
        memeEthereum.connect(signers[2]).collectThisMeme(memeTokenTwo)
    ).to.be.revertedWith("Collect only allowed until 24 hours after unleash");

    // Purge remaining allocation
    await memeEthereum.purgeThisMeme(memeTokenTwo);

    // Try to purge again
    await expect(
        memeEthereum.purgeThisMeme(memeTokenTwo)
    ).to.be.revertedWith("Has been purged or nothing to purge");

    // Wait for 10 more seconds
    await helpers.time.increase(10);

    // Collect fees
    scheduledForAscendance = await memeEthereum.scheduledForAscendance();
    // Try to collect fees when there were no swaps
    await expect(
        memeEthereum.collectFees([memeToken, memeTokenTwo])
    ).to.be.revertedWith("Zero fees available");

    let newScheduledForAscendance = await memeEthereum.scheduledForAscendance();
    // since no fees to collect, expect identical
    expect(newScheduledForAscendance).to.equal(scheduledForAscendance);

    // Send to buyBackBurner
    await expect(
        memeEthereum.scheduleForAscendance()
    ).to.emit(memeEthereum, "OLASJourneyToAscendance");

    // Try to send to buyBackBurner again
    await expect(
        memeEthereum.scheduleForAscendance()
    ).to.be.revertedWith("Nothing to send");

    scheduledForAscendance = await memeEthereum.scheduledForAscendance();
    expect(scheduledForAscendance).to.equal(0);

    // Check the contract balances - must be no native and wrapped token left after all the unleashes
    ethBalance = await ethers.provider.getBalance(memeEthereum.address);
    expect(ethBalance).to.equal(0);

    // Check the wrapped native token contract balance
    ethBalance = await weth.balanceOf(memeEthereum.address);
    expect(ethBalance).to.equal(0);

    // Check the number of meme tokens
    const numTokens = await memeEthereum.numTokens();
    expect(numTokens).to.equal(2);

    // Swap tokens
    const factoryABI = fs.readFileSync("abis/uniswap/factory.json", "utf8");
    const factory = new ethers.Contract(parsedData.factoryAddress, factoryABI, ethers.provider);
    const quoterABI = fs.readFileSync("abis/uniswap/quoter.json", "utf8");
    const quoter = new ethers.Contract(parsedData.quoterAddress, quoterABI, ethers.provider);
    const routerABI = fs.readFileSync("abis/uniswap/swaprouter.json", "utf8");
    const router = new ethers.Contract(parsedData.routerV3Address, routerABI, ethers.provider);
    const poolAddress = await factory.getPool(weth.address, memeToken, fee);
    const poolABI = fs.readFileSync("abis/uniswap/pool.json", "utf8");
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

    // Wait for 1800 seconds to have enough time for the oldest observation
    await helpers.time.increase(1800);

    // Collect fees for the first time
    await memeEthereum.collectFees([memeToken], { gasLimit });

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

    // Wait for 100 seconds
    await helpers.time.increase(100);

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
    //console.log("3. slot0:", slot0);
    //observations0 = await pool.observations(0);
    //console.log("3. observations0:", observations0);

    // Wait for 100 seconds
    await helpers.time.increase(100);

    // Try to collect fees - but not enough time passed after huge swaps
    // NOTE: In order for revert to work correctly one needs to remove gasLimit, as it's conflicting with the estimation
    await expect(
        memeEthereum.collectFees([memeToken])
    ).to.be.revertedWith("Price deviation too high");

    // Wait for 1200 seconds - not more than 1800 seconds, because after 1800 of inactivity the price is considered correct
    await helpers.time.increase(1200);

    // Collect fees
    await expect(
        memeEthereum.collectFees([memeToken], { gasLimit })
    ).to.emit(memeEthereum, "FeesCollected");

    // Try to collect fees again
    await expect(
        memeEthereum.collectFees([memeToken])
    ).to.be.revertedWith("Zero fees available");

    // Wait for 10 seconds more in order not to engage with oracle in the same timestamp
    await helpers.time.increase(10);

    // Try to do a very big swap that completely unbalances the pool
    await expect(
        buyBackBurner.buyBack(0)
    ).to.be.revertedWith("After swap slippage limit is breached");

    // After swap slippage limit is not going to be fully simulated as swaps on Uniswap V2 provide TWAP updates
    // Swap native token for OLAS
    await buyBackBurner.buyBack(ethers.utils.parseEther("5"));
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
