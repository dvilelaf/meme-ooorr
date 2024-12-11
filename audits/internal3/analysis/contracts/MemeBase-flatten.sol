// Sources flattened with hardhat v2.22.15 https://hardhat.org

// SPDX-License-Identifier: MIT

pragma solidity >=0.8.0;

/// @notice Modern and gas efficient ERC20 + EIP-2612 implementation.
/// @author Solmate (https://github.com/Rari-Capital/solmate/blob/main/src/tokens/ERC20.sol)
/// @author Modified from Uniswap (https://github.com/Uniswap/uniswap-v2-core/blob/master/contracts/UniswapV2ERC20.sol)
/// @dev Do not manually set balances without updating totalSupply, as the sum of all user balances must not exceed it.
abstract contract ERC20 {
    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    event Transfer(address indexed from, address indexed to, uint256 amount);

    event Approval(address indexed owner, address indexed spender, uint256 amount);

    /*//////////////////////////////////////////////////////////////
                            METADATA STORAGE
    //////////////////////////////////////////////////////////////*/

    string public name;

    string public symbol;

    uint8 public immutable decimals;

    /*//////////////////////////////////////////////////////////////
                              ERC20 STORAGE
    //////////////////////////////////////////////////////////////*/

    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;

    mapping(address => mapping(address => uint256)) public allowance;

    /*//////////////////////////////////////////////////////////////
                            EIP-2612 STORAGE
    //////////////////////////////////////////////////////////////*/

    uint256 internal immutable INITIAL_CHAIN_ID;

    bytes32 internal immutable INITIAL_DOMAIN_SEPARATOR;

    mapping(address => uint256) public nonces;

    /*//////////////////////////////////////////////////////////////
                               CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    constructor(
        string memory _name,
        string memory _symbol,
        uint8 _decimals
    ) {
        name = _name;
        symbol = _symbol;
        decimals = _decimals;

        INITIAL_CHAIN_ID = block.chainid;
        INITIAL_DOMAIN_SEPARATOR = computeDomainSeparator();
    }

    /*//////////////////////////////////////////////////////////////
                               ERC20 LOGIC
    //////////////////////////////////////////////////////////////*/

    function approve(address spender, uint256 amount) public virtual returns (bool) {
        allowance[msg.sender][spender] = amount;

        emit Approval(msg.sender, spender, amount);

        return true;
    }

    function transfer(address to, uint256 amount) public virtual returns (bool) {
        balanceOf[msg.sender] -= amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(msg.sender, to, amount);

        return true;
    }

    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) public virtual returns (bool) {
        uint256 allowed = allowance[from][msg.sender]; // Saves gas for limited approvals.

        if (allowed != type(uint256).max) allowance[from][msg.sender] = allowed - amount;

        balanceOf[from] -= amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(from, to, amount);

        return true;
    }

    /*//////////////////////////////////////////////////////////////
                             EIP-2612 LOGIC
    //////////////////////////////////////////////////////////////*/

    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) public virtual {
        require(deadline >= block.timestamp, "PERMIT_DEADLINE_EXPIRED");

        // Unchecked because the only math done is incrementing
        // the owner's nonce which cannot realistically overflow.
        unchecked {
            address recoveredAddress = ecrecover(
                keccak256(
                    abi.encodePacked(
                        "\x19\x01",
                        DOMAIN_SEPARATOR(),
                        keccak256(
                            abi.encode(
                                keccak256(
                                    "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
                                ),
                                owner,
                                spender,
                                value,
                                nonces[owner]++,
                                deadline
                            )
                        )
                    )
                ),
                v,
                r,
                s
            );

            require(recoveredAddress != address(0) && recoveredAddress == owner, "INVALID_SIGNER");

            allowance[recoveredAddress][spender] = value;
        }

        emit Approval(owner, spender, value);
    }

    function DOMAIN_SEPARATOR() public view virtual returns (bytes32) {
        return block.chainid == INITIAL_CHAIN_ID ? INITIAL_DOMAIN_SEPARATOR : computeDomainSeparator();
    }

    function computeDomainSeparator() internal view virtual returns (bytes32) {
        return
            keccak256(
                abi.encode(
                    keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                    keccak256(bytes(name)),
                    keccak256("1"),
                    block.chainid,
                    address(this)
                )
            );
    }

    /*//////////////////////////////////////////////////////////////
                        INTERNAL MINT/BURN LOGIC
    //////////////////////////////////////////////////////////////*/

    function _mint(address to, uint256 amount) internal virtual {
        totalSupply += amount;

        // Cannot overflow because the sum of all user
        // balances can't exceed the max uint256 value.
        unchecked {
            balanceOf[to] += amount;
        }

        emit Transfer(address(0), to, amount);
    }

    function _burn(address from, uint256 amount) internal virtual {
        balanceOf[from] -= amount;

        // Cannot underflow because a user's balance
        // will never be larger than the total supply.
        unchecked {
            totalSupply -= amount;
        }

        emit Transfer(from, address(0), amount);
    }
}


// File contracts/Meme.sol

contract Meme is ERC20 {
    constructor(
        string memory _name,
        string memory _symbol,
        uint8 _decimals,
        uint256 _totalSupply
    ) ERC20(_name, _symbol, _decimals) {
        _mint(msg.sender, _totalSupply);
    }

    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }
}


interface IUniswapV3 {
    /// @notice Creates a new pool if it does not exist, then initializes if not initialized
    /// @dev This method can be bundled with others via IMulticall for the first action (e.g. mint) performed against a pool
    /// @param token0 The contract address of token0 of the pool
    /// @param token1 The contract address of token1 of the pool
    /// @param fee The fee amount of the v3 pool for the specified token pair
    /// @param sqrtPriceX96 The initial square root price of the pool as a Q64.96 value
    /// @return pool Returns the pool address based on the pair of tokens and fee, will return the newly created pool address if necessary
    function createAndInitializePoolIfNecessary(address token0, address token1, uint24 fee, uint160 sqrtPriceX96)
        external payable returns (address pool);

    struct MintParams {
        address token0;
        address token1;
        uint24 fee;
        int24 tickLower;
        int24 tickUpper;
        uint256 amount0Desired;
        uint256 amount1Desired;
        uint256 amount0Min;
        uint256 amount1Min;
        address recipient;
        uint256 deadline;
    }

    /// @notice Creates a new position wrapped in a NFT
    /// @dev Call this when the pool does exist and is initialized. Note that if the pool is created but not initialized
    /// a method does not exist, i.e. the pool is assumed to be initialized.
    /// @param params The params necessary to mint a position, encoded as `MintParams` in calldata
    /// @return tokenId The ID of the token that represents the minted position
    /// @return liquidity The amount of liquidity for this position
    /// @return amount0 The amount of token0
    /// @return amount1 The amount of token1
    function mint(MintParams calldata params) external payable
        returns (
            uint256 tokenId,
            uint128 liquidity,
            uint256 amount0,
            uint256 amount1
        );

    struct CollectParams {
        uint256 tokenId;
        address recipient;
        uint128 amount0Max;
        uint128 amount1Max;
    }

    /// @notice Collects up to a maximum amount of fees owed to a specific position to the recipient
    /// @param params tokenId The ID of the NFT for which tokens are being collected,
    /// recipient The account that should receive the tokens,
    /// amount0Max The maximum amount of token0 to collect,
    /// amount1Max The maximum amount of token1 to collect
    /// @return amount0 The amount of fees collected in token0
    /// @return amount1 The amount of fees collected in token1
    function collect(CollectParams calldata params) external payable returns (uint256 amount0, uint256 amount1);

    /// @notice Returns the pool address for a given pair of tokens and a fee, or address 0 if it does not exist
    /// @dev tokenA and tokenB may be passed in either token0/token1 or token1/token0 order
    /// @param tokenA The contract address of either token0 or token1
    /// @param tokenB The contract address of the other token
    /// @param fee The fee collected upon every swap in the pool, denominated in hundredths of a bip
    /// @return pool The pool address
    function getPool(address tokenA, address tokenB, uint24 fee) external view returns (address pool);

    /// @notice The 0th storage slot in the pool stores many values, and is exposed as a single method to save gas
    /// when accessed externally.
    /// @return sqrtPriceX96 The current price of the pool as a sqrt(token1/token0) Q64.96 value
    /// tick The current tick of the pool, i.e. according to the last tick transition that was run.
    /// This value may not always be equal to SqrtTickMath.getTickAtSqrtRatio(sqrtPriceX96) if the price is on a tick
    /// boundary.
    /// observationIndex The index of the last oracle observation that was written,
    /// observationCardinality The current maximum number of observations stored in the pool,
    /// observationCardinalityNext The next maximum number of observations, to be updated when the observation.
    /// feeProtocol The protocol fee for both tokens of the pool.
    /// Encoded as two 4 bit values, where the protocol fee of token1 is shifted 4 bits and the protocol fee of token0
    /// is the lower 4 bits. Used as the denominator of a fraction of the swap fee, e.g. 4 means 1/4th of the swap fee.
    /// unlocked Whether the pool is currently locked to reentrancy
    function slot0() external view
        returns (
            uint160 sqrtPriceX96,
            int24 tick,
            uint16 observationIndex,
            uint16 observationCardinality,
            uint16 observationCardinalityNext,
            uint8 feeProtocol,
            bool unlocked
        );

    /// @notice Returns the cumulative tick and liquidity as of each timestamp `secondsAgo` from the current block timestamp
    /// @dev To get a time weighted average tick or liquidity-in-range, you must call this with two values, one representing
    /// the beginning of the period and another for the end of the period. E.g., to get the last hour time-weighted average tick,
    /// you must call it with secondsAgos = [3600, 0].
    /// @dev The time weighted average tick represents the geometric time weighted average price of the pool, in
    /// log base sqrt(1.0001) of token1 / token0. The TickMath library can be used to go from a tick value to a ratio.
    /// @param secondsAgos From how long ago each cumulative tick and liquidity value should be returned
    /// @return tickCumulatives Cumulative tick values as of each `secondsAgos` from the current block timestamp
    /// @return secondsPerLiquidityCumulativeX128s Cumulative seconds per liquidity-in-range value as of each `secondsAgos` from the current block
    /// timestamp
    function observe(uint32[] calldata secondsAgos)
        external view returns (int56[] memory tickCumulatives, uint160[] memory secondsPerLiquidityCumulativeX128s);

    function factory() external view returns (address);
}


/// @notice Arithmetic library with operations for fixed-point numbers.
/// @author Solmate (https://github.com/Rari-Capital/solmate/blob/main/src/utils/FixedPointMathLib.sol)
library FixedPointMathLib {
    /*//////////////////////////////////////////////////////////////
                    SIMPLIFIED FIXED POINT OPERATIONS
    //////////////////////////////////////////////////////////////*/

    uint256 internal constant WAD = 1e18; // The scalar of ETH and most ERC20s.

    function mulWadDown(uint256 x, uint256 y) internal pure returns (uint256) {
        return mulDivDown(x, y, WAD); // Equivalent to (x * y) / WAD rounded down.
    }

    function mulWadUp(uint256 x, uint256 y) internal pure returns (uint256) {
        return mulDivUp(x, y, WAD); // Equivalent to (x * y) / WAD rounded up.
    }

    function divWadDown(uint256 x, uint256 y) internal pure returns (uint256) {
        return mulDivDown(x, WAD, y); // Equivalent to (x * WAD) / y rounded down.
    }

    function divWadUp(uint256 x, uint256 y) internal pure returns (uint256) {
        return mulDivUp(x, WAD, y); // Equivalent to (x * WAD) / y rounded up.
    }

    function powWad(int256 x, int256 y) internal pure returns (int256) {
        // Equivalent to x to the power of y because x ** y = (e ** ln(x)) ** y = e ** (ln(x) * y)
        return expWad((lnWad(x) * y) / int256(WAD)); // Using ln(x) means x must be greater than 0.
    }

    function expWad(int256 x) internal pure returns (int256 r) {
        unchecked {
            // When the result is < 0.5 we return zero. This happens when
            // x <= floor(log(0.5e18) * 1e18) ~ -42e18
            if (x <= -42139678854452767551) return 0;

            // When the result is > (2**255 - 1) / 1e18 we can not represent it as an
            // int. This happens when x >= floor(log((2**255 - 1) / 1e18) * 1e18) ~ 135.
            if (x >= 135305999368893231589) revert("EXP_OVERFLOW");

            // x is now in the range (-42, 136) * 1e18. Convert to (-42, 136) * 2**96
            // for more intermediate precision and a binary basis. This base conversion
            // is a multiplication by 1e18 / 2**96 = 5**18 / 2**78.
            x = (x << 78) / 5**18;

            // Reduce range of x to (-½ ln 2, ½ ln 2) * 2**96 by factoring out powers
            // of two such that exp(x) = exp(x') * 2**k, where k is an integer.
            // Solving this gives k = round(x / log(2)) and x' = x - k * log(2).
            int256 k = ((x << 96) / 54916777467707473351141471128 + 2**95) >> 96;
            x = x - k * 54916777467707473351141471128;

            // k is in the range [-61, 195].

            // Evaluate using a (6, 7)-term rational approximation.
            // p is made monic, we'll multiply by a scale factor later.
            int256 y = x + 1346386616545796478920950773328;
            y = ((y * x) >> 96) + 57155421227552351082224309758442;
            int256 p = y + x - 94201549194550492254356042504812;
            p = ((p * y) >> 96) + 28719021644029726153956944680412240;
            p = p * x + (4385272521454847904659076985693276 << 96);

            // We leave p in 2**192 basis so we don't need to scale it back up for the division.
            int256 q = x - 2855989394907223263936484059900;
            q = ((q * x) >> 96) + 50020603652535783019961831881945;
            q = ((q * x) >> 96) - 533845033583426703283633433725380;
            q = ((q * x) >> 96) + 3604857256930695427073651918091429;
            q = ((q * x) >> 96) - 14423608567350463180887372962807573;
            q = ((q * x) >> 96) + 26449188498355588339934803723976023;

            assembly {
                // Div in assembly because solidity adds a zero check despite the unchecked.
                // The q polynomial won't have zeros in the domain as all its roots are complex.
                // No scaling is necessary because p is already 2**96 too large.
                r := sdiv(p, q)
            }

            // r should be in the range (0.09, 0.25) * 2**96.

            // We now need to multiply r by:
            // * the scale factor s = ~6.031367120.
            // * the 2**k factor from the range reduction.
            // * the 1e18 / 2**96 factor for base conversion.
            // We do this all at once, with an intermediate result in 2**213
            // basis, so the final right shift is always by a positive amount.
            r = int256((uint256(r) * 3822833074963236453042738258902158003155416615667) >> uint256(195 - k));
        }
    }

    function lnWad(int256 x) internal pure returns (int256 r) {
        unchecked {
            require(x > 0, "UNDEFINED");

            // We want to convert x from 10**18 fixed point to 2**96 fixed point.
            // We do this by multiplying by 2**96 / 10**18. But since
            // ln(x * C) = ln(x) + ln(C), we can simply do nothing here
            // and add ln(2**96 / 10**18) at the end.

            // Reduce range of x to (1, 2) * 2**96
            // ln(2^k * x) = k * ln(2) + ln(x)
            int256 k = int256(log2(uint256(x))) - 96;
            x <<= uint256(159 - k);
            x = int256(uint256(x) >> 159);

            // Evaluate using a (8, 8)-term rational approximation.
            // p is made monic, we will multiply by a scale factor later.
            int256 p = x + 3273285459638523848632254066296;
            p = ((p * x) >> 96) + 24828157081833163892658089445524;
            p = ((p * x) >> 96) + 43456485725739037958740375743393;
            p = ((p * x) >> 96) - 11111509109440967052023855526967;
            p = ((p * x) >> 96) - 45023709667254063763336534515857;
            p = ((p * x) >> 96) - 14706773417378608786704636184526;
            p = p * x - (795164235651350426258249787498 << 96);

            // We leave p in 2**192 basis so we don't need to scale it back up for the division.
            // q is monic by convention.
            int256 q = x + 5573035233440673466300451813936;
            q = ((q * x) >> 96) + 71694874799317883764090561454958;
            q = ((q * x) >> 96) + 283447036172924575727196451306956;
            q = ((q * x) >> 96) + 401686690394027663651624208769553;
            q = ((q * x) >> 96) + 204048457590392012362485061816622;
            q = ((q * x) >> 96) + 31853899698501571402653359427138;
            q = ((q * x) >> 96) + 909429971244387300277376558375;
            assembly {
                // Div in assembly because solidity adds a zero check despite the unchecked.
                // The q polynomial is known not to have zeros in the domain.
                // No scaling required because p is already 2**96 too large.
                r := sdiv(p, q)
            }

            // r is in the range (0, 0.125) * 2**96

            // Finalization, we need to:
            // * multiply by the scale factor s = 5.549…
            // * add ln(2**96 / 10**18)
            // * add k * ln(2)
            // * multiply by 10**18 / 2**96 = 5**18 >> 78

            // mul s * 5e18 * 2**96, base is now 5**18 * 2**192
            r *= 1677202110996718588342820967067443963516166;
            // add ln(2) * k * 5e18 * 2**192
            r += 16597577552685614221487285958193947469193820559219878177908093499208371 * k;
            // add ln(2**96 / 10**18) * 5e18 * 2**192
            r += 600920179829731861736702779321621459595472258049074101567377883020018308;
            // base conversion: mul 2**18 / 2**192
            r >>= 174;
        }
    }

    /*//////////////////////////////////////////////////////////////
                    LOW LEVEL FIXED POINT OPERATIONS
    //////////////////////////////////////////////////////////////*/

    function mulDivDown(
        uint256 x,
        uint256 y,
        uint256 denominator
    ) internal pure returns (uint256 z) {
        assembly {
            // Store x * y in z for now.
            z := mul(x, y)

            // Equivalent to require(denominator != 0 && (x == 0 || (x * y) / x == y))
            if iszero(and(iszero(iszero(denominator)), or(iszero(x), eq(div(z, x), y)))) {
                revert(0, 0)
            }

            // Divide z by the denominator.
            z := div(z, denominator)
        }
    }

    function mulDivUp(
        uint256 x,
        uint256 y,
        uint256 denominator
    ) internal pure returns (uint256 z) {
        assembly {
            // Store x * y in z for now.
            z := mul(x, y)

            // Equivalent to require(denominator != 0 && (x == 0 || (x * y) / x == y))
            if iszero(and(iszero(iszero(denominator)), or(iszero(x), eq(div(z, x), y)))) {
                revert(0, 0)
            }

            // First, divide z - 1 by the denominator and add 1.
            // We allow z - 1 to underflow if z is 0, because we multiply the
            // end result by 0 if z is zero, ensuring we return 0 if z is zero.
            z := mul(iszero(iszero(z)), add(div(sub(z, 1), denominator), 1))
        }
    }

    function rpow(
        uint256 x,
        uint256 n,
        uint256 scalar
    ) internal pure returns (uint256 z) {
        assembly {
            switch x
            case 0 {
                switch n
                case 0 {
                    // 0 ** 0 = 1
                    z := scalar
                }
                default {
                    // 0 ** n = 0
                    z := 0
                }
            }
            default {
                switch mod(n, 2)
                case 0 {
                    // If n is even, store scalar in z for now.
                    z := scalar
                }
                default {
                    // If n is odd, store x in z for now.
                    z := x
                }

                // Shifting right by 1 is like dividing by 2.
                let half := shr(1, scalar)

                for {
                    // Shift n right by 1 before looping to halve it.
                    n := shr(1, n)
                } n {
                    // Shift n right by 1 each iteration to halve it.
                    n := shr(1, n)
                } {
                    // Revert immediately if x ** 2 would overflow.
                    // Equivalent to iszero(eq(div(xx, x), x)) here.
                    if shr(128, x) {
                        revert(0, 0)
                    }

                    // Store x squared.
                    let xx := mul(x, x)

                    // Round to the nearest number.
                    let xxRound := add(xx, half)

                    // Revert if xx + half overflowed.
                    if lt(xxRound, xx) {
                        revert(0, 0)
                    }

                    // Set x to scaled xxRound.
                    x := div(xxRound, scalar)

                    // If n is even:
                    if mod(n, 2) {
                        // Compute z * x.
                        let zx := mul(z, x)

                        // If z * x overflowed:
                        if iszero(eq(div(zx, x), z)) {
                            // Revert if x is non-zero.
                            if iszero(iszero(x)) {
                                revert(0, 0)
                            }
                        }

                        // Round to the nearest number.
                        let zxRound := add(zx, half)

                        // Revert if zx + half overflowed.
                        if lt(zxRound, zx) {
                            revert(0, 0)
                        }

                        // Return properly scaled zxRound.
                        z := div(zxRound, scalar)
                    }
                }
            }
        }
    }

    /*//////////////////////////////////////////////////////////////
                        GENERAL NUMBER UTILITIES
    //////////////////////////////////////////////////////////////*/

    function sqrt(uint256 x) internal pure returns (uint256 z) {
        assembly {
            let y := x // We start y at x, which will help us make our initial estimate.

            z := 181 // The "correct" value is 1, but this saves a multiplication later.

            // This segment is to get a reasonable initial estimate for the Babylonian method. With a bad
            // start, the correct # of bits increases ~linearly each iteration instead of ~quadratically.

            // We check y >= 2^(k + 8) but shift right by k bits
            // each branch to ensure that if x >= 256, then y >= 256.
            if iszero(lt(y, 0x10000000000000000000000000000000000)) {
                y := shr(128, y)
                z := shl(64, z)
            }
            if iszero(lt(y, 0x1000000000000000000)) {
                y := shr(64, y)
                z := shl(32, z)
            }
            if iszero(lt(y, 0x10000000000)) {
                y := shr(32, y)
                z := shl(16, z)
            }
            if iszero(lt(y, 0x1000000)) {
                y := shr(16, y)
                z := shl(8, z)
            }

            // Goal was to get z*z*y within a small factor of x. More iterations could
            // get y in a tighter range. Currently, we will have y in [256, 256*2^16).
            // We ensured y >= 256 so that the relative difference between y and y+1 is small.
            // That's not possible if x < 256 but we can just verify those cases exhaustively.

            // Now, z*z*y <= x < z*z*(y+1), and y <= 2^(16+8), and either y >= 256, or x < 256.
            // Correctness can be checked exhaustively for x < 256, so we assume y >= 256.
            // Then z*sqrt(y) is within sqrt(257)/sqrt(256) of sqrt(x), or about 20bps.

            // For s in the range [1/256, 256], the estimate f(s) = (181/1024) * (s+1) is in the range
            // (1/2.84 * sqrt(s), 2.84 * sqrt(s)), with largest error when s = 1 and when s = 256 or 1/256.

            // Since y is in [256, 256*2^16), let a = y/65536, so that a is in [1/256, 256). Then we can estimate
            // sqrt(y) using sqrt(65536) * 181/1024 * (a + 1) = 181/4 * (y + 65536)/65536 = 181 * (y + 65536)/2^18.

            // There is no overflow risk here since y < 2^136 after the first branch above.
            z := shr(18, mul(z, add(y, 65536))) // A mul() is saved from starting z at 181.

            // Given the worst case multiplicative error of 2.84 above, 7 iterations should be enough.
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))
            z := shr(1, add(z, div(x, z)))

            // If x+1 is a perfect square, the Babylonian method cycles between
            // floor(sqrt(x)) and ceil(sqrt(x)). This statement ensures we return floor.
            // See: https://en.wikipedia.org/wiki/Integer_square_root#Using_only_integer_division
            // Since the ceil is rare, we save gas on the assignment and repeat division in the rare case.
            // If you don't care whether the floor or ceil square root is returned, you can remove this statement.
            z := sub(z, lt(div(x, z), z))
        }
    }

    function log2(uint256 x) internal pure returns (uint256 r) {
        require(x > 0, "UNDEFINED");

        assembly {
            r := shl(7, lt(0xffffffffffffffffffffffffffffffff, x))
            r := or(r, shl(6, lt(0xffffffffffffffff, shr(r, x))))
            r := or(r, shl(5, lt(0xffffffff, shr(r, x))))
            r := or(r, shl(4, lt(0xffff, shr(r, x))))
            r := or(r, shl(3, lt(0xff, shr(r, x))))
            r := or(r, shl(2, lt(0xf, shr(r, x))))
            r := or(r, shl(1, lt(0x3, shr(r, x))))
            r := or(r, lt(0x1, shr(r, x)))
        }
    }

    function unsafeMod(uint256 x, uint256 y) internal pure returns (uint256 z) {
        assembly {
            // z will equal 0 if y is 0, unlike in Solidity where it will revert.
            z := mod(x, y)
        }
    }

    function unsafeDiv(uint256 x, uint256 y) internal pure returns (uint256 z) {
        assembly {
            // z will equal 0 if y is 0, unlike in Solidity where it will revert.
            z := div(x, y)
        }
    }

    /// @dev Will return 0 instead of reverting if y is zero.
    function unsafeDivUp(uint256 x, uint256 y) internal pure returns (uint256 z) {
        assembly {
            // Add 1 to x * y if x % y > 0.
            z := add(gt(mod(x, y), 0), div(x, y))
        }
    }
}


