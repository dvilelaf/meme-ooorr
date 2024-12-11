# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `3c7c861ec774e2cc4efb2daeeb48343e2a927499` or `v0.2.0-internal-audit3` <br>

## Objectives
The audit focused on Meme* contracts <BR>

## Issue
Not new issue in https://github.com/dvilelaf/meme-ooorr/pull/22/commits/9d725bf5ad9df14e537b97a98ccc05ae031b2843

### Notes
```
Double testing
        // Ensure token order matches Uniswap convention
        (address token0, address token1, uint256 amount0, uint256 amount1) = isNativeFirst
            ? (nativeToken, memeToken, nativeTokenAmount, memeTokenAmount)
            : (memeToken, nativeToken, memeTokenAmount, nativeTokenAmount);

        // Calculate the price ratio (amount1 / amount0) scaled by 1e18 to avoid floating point issues
        uint256 priceX96 = (amount1 * 1e18) / amount0;
```
[x] Verified

## Fixing TODO
```
int24 public constant MIN_TICK = -887200; // TODO: double check

Solution:
Uniswap v3 pools have a tick range from a minimum of -887272 to a maximum of 887272.
Let Fee tier % = 1%
Then Tick-spacing = 200 (* table in https://support.uniswap.org/hc/en-us/articles/21069524840589-What-is-a-tick-when-providing-liquidity)
Formula 1: 
tick % Tick-spacing = 0 (* By definition: Tick spacing sets the minimum distance between ticks for adding or removing liquidity.)
We need to find x that satisfies two equations:
a) x % 200 = 0
b) x < 887272
x = 887200
For full range:
MIN_TICK = -|x|
MAX_TICK = |x|

Refences:
https://support.uniswap.org/hc/en-us/articles/21069524840589-What-is-a-tick-when-providing-liquidity
https://support.uniswap.org/hc/en-us/articles/7423663459597-Why-does-the-price-input-automatically-round
https://medium.com/@jaysojitra1011/uniswap-v3-deep-dive-visualizing-ticks-and-liquidity-provisioning-part-3-081db166243b
```
[x] Confirmed, does not need update
