# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `c6e6b55012c3bc18f8b7d848f4e6243f4b3881bd` or `v0.2.0-internal-audit4` <br>

## Objectives
The audit focused on Meme* contracts <BR>

## Issue medium? low?
### olasLeftovers It's not clear what happens to them next.
```
    function _bridgeAndBurn(
        uint256 olasAmount,
        uint256,
        bytes memory
    ) internal virtual override returns (uint256 leftovers) {
        // Get OLAS leftovers from previous transfers and adjust the amount to transfer
        olasAmount += olasLeftovers;

        // Round transfer amount to the cutoff value
        uint256 transferAmount = olasAmount / WORMHOLE_BRIDGING_CUTOFF;
        transferAmount *= WORMHOLE_BRIDGING_CUTOFF;

        // Check for zero value
        require(transferAmount > 0, "Amount is too small for bridging");

        // Update OLAS leftovers
        olasLeftovers = olasAmount - transferAmount;
```
[x] Discussed, all fine

### Low, CEI - Check before interaction
```
        // Apply slippage protection
        require(IOracle(oracle).validatePrice(maxSlippage), "Slippage limit is breached"); move to top
```
[x] Fixed

### To discussion UniswapPriceOracle. IMO no change code
```
    /// @dev Validates the current price against a TWAP according to slippage tolerance.
    /// @param slippage the acceptable slippage tolerance
    function validatePrice(uint256 slippage) external view returns (bool) {
        require(slippage <= maxSlippage, "Slippage overflow");

        // Compute time-weighted average price
        // Fetch the cumulative prices from the pair
        uint256 cumulativePriceLast;
        if (direction == 0) {
            cumulativePriceLast = IUniswapV2(pair).price1CumulativeLast();
        } else {
            cumulativePriceLast = IUniswapV2(pair).price0CumulativeLast();
        }

        // Fetch the reserves and the last block timestamp
        (, , uint256 blockTimestampLast) = IUniswapV2(pair).getReserves();

        // Require at least one block since last update
        if (block.timestamp == blockTimestampLast) {
            return false;
        }
        uint256 elapsedTime = block.timestamp - blockTimestampLast;

        ??? elapsedTime > minElapsedTime - Current logic allows any time interval.
        On the other hand, if we put a barrier, we will create a trap for ourselves, that any price update through swap will block it.
        IMO: better code as is.
```
[x] Noted

## Notes to TODO
```
Let Oracle (Balancer) update independently. No needed 
        // TODO Check if needed
        // Update prices in oracle
        //IOracle(oracle).updatePrice();
```
[x] Fixed