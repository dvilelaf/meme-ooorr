# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `606acf4ed03c9d66a48e38abe0bce614feaf5ee5` or `tag: v0.0.1-pre-internal-audit` <br>

## Objectives
The audit focused on Meme* contracts <BR>

### Flatten version
Flatten version of contracts. [contracts](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal/analysis/contracts)

### Security issues
Details in [slither_full](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal/analysis/slither_full.txt) <br>
All false positive.

## Issue
## Critical issue
### scheduleOLASForAscendance() needs Oracle for price
```
Needing re-design with TWAP Oracle
        // TODO: needs oracle integration
        // Apply 3% slippage protection
        uint256 limit = _getLowSlippageSafeSwapAmount();
This is correctly reflected in TODO
``` 
### Medium issue
#### Not check that this LP token doesn't exist, DOS if exist
```
    function _createUniswapPair(
        address memeToken,
        uint256 nativeTokenAmount,
        uint256 memeTokenAmount
    ) internal returns (address pair, uint256 liquidity) {
        _wrap(nativeTokenAmount);

        // TODO Check that this LP token doesn't exist
        // TODO What to do if it exists: add liquidity if one exists, otherwise create it
        // TODO try-catch
        // Create the LP
        pair = IUniswap(factory).createPair(nativeToken, memeToken);
        Please, fixing TODO
```
[x] Fixed

#### All critical functions from the FSM that should only be called once must be guaranteed to be called only once. This must be explicitly checked.
```
        Example of bad design:

        function unleashThisMeme(address memeToken) external = must be called only once for every memeToken
        // Zero the allocation
        ...
        uint256 hearterContribution = memeHearters[memeToken][msg.sender]; 
        if(earterContribution > 0) {
            ... inside internal function

            memeHearters[memeToken][msg.sender] = 0;
        }
        So, we needed sure:
        1. t0: unleashThisMeme(tkn1) - passed
        2. t1: unleashThisMeme(tkn1) - revert
        3. t2: unleashThisMeme(tkn2) - passed
    This should be true for all functions from FSM:
    - summonThisMem -> heartThisMeme -> unleashThisMeme -> collectThisMeme (optional) -> purgeThisMeme

    By code: race between collectThisMeme and purgeThisMeme. to discussion
```
[x] Fixed

### Low issue
#### Rare case = don't create()
```
function summonThisMeme(
            // Create a new token
        Meme newTokenInstance = new Meme(name, symbol, DECIMALS, totalSupply);
        address memeToken = address(newTokenInstance);
        +
        require(memeToken != address(0), "Token creation failed"); // This is redundant but good for clarity
```
[x] Fixed

#### Confusing name of variable lpTokenAmount
```
uint256 heartersAmount = totalSupply - lpTokenAmount;
Because it is NOT amount of LP token.
```
[x] Fixed