interface IBuyBackBurner {
    function checkPoolPrices(address nativeToken, address memeToken, address uniV3PositionManager, uint24 fee,
        uint256 allowedDeviation, bool isNativeFirst) external view;
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);

    /// @dev Transfers the token amount.
    /// @param to Address to transfer to.
    /// @param amount The amount to transfer.
    /// @return True if the function execution is successful.
    function transfer(address to, uint256 amount) external returns (bool);

    /// @dev Burns tokens.
    /// @param amount Token amount to burn.
    function burn(uint256 amount) external;
}

/// @title MemeFactory - a smart contract factory for Meme Token creation
/// @dev This contract let's:
///      1) Any msg.sender summons a meme by contributing at least 0.01 ETH (or equivalent native asset for other chains).
///      2) Within 24h of a meme being summoned, any msg.sender can heart a meme (thereby becoming a hearter).
///         This requires the msg.sender to send a non-zero ETH value, which gets recorded as a contribution.
///      3) After 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for
///         the meme and schedules the distribution of the rest of the tokens to the hearters, proportional to their
///         contributions.
///      4) After the meme is being unleashed any hearter can collect their share of the meme token.
///      5) After 24h of a meme being unleashed, any msg.sender can purge the uncollected meme token allocations of hearters.
/// @notice 10% of the ETH contributed to a meme gets retained upon unleashing of the meme, that can later be
///         converted to OLAS and scheduled for burning (on Ethereum mainnet). The remainder of the ETH contributed (90%)
///         is contributed to an LP, together with 50% of the token supply of the meme.
///         The remaining 50% of the meme token supply goes to hearters. The LP token is held forever by MemeBase,
///         guaranteeing lasting liquidity in the meme token.
///
///         Example:
///         - Agent Smith would summonThisMeme with arguments Smiths Army, SMTH, 1_000_000_000 and $500 worth of ETH
///         - Agent Brown would heartThisMeme with $250 worth of ETH
///         - Agent Jones would heartThisMeme with $250 worth of ETH
///         - Any agent, let's say Brown, would call unleashThisMeme. This would:
///             - create a liquidity pool with $SMTH:$ETH, containing 500_000_000 SMTH tokens and $900 worth of ETH
///             - schedule $100 worth of OLAS for burning on Ethereum mainnet
///             - Brown would receive 125_000_000 worth of $SMTH
///         - Agent Smith would collectThisMeme and receive 250_000_000 worth of $SMTH
///         - Agent Jones would forget to collectThisMeme
///         - Any agent would call purgeThisMeme, which would cause Agent Jones's allocation of 125_000_000 worth of
///           $SMTH to be burned.
abstract contract MemeFactory {
    event OLASJourneyToAscendance(uint256 amount);
    event Summoned(address indexed summoner, uint256 indexed memeNonce, uint256 nativeTokenContributed);
    event Hearted(address indexed hearter, uint256 indexed memeNonce, uint256 amount);
    event Unleashed(address indexed unleasher, address indexed memeToken, uint256 indexed lpTokenId,
        uint256 liquidity, uint256  nativeAmountForOLASBurn);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 remainingAmount);
    event FeesCollected(address indexed feeCollector, address indexed memeToken, uint256 nativeTokenAmount, uint256 memeTokenAmount);

    // Meme Summon struct
    struct MemeSummon {
        // Meme token name
        string name;
        // Meme token symbol
        string symbol;
        // Meme token total supply
        uint256 totalSupply;
        // Native token contributed to the meme launch
        uint256 nativeTokenContributed;
        // Summon timestamp
        uint256 summonTime;
        // Unleash timestamp
        uint256 unleashTime;
        // Finalized hearters amount
        uint256 heartersAmount;
        // UniswapV3 position token Id
        uint256 positionId;
        // Native token direction in the pool
        bool isNativeFirst;
    }

    // Version number
    string public constant VERSION = "0.2.0";
    // Total supply minimum value
    uint256 public constant MIN_TOTAL_SUPPLY = 1_000_000 ether;
    // Unleash delay after token summoning
    uint256 public constant UNLEASH_DELAY = 24 hours;
    // Collect delay after token unleashing
    uint256 public constant COLLECT_DELAY = 24 hours;
    // Percentage of OLAS to burn (10%)
    uint256 public constant OLAS_BURN_PERCENTAGE = 10;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public constant LP_PERCENTAGE = 50;
    // Max allowed price deviation for TWAP pool values (100 = 1%) in 1e18 format
    uint256 public constant MAX_ALLOWED_DEVIATION = 1e16;
    // Uniswap V3 fee tier of 1%
    uint24 public constant FEE_TIER = 10_000;
    /// @dev The minimum tick that corresponds to a selected fee tier
    int24 public constant MIN_TICK = -887200;
    /// @dev The maximum tick that corresponds to a selected fee tier
    int24 public constant MAX_TICK = -MIN_TICK;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Minimum value of native token deposit
    uint256 public immutable minNativeTokenValue;
    // OLAS token address
    address public immutable olas;
    // Native token address (ERC-20 equivalent)
    address public immutable nativeToken;
    // Uniswap V3 position manager address
    address public immutable uniV3PositionManager;
    // BuyBackBurner address
    address public immutable buyBackBurner;

    // Number of meme tokens
    uint256 public numTokens;
    // Native token (ERC-20) scheduled to be converted to OLAS for Ascendance
    uint256 public scheduledForAscendance;
    // Nonce
    uint256 internal _nonce = 1;
    // Reentrancy lock
    uint256 internal _locked = 1;
    // Launch tracker
    uint256 internal _launched = 1;

    // Map of meme nonce => Meme summon struct
    mapping(uint256 => MemeSummon) public memeSummons;
    // Map of mem nonce => (map of hearter => native token balance)
    mapping(uint256 => mapping(address => uint256)) public memeHearters;
    // Map of meme token address => Meme nonce
    mapping(address => uint256) public memeTokenNonces;
    // Map of account => activity counter
    mapping(address => uint256) public mapAccountActivities;
    // Set of all meme tokens created by this contract
    address[] public memeTokens;

    /// @dev MemeFactory constructor
    constructor(
        address _olas,
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue
    ) {
        olas = _olas;
        nativeToken = _nativeToken;
        uniV3PositionManager = _uniV3PositionManager;
        buyBackBurner = _buyBackBurner;
        minNativeTokenValue = _minNativeTokenValue;
    }

    /// @dev Creates native token + meme token LP and adds liquidity.
    /// @param memeToken Meme token address.
    /// @param nativeTokenAmount Native token amount.
    /// @param memeTokenAmount Meme token amount.
    /// @return positionId LP position token Id.
    /// @return liquidity Obtained LP liquidity.
    /// @return isNativeFirst Order of tokens in the pool.
    function _createUniswapPair(
        address memeToken,
        uint256 nativeTokenAmount,
        uint256 memeTokenAmount
    ) internal returns (uint256 positionId, uint256 liquidity, bool isNativeFirst) {
        if (nativeToken < memeToken) {
            isNativeFirst = true;
        }

        // Ensure token order matches Uniswap convention
        (address token0, address token1, uint256 amount0, uint256 amount1) = isNativeFirst
            ? (nativeToken, memeToken, nativeTokenAmount, memeTokenAmount)
            : (memeToken, nativeToken, memeTokenAmount, nativeTokenAmount);

        // Calculate the price ratio (amount1 / amount0) scaled by 1e18 to avoid floating point issues
        uint256 priceX96 = (amount1 * 1e18) / amount0;

        // Calculate the square root of the price ratio in X96 format
        uint160 sqrtPriceX96 = uint160((FixedPointMathLib.sqrt(priceX96) * (1 << 96)) / 1e9);

        // Create a pool
        IUniswapV3(uniV3PositionManager).createAndInitializePoolIfNecessary(token0, token1, FEE_TIER, sqrtPriceX96);

        // Approve tokens for router
        IERC20(token0).approve(uniV3PositionManager, amount0);
        IERC20(token1).approve(uniV3PositionManager, amount1);

        // Add native token + meme token liquidity
        IUniswapV3.MintParams memory params = IUniswapV3.MintParams({
            token0: token0,
            token1: token1,
            fee: FEE_TIER,
            tickLower: MIN_TICK,
            tickUpper: MAX_TICK,
            amount0Desired: amount0,
            amount1Desired: amount1,
            amount0Min: 0, // Accept any amount of token0
            amount1Min: 0, // Accept any amount of token1
            recipient: address(this),
            deadline: block.timestamp
        });

        (positionId, liquidity, amount0, amount1) = IUniswapV3(uniV3PositionManager).mint(params);

        // Schedule for ascendance leftovers from native token
        // Note that meme token leftovers will be purged via purgeThisMeme
        uint256 nativeLeftovers = isNativeFirst ? (nativeTokenAmount - amount0) : (nativeTokenAmount - amount1);
        if (nativeLeftovers > 0) {
            scheduledForAscendance += nativeLeftovers;
        }
    }

    /// @dev Collects fees from LP position, burns the meme token part and schedules for ascendance the native token part.
    /// @param memeToken Meme token address.
    /// @param positionId LP position ID.
    /// @param isNativeFirst Order of a native token in the pool.
    function _collectFees(address memeToken, uint256 positionId, bool isNativeFirst) internal {
        // Check current pool prices
        IBuyBackBurner(buyBackBurner).checkPoolPrices(nativeToken, memeToken, uniV3PositionManager, FEE_TIER,
            MAX_ALLOWED_DEVIATION, isNativeFirst);

        IUniswapV3.CollectParams memory params = IUniswapV3.CollectParams({
            tokenId: positionId,
            recipient: address(this),
            amount0Max: type(uint128).max,
            amount1Max: type(uint128).max
        });

        // Get the corresponding tokens
        (uint256 amount0, uint256 amount1) = IUniswapV3(uniV3PositionManager).collect(params);

        uint256 nativeAmountForOLASBurn;
        uint256 memeAmountToBurn;

        if (isNativeFirst) {
            nativeAmountForOLASBurn = amount0;
            memeAmountToBurn = amount1;
        } else {
            memeAmountToBurn = amount0;
            nativeAmountForOLASBurn = amount1;
        }

        // Burn meme tokens
        IERC20(memeToken).burn(memeAmountToBurn);

        // Schedule native token amount for ascendance
        scheduledForAscendance += nativeAmountForOLASBurn;

        emit FeesCollected(msg.sender, memeToken, nativeAmountForOLASBurn, memeAmountToBurn);
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    /// @param memeNonce Meme nonce.
    /// @param heartersAmount Total hearters meme token amount.
    /// @param hearterContribution Hearter contribution.
    /// @param totalNativeTokenCommitted Total native token contributed for the token launch.
    function _collectMemeToken(
        address memeToken,
        uint256 memeNonce,
        uint256 heartersAmount,
        uint256 hearterContribution,
        uint256 totalNativeTokenCommitted
    ) internal {
        // Allocate corresponding meme token amount to the hearter
        uint256 allocation = (heartersAmount * hearterContribution) / totalNativeTokenCommitted;

        // Zero the allocation
        memeHearters[memeNonce][msg.sender] = 0;

        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);
        
        // Transfer meme token amount to the msg.sender
        memeTokenInstance.transfer(msg.sender, allocation);

        emit Collected(msg.sender, memeToken, allocation);
    }

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @return adjustedAmount Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign() internal virtual returns (uint256 adjustedAmount);

    /// @dev Native token amount to wrap.
    /// @param nativeTokenAmount Native token amount to be wrapped.
    function _wrap(uint256 nativeTokenAmount) internal virtual;

    /// @dev Summons meme token.
    /// @param name Token name.
    /// @param symbol Token symbol.
    /// @param totalSupply Token total supply.
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
        memeHearters[memeNonce][msg.sender] = msg.value;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Update nonce
        _nonce = memeNonce + 1;

        emit Summoned(msg.sender, memeNonce, msg.value);
        emit Hearted(msg.sender, memeNonce, msg.value);

        _locked = 1;
    }
    
    /// @dev Hearts the meme token with native token contribution.
    /// @param memeNonce Meme token nonce.
    function heartThisMeme(uint256 memeNonce) external payable {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Check for zero value
        require(msg.value > 0, "Native token amount must be greater than zero");

        // Get meme summon info
        MemeSummon storage memeSummon = memeSummons[memeNonce];

        // Check that the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(memeSummon.unleashTime == 0, "Meme already unleashed");

        // Update meme token map values
        uint256 totalNativeTokenCommitted = memeSummon.nativeTokenContributed;
        totalNativeTokenCommitted += msg.value;
        memeSummon.nativeTokenContributed = totalNativeTokenCommitted;
        memeHearters[memeNonce][msg.sender] += msg.value;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Hearted(msg.sender, memeNonce, msg.value);

        _locked = 1;
    }

    /// @dev Create a new meme token.
    function _createThisMeme(
        uint256 memeNonce,
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) internal returns (address memeToken) {
        bytes32 randomNonce = keccak256(abi.encodePacked(block.timestamp, block.prevrandao, msg.sender, memeNonce));
        randomNonce = keccak256(abi.encodePacked(randomNonce));
        bytes memory payload = abi.encodePacked(type(Meme).creationCode, abi.encode(name, symbol, DECIMALS, totalSupply));
        // solhint-disable-next-line no-inline-assembly
        assembly {
            memeToken := create2(0x0, add(0x20, payload), mload(payload), memeNonce) // revert to randomNonce
        }

        // Check for non-zero token address
        require(memeToken != address(0), "Token creation failed");
    }

    /// @dev Unleashes the meme token.
    /// @param memeNonce Meme token nonce.
    function unleashThisMeme(uint256 memeNonce) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get meme summon info
        MemeSummon storage memeSummon = memeSummons[memeNonce];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime == 0, "Meme already unleashed");
        // Check if the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummon.summonTime + UNLEASH_DELAY, "Cannot unleash yet");

        // Get the total native token amount committed to this meme
        uint256 totalNativeTokenCommitted = memeSummon.nativeTokenContributed;

        // Wrap native token to its ERC-20 version
        // All funds ever contributed to a given meme are wrapped here.
        _wrap(totalNativeTokenCommitted);

        // Put aside native token to buy OLAS with the burn percentage of the total native token amount committed
        uint256 nativeAmountForOLASBurn = (totalNativeTokenCommitted * OLAS_BURN_PERCENTAGE) / 100;

        // Adjust native token amount
        uint256 nativeAmountForLP = totalNativeTokenCommitted - nativeAmountForOLASBurn;

        // Schedule native token amount for ascendance
        // uint256 adjustedNativeAmountForAscendance = _updateLaunchCampaignBalance(nativeAmountForOLASBurn);
        scheduledForAscendance += nativeAmountForOLASBurn;

        _unleashThisMeme(memeNonce, memeSummon, nativeAmountForLP, totalNativeTokenCommitted, nativeAmountForOLASBurn);

        _locked = 1;
    }

    /// @dev Unleashes the meme token.
    /// @param memeNonce Meme token nonce.
    function _unleashThisMeme(uint256 memeNonce, MemeSummon storage memeSummon, uint256 nativeAmountForLP, uint256 totalNativeTokenCommitted, uint256 nativeAmountForOLASBurn) internal {

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        uint256 memeAmountForLP = (memeSummon.totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = memeSummon.totalSupply - memeAmountForLP;

        // Create new meme token
        address memeToken = _createThisMeme(memeNonce, memeSummon.name, memeSummon.symbol, memeSummon.totalSupply);

        // Record meme token address
        memeTokenNonces[memeToken] = memeNonce;

        // Create Uniswap pair with LP allocation
        (uint256 positionId, uint256 liquidity, bool isNativeFirst) =
            _createUniswapPair(memeToken, nativeAmountForLP, memeAmountForLP);

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;
        // Record position token Id
        memeSummon.positionId = positionId;
        // Record token order in the pool
        if (isNativeFirst) {
            memeSummon.isNativeFirst = isNativeFirst;
        }

        // Push token into the global list of tokens
        memeTokens.push(memeToken);
        numTokens = memeTokens.length;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[memeNonce][msg.sender];
        if (hearterContribution > 0) {
            _collectMemeToken(memeToken, memeNonce, heartersAmount, hearterContribution, totalNativeTokenCommitted);
        }

        emit Unleashed(msg.sender, memeToken, positionId, liquidity, nativeAmountForOLASBurn);
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    function collectThisMeme(address memeToken) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get meme nonce
        uint256 memeNonce = memeTokenNonces[memeToken];

        // Get meme summon info
        MemeSummon memory memeSummon = memeSummons[memeNonce];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if the meme can be collected
        require(block.timestamp <= memeSummon.unleashTime + COLLECT_DELAY, "Collect only allowed until 24 hours after unleash");

        // Get hearter contribution
        uint256 hearterContribution = memeHearters[memeNonce][msg.sender];
        // Check for zero value
        require(hearterContribution > 0, "No token allocation");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Collect the token
        _collectMemeToken(memeToken, memeNonce, memeSummon.heartersAmount, hearterContribution,
            memeSummon.nativeTokenContributed);

        _locked = 1;
    }

    /// @dev Purges uncollected meme token allocation.
    /// @param memeToken Meme token address.
    function purgeThisMeme(address memeToken) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get meme nonce
        uint256 memeNonce = memeTokenNonces[memeToken];

        // Get meme summon info
        MemeSummon memory memeSummon = memeSummons[memeNonce];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if enough time has passed since the meme was unleashed
        require(block.timestamp > memeSummon.unleashTime + COLLECT_DELAY, "Purge only allowed from 24 hours after unleash");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Burn all remaining tokens in this contract
        uint256 remainingBalance = memeTokenInstance.balanceOf(address(this));
        // Check the remaining balance is positive
        require(remainingBalance > 0, "Has been purged or nothing to purge");
        // Burn the remaining balance
        memeTokenInstance.burn(remainingBalance);

        emit Purged(memeToken, remainingBalance);

        _locked = 1;
    }

    /// @dev Transfers native token to later be converted to OLAS for burn.
    function scheduleForAscendance() external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        uint256 amount = _launched > 0 ? scheduledForAscendance : _launchCampaign();
        require(amount > 0, "Nothing to send");

        scheduledForAscendance = 0;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        if (amount > 0) {
            // Transfers native token to be later converted to OLAS for burn.
            IERC20(nativeToken).transfer(buyBackBurner, amount);

            emit OLASJourneyToAscendance(amount);
        }

        _locked = 1;
    }

    /// @dev Collects all accumulated LP fees.
    /// @param tokens List of tokens to be iterated over.
    function collectFees(address[] memory tokens) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        for (uint256 i = 0; i < tokens.length; ++i) {
            // Get meme nonce
            uint256 memeNonce = memeTokenNonces[tokens[i]];
            // Get meme summon struct
            MemeSummon memory memeSummon = memeSummons[memeNonce];

            // Collect fees
            _collectFees(tokens[i], memeSummon.positionId, memeSummon.isNativeFirst);
        }

        _locked = 1;
    }
}

