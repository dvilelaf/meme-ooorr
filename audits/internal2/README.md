# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `8e188f0f960fdf7c4d1538dd195152df88b6c55b` or `tag: v0.2.0-pre-internal-audi` <br>

## Objectives
The audit focused on Meme* contracts <BR>

### Flatten version
Flatten version of contracts. [contracts](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal2/analysis/contracts)

### Security issues
Details in [slither_full](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal2/analysis/slither_full.txt) <br>
All false positive.

## Issue (medium/critical)
### receive() without windraw() on Meme* (medium)
```
    /// @dev Allows the contract to receive native token
    receive() external payable {}
    It is unclear why the contract accepts arbitrary ETH to address of contract. Purposes? Contract locking ether found.
```
[x] Fixed

### function __createUniswapPair() internal possible manipulated if pool exists (critical)
Any interactions with the pool (v3 too) can be attacked using the sandwich method.
```
If pool exist, then
Lack of Price Oracle Validation:

There is no mechanism to validate the input price (amount1 / amount0) against a trusted oracle or time-weighted average price (TWAP).
Without this validation, attackers could manipulate the price temporarily using flashloans and then initialize the pool with a skewed price.
Thanks, ChatGPT 4o mini to loang discussion.
```

or code:
```
function _createUniswapPair(
    address memeToken,
    uint256 nativeTokenAmount,
    uint256 memeTokenAmount
) internal returns (uint256 positionId, uint256 liquidity, bool isNativeFirst) {
    require(nativeTokenAmount > 0 && memeTokenAmount > 0, "Amounts must be positive");

    if (nativeToken < memeToken) {
        isNativeFirst = true;
    }

    (address token0, address token1, uint256 amount0, uint256 amount1) = isNativeFirst
        ? (nativeToken, memeToken, nativeTokenAmount, memeTokenAmount)
        : (memeToken, nativeToken, memeTokenAmount, nativeTokenAmount);

    // Validate price against trusted oracle
    uint256 priceX96 = (amount1 * 1e18) / amount0;
    // 30 min
    uint256 oraclePriceX96 = getPriceFromOracle(token0, token1, 1800);
    require(
        priceX96 >= (oraclePriceX96 * 95) / 100 && priceX96 <= (oraclePriceX96 * 105) / 100,
        "Price deviation too high"
    );

    uint160 sqrtPriceX96 = uint160(FixedPointMathLib.sqrt(priceX96) * 2**48);

    // Create the pool
    IUniswapV3(uniV3PositionManager).createAndInitializePoolIfNecessary(token0, token1,
        FEE_TIER, sqrtPriceX96);

    IERC20(token0).approve(uniV3PositionManager, amount0);
    IERC20(token1).approve(uniV3PositionManager, amount1);

    IUniswapV3.MintParams memory params = IUniswapV3.MintParams({
        token0: token0,
        token1: token1,
        fee: FEE_TIER,
        tickLower: MIN_TICK,
        tickUpper: MAX_TICK,
        amount0Desired: amount0,
        amount1Desired: amount1,
        amount0Min: 0,
        amount1Min: 0,
        recipient: address(this),
        deadline: block.timestamp
    });

    (positionId, liquidity, , ) = IUniswapV3(uniV3PositionManager).mint(params);
}

function getTwapFromOracle(
    address token0,
    address token1,
    uint32 secondsAgo
) public view returns (uint256 priceX96) {
    // Get the address of the pool
    address pool = IUniswapV3Factory(uniV3Factory).getPool(token0, token1, FEE_TIER);
    require(pool != address(0), "Pool does not exist");

    // Query the pool for the current and historical tick
    uint32;
    secondsAgos[0] = secondsAgo; // Start of the period
    secondsAgos[1] = 0; // End of the period (current time)

    // Fetch the tick cumulative values from the pool
    (int56[] memory tickCumulatives, ) = IUniswapV3Pool(pool).observe(secondsAgos);

    // Calculate the average tick over the time period
    int56 tickCumulativeDelta = tickCumulatives[1] - tickCumulatives[0];
    int24 averageTick = int24(tickCumulativeDelta / int56(int32(secondsAgo)));

    // Convert the average tick to sqrtPriceX96
    uint160 sqrtPriceX96 = TickMath.getSqrtRatioAtTick(averageTick);

    // Calculate the price using the sqrtPriceX96
    uint256 price = (uint256(sqrtPriceX96) * uint256(sqrtPriceX96)) / (1 << 192);

    // Return the price in X96 format
    return price;
}
```
[x] Fixed in later version

### Same for function _collectFees(address memeToken, uint256 positionId, bool isNativeFirst) internal (critical)
```
Yes, the collect function in Uniswap V3, which retrieves the tokens owed to the position based on the accrued fees, can potentially be affected by external factors like a flashloan if the pool's reserves have been manipulated. However, this depends on how and when the function is called. 
Mitigation Strategies:
To minimize the risks associated with flashloan attacks or other manipulations, consider the following:

1. Use Time-Weighted Average Prices (TWAPs)
How It Helps:
TWAPs mitigate the impact of short-term price manipulation by averaging the price over a specified time frame.
Before calling collect, you can check the pool's TWAP and compare it to the instant price. If the deviation exceeds a threshold, delay the operation.
2. Check Pool State Consistency
How It Helps:
Before calling collect, validate the pool's current state against historical data (e.g., previous reserves or price).
Reject the operation if the state deviates significantly.
3. Time-Locking Operations
How It Helps:
Enforce a minimum delay between critical pool interactions (e.g., minting liquidity, swapping, or collecting fees).
This reduces the attacker's ability to exploit a manipulated state within a single transaction or block.
4. Verify Reserves and Trades
How It Helps:
Before calling collect, check the pool's reserves to ensure they haven't been manipulated significantly (e.g., large reserve changes relative to historical averages).
Thanks, ChatGPT 4o mini to loang discussion.
```
or code:
```
function safeCollect(
    uint256 tokenId,
    address recipient,
    uint128 amount0Max,
    uint128 amount1Max
) external {
    // Verify pool reserves before proceeding
    address pool = IUniswapV3Pool(factory.getPool(token0, token1, FEE_TIER));
    require(pool != address(0), "Pool does not exist");

    // Get current pool reserves
    (uint160 sqrtPriceX96, , , , , , ) = IUniswapV3Pool(pool).slot0();

    // Check TWAP or historical data
    uint256 twapPrice = getTwapFromOracle(token0, token1, 1800); // 30-minute TWAP
    uint256 instantPrice = (uint256(sqrtPriceX96) * uint256(sqrtPriceX96)) / (1 << 192);

    uint256 deviation = (instantPrice > twapPrice)
        ? ((instantPrice - twapPrice) * 1e18) / twapPrice
        : ((twapPrice - instantPrice) * 1e18) / twapPrice;

    require(deviation <= maxAllowedDeviation, "Price deviation too high");

    // Proceed with the collect operation
    IUniswapV3(uniV3PositionManager).collect(
        IUniswapV3.CollectParams({
            tokenId: tokenId,
            recipient: recipient,
            amount0Max: amount0Max,
            amount1Max: amount1Max
        })
    );
}
```
[x] Fixed in later version

### Low issue: Oracle not finished?
```
Unclear about oracles. They simply exist as separate contracts. Needed proxy pattern for oracle?
```
[x] Noted for later versions