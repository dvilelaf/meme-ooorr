# meme-ooorr
The review has been performed based on the contract code in the following repository:<br>
`https://github.com/dvilelaf/meme-ooorr` <br>
commit: `9b427618db7bd233651476de9abe12c18fbd236a` or `v0.2.0-internal-audit2` <br>

## Objectives
The audit focused on Meme* contracts <BR>

### Flatten version
Flatten version of contracts. [contracts](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal3/analysis/contracts)

### Security issues
Details in [slither_full](https://github.com/dvilelaf/meme-ooorr/blob/main/audits/internal3/analysis/slither_full.txt) <br>
All false positive.

## Issues
### Medium? Critical?: to discussion, sandwich attack
```
attaсker contract => function unleashThisMeme => _createThisMeme => 
bytes32 randomNonce = keccak256(abi.encodePacked(block.timestamp, block.prevrandao, msg.sender, memeNonce));
        randomNonce = keccak256(abi.encodePacked(randomNonce));
Can be calculated in the attacking contract (because deterministic in same block)
Can predict: memeToken := create2(0x0, add(0x20, payload), mload(payload), memeNonce)
Call before own contract:
        // Calculate the price ratio (amount1 / amount0) scaled by 1e18 to avoid floating point issues
        uint256 priceX96 = (amount1 * 1e18) / amount0;

        // Calculate the square root of the price ratio in X96 format
        uint160 sqrtPriceX96 = uint160((FixedPointMathLib.sqrt(priceX96) * (1 << 96)) / 1e9);

        // Create a pool
        IUniswapV3(uniV3PositionManager).createAndInitializePoolIfNecessary(token0, token1, FEE_TIER, sqrtPriceX96);
So, we must revert if pool exist at moment unleashThisMeme        
```
[x] Fixed

### Lown issue: group internal function
```
Internal functions are mixed with public ones, which makes it difficult to understand contracts.
```
[x] Fixed

### Low issue: checking name, symbol. Not requrments ERC20
```
function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Check for minimum native token value
        require(msg.value >= minNativeTokenValue, "Minimum native token value is required to summon");
        // Check for minimum total supply
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Minimum total supply is not met");
        // Check for max total supply as to practical limits for the Uniswap LP creation
        require(totalSupply < type(uint128).max, "Maximum total supply overflow");

        uint256 memeNonce = _nonce;

        // Initiate meme nonce map values
        memeSummons[memeNonce] = MemeSummon(name, symbol, totalSupply, msg.value, block.timestamp, 0, 0, 0, false);

        Checking name != "" and symbol != ""
        Many dApps and platforms (like Uniswap, Etherscan, etc.) expect name/symbol functions to be implemented and return meaningful values.
```
[x] Fixed

### Low issue: Remove block.prevrandao from randomNonce
```
Observation:
block.prevrandao replaced block.difficulty after the Merge, as Proof-of-Stake (PoS) rendered block.difficulty meaningless.
It provides the random value from the previous block, derived from the beacon chain.

bytes32 randomNonce = keccak256(abi.encodePacked(block.timestamp, block.prevrandao, msg.sender, memeNonce));
remove block.prevrandao for sure compatible with ANY evm-like networks (include rollups, non mainnet-L1)
On some L2s, block.prevrandao may return a fixed value (e.g., 0). 
```
[x] Fixed