interface IWETH {
    function deposit() external payable;
}

/// @title MemeBase - a smart contract factory for Meme Token creation on Base.
contract MemeBase is MemeFactory {
    // AGNT data:
    // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F17
    // Previous token address: 0x7484a9fB40b16c4DFE9195Da399e808aa45E9BB9
    // Full collected amount: 141569842100000000000
    uint256 public constant CONTRIBUTION_AGNT = 141569842100000000000;
    // Liquidity amount: collected amount - 10% for burn = 127412857890000000000
    uint256 public constant LIQUIDITY_AGNT = 127412857890000000000;
    // Block time of original summon
    uint256 public constant SUMMON_AGNT = 22902993;

    // Launch campaign nonce
    uint256 public immutable launchCampaignNonce;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue,
        address[] memory accounts,
        uint256[] memory amounts
    ) MemeFactory(_olas, _nativeToken, _uniV3PositionManager, _buyBackBurner, _minNativeTokenValue) {
        if (accounts.length > 0) {
            launchCampaignNonce = _nonce;
            _launchCampaignSetup(accounts, amounts);
            _nonce = launchCampaignNonce + 1;
            _launched = 0;
        }
    }

    /// @dev Launch campaign initialization function.
    /// @param accounts Original accounts.
    /// @param amounts Corresponding original amounts (without subtraction for burn).
    function _launchCampaignSetup(address[] memory accounts, uint256[] memory amounts) private {
        require(accounts.length == amounts.length);

        // Initiate meme token map values
        // unleashTime is set to 1 such that no one is able to heart this token
        memeSummons[launchCampaignNonce] = MemeSummon("Agent Token II", "AGNT II", 1_000_000_000 ether,
            CONTRIBUTION_AGNT, SUMMON_AGNT, 1, 0, 0, false);

        // To match original summon events (purposefully placed here to match order of original events)
        emit Summoned(accounts[0], launchCampaignNonce, amounts[0]);

        // Record all the accounts and amounts
        uint256 totalAmount;
        for (uint256 i = 0; i < accounts.length; ++i) {
            totalAmount += amounts[i];
            memeHearters[launchCampaignNonce][accounts[i]] = amounts[i];
            // to match original hearter events
            emit Hearted(accounts[i], launchCampaignNonce, amounts[i]);
        }
        require(totalAmount == CONTRIBUTION_AGNT, "Total amount must match original contribution amount");
        // Adjust amount for already collected burned tokens
        uint256 adjustedAmount = (totalAmount * 9) / 10;
        require(adjustedAmount == LIQUIDITY_AGNT, "Total amount adjusted for burn allocation must match liquidity amount");
    }

    /// @dev AGNT token launch campaign unleash.
    /// @notice Make Agents.Fun Great Again.
    /// Unleashes a new version of AGNT, called `AGNT II`, that has the same 
    /// LP setup (same amount of AGNT II and ETH), as the original AGN was meant to have.
    /// Hearters of the original AGNT now have 24 hours to collect their `AGNT II`.
    function _MAGA() private {
        // Get meme summon info
        MemeSummon storage memeSummon = memeSummons[launchCampaignNonce];

        // Unleash the token
        _unleashThisMeme(launchCampaignNonce, memeSummon, LIQUIDITY_AGNT, CONTRIBUTION_AGNT, 0);

    }

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @return adjustedAmount Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign() internal override returns (uint256 adjustedAmount) {
        require(scheduledForAscendance >= LIQUIDITY_AGNT, "Not enough to cover launch campaign");

        // Unleash the campaign token
        _MAGA();

        // scheduledForAscendance might also increase during the pool creation
        adjustedAmount = scheduledForAscendance - LIQUIDITY_AGNT;

        _launched = 1;
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
