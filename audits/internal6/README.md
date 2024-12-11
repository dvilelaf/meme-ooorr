# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `c2d85cf3279c5a50b4367df75f03cb39106867b32` or `v0.2.0-internal-audit5` <br>

## Objectives
The audit focused on BBB* contracts <BR>

## Issue
### Medium: inf activity from nothing for UniswapPriceOracle.
```
mapAccountActivities[msg.sender]++;
remove updatePrice or return false.

    /// @dev Triggers oracle price update.
    function updateOraclePrice() external {
        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Update price
        bool success = IOracle(oracle).updatePrice();
        require(success, "Oracle price update failed");

        emit OraclePriceUpdated(oracle, msg.sender);
    }
        /// @dev Updates the time-weighted average price.
    function updatePrice() external pure returns (bool) {
        // Nothing to update; use built-in TWAP from Uniswap V2 pool
        return true;
    }
```
[x] Fixed

### Low - no checking fee. 
```
May lead to artificial activity through the withdrawal of zeros fee
function _collectFees(address memeToken, uint256 positionId, bool isNativeFirst) internal {
        (address token0, address token1) = isNativeFirst ? (nativeToken, memeToken) : (memeToken, nativeToken);

        // Check current pool prices
        IBuyBackBurner(buyBackBurner).checkPoolPrices(token0, token1, uniV3PositionManager, FEE_TIER);

        IUniswapV3.CollectParams memory params = IUniswapV3.CollectParams({
            tokenId: positionId,
            recipient: address(this),
            amount0Max: type(uint128).max,
            amount1Max: type(uint128).max
        });

        // Get the corresponding tokens
        (uint256 amount0, uint256 amount1) = IUniswapV3(uniV3PositionManager).collect(params);
        //require(amount0 > 0 || amount1 > 0, "No rewards");
Improve:
        (address token0, address token1) = isNativeFirst ? (nativeToken, memeToken) : (memeToken, nativeToken);

    // Check position to ensure there are fees to collect
    (, , , , , , , uint128 liquidity, uint256 feeGrowthInside0LastX128, uint256 feeGrowthInside1LastX128, , ) = IUniswapV3(uniV3PositionManager).positions(positionId);

    require(liquidity > 0, "No liquidity in position");
    require(feeGrowthInside0LastX128 > 0 || feeGrowthInside1LastX128 > 0, "No fees available to collect");

+
    require(amount0 > 0 || amount1 > 0, "No rewards");
```
[x] Fixed

### Remove console.log in prod.
```
        console.log("tradePrice", tradePrice);
```
[]
