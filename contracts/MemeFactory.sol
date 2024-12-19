// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {FixedPointMathLib} from "../lib/solmate/src/utils/FixedPointMathLib.sol";
import {Meme} from "./Meme.sol";
import {IUniswapV3} from "./interfaces/IUniswapV3.sol";

interface IBuyBackBurner {
    function checkPoolPrices(address token0, address token1, address uniV3PositionManager, uint24 fee) external view;
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
/// @dev This contract lets:
///      1) Any msg.sender summons a meme by contributing at least 0.01 ETH (or equivalent native asset for other chains).
///      2) Within 24h of a meme being summoned, any msg.sender can heart a meme (thereby becoming a hearter).
///         This requires the msg.sender to send a non-zero ETH value (or equivalent native asset for other chains),
///         which gets recorded as a contribution.
///      3) After 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for
///         the meme and schedules the distribution of the rest of the tokens to the hearters, proportional to their
///         contributions.
///      4) After the meme is being unleashed any hearter can collect their share of the meme token.
///      5) After 24h of a meme being unleashed, any msg.sender can purge the uncollected meme token allocations of hearters.
/// @notice 10% of the ETH (or equivalent native asset for other chains) contributed to a meme gets retained upon unleashing
///         of the meme, that can later be converted to OLAS and scheduled for burning (on Ethereum mainnet). The remainder of
///         the ETH contributed (90%) is contributed to an LP on UniV3, together with 50% of the token supply of the meme.
///         The remaining 50% of the meme token supply goes to hearters. The LP token is held forever by MemeFactory,
///         guaranteeing lasting liquidity in the meme token.
///         Trading fees from the LPs held by MemeFactory can be collected. When collected, the meme token part of the fees is
///         instantly burned. The ETH (or equivalent native asset for other chains) token part can later be converted to OLAS
///         and scheduled for burning (on Ethereum mainnet).
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
    event Summoned(address indexed summoner, uint256 indexed memeNonce, uint256 amount);
    event Hearted(address indexed hearter, uint256 indexed memeNonce, uint256 amount);
    event Unleashed(address indexed unleasher, uint256 indexed memeNonce, address indexed memeToken, uint256 lpTokenId,
        uint256 liquidity);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 amount);
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
    // Uniswap V3 fee tier of 1%
    uint24 public constant FEE_TIER = 10_000;
    /// The minimum tick that corresponds to a selected fee tier
    int24 public constant MIN_TICK = -887200;
    /// The maximum tick that corresponds to a selected fee tier
    int24 public constant MAX_TICK = -MIN_TICK;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Minimum value of native token deposit
    uint256 public immutable minNativeTokenValue;
    // Native token address (ERC-20 equivalent)
    address public immutable nativeToken;
    // Uniswap V3 position manager address
    address public immutable uniV3PositionManager;
    // BuyBackBurner address
    address public immutable buyBackBurner;

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
    // Map of meme nonce => (map of hearter => native token balance)
    mapping(uint256 => mapping(address => uint256)) public memeHearters;
    // Map of meme token address => Meme nonce
    mapping(address => uint256) public memeTokenNonces;
    // Map of account => activity counter
    mapping(address => uint256) public mapAccountActivities;
    // Set of all meme tokens created by this contract
    address[] public memeTokens;

    /// @dev MemeFactory constructor
    constructor(
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue
    ) {
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
        uint256 price = FixedPointMathLib.divWadDown(amount1, amount0);

        // Calculate the square root of the price ratio in X96 format
        uint160 sqrtPriceX96 = uint160((FixedPointMathLib.sqrt(price) * (1 << 96)) / 1e9);

        // Get factory address
        address factory = IUniswapV3(uniV3PositionManager).factory();
        // Verify that pool does not exist
        address pool = IUniswapV3(factory).getPool(token0, token1, FEE_TIER);
        require(pool == address(0), "Pool address must be zero");

        // Create pool
        pool = IUniswapV3(uniV3PositionManager).createAndInitializePoolIfNecessary(token0, token1, FEE_TIER, sqrtPriceX96);

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
        uint256 nativeLeftovers = nativeTokenAmount - (isNativeFirst ? amount0 : amount1);
        if (nativeLeftovers > 0) {
            scheduledForAscendance += nativeLeftovers;
        }

        // Increase observation cardinality
        IUniswapV3(pool).increaseObservationCardinalityNext(_observationCardinalityNext());
    }

    /// @dev Collects fees from LP position, burns the meme token part and schedules for ascendance the native token part.
    /// @param memeToken Meme token address.
    /// @param positionId LP position ID.
    /// @param isNativeFirst Order of a native token in the pool.
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

        // Get corresponding token fees
        (uint256 amount0, uint256 amount1) = IUniswapV3(uniV3PositionManager).collect(params);
        require(amount0 > 0 || amount1 > 0, "Zero fees available");

        (uint256 nativeAmountForOLASBurn, uint256 memeAmountToBurn) = isNativeFirst ? (amount0, amount1) :
            (amount1, amount0);

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

    /// @dev Create a new meme token.
    /// @param memeNonce Meme nonce.
    /// @param name Meme token name.
    /// @param symbol Meme token symbol.
    /// @param totalSupply Meme token total supply.
    /// @return memeToken Meme token address.
    function _createThisMeme(
        uint256 memeNonce,
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) internal returns (address memeToken) {
        bytes32 randomNonce = keccak256(abi.encodePacked(block.timestamp, msg.sender, memeNonce));
        randomNonce = keccak256(abi.encodePacked(randomNonce));
        memeToken = address(new Meme{salt: randomNonce}(name, symbol, DECIMALS, totalSupply));

        // Check for non-zero token address
        require(memeToken != address(0), "Token creation failed");
    }

    /// @dev Gets required UniswapV3 pool cardinality.
    /// @return Pool cardinality.
    function _observationCardinalityNext() internal virtual pure returns (uint16);

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @return adjustedAmount Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign() internal virtual returns (uint256 adjustedAmount);

    /// @dev Unleashes the meme token.
    /// @param memeNonce Meme token nonce.
    /// @param memeSummon Meme summon struct.
    /// @param nativeAmountForLP The native token amount allocated for the LP.
    /// @param totalNativeTokenCommitted The total native token amount committed to the meme.
    function _unleashThisMeme(
        uint256 memeNonce,
        MemeSummon storage memeSummon,
        uint256 nativeAmountForLP,
        uint256 totalNativeTokenCommitted
    ) internal {
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

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[memeNonce][msg.sender];
        if (hearterContribution > 0) {
            _collectMemeToken(memeToken, memeNonce, heartersAmount, hearterContribution, totalNativeTokenCommitted);
        }

        emit Unleashed(msg.sender, memeNonce, memeToken, positionId, liquidity);
    }

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

        // Check for name and symbol lengths
        require(bytes(name).length > 0 && bytes(symbol).length > 0, "Name and symbol must not be empty");
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
        memeSummon.nativeTokenContributed += msg.value;
        memeHearters[memeNonce][msg.sender] += msg.value;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Hearted(msg.sender, memeNonce, msg.value);

        _locked = 1;
    }
    
    /// @dev Unleashes the meme token.
    /// @param memeNonce Meme token nonce.
    function unleashThisMeme(uint256 memeNonce) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get meme summon info
        MemeSummon storage memeSummon = memeSummons[memeNonce];

        // Check if the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(memeSummon.unleashTime == 0, "Meme already unleashed");
        // Check the unleash condition
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
        scheduledForAscendance += nativeAmountForOLASBurn;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        _unleashThisMeme(memeNonce, memeSummon, nativeAmountForLP, totalNativeTokenCommitted);

        _locked = 1;
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

        // Check if the meme has been unleashed
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

    /// @dev Transfers native token to BuyBackBurner to later be converted to OLAS for burn.
    function scheduleForAscendance() external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        uint256 amount = _launched > 0 ? scheduledForAscendance : _launchCampaign();
        // This condition means launchCampaign can only be triggered once there's a positive
        // amount for ascendance remaining.
        require(amount > 0, "Nothing to send");

        scheduledForAscendance = 0;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Transfers native token to be later converted to OLAS for burn.
        IERC20(nativeToken).transfer(buyBackBurner, amount);

        emit OLASJourneyToAscendance(amount);

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

    /// @dev Gets global number of unleashed meme tokens.
    /// @return Number of unleashed meme tokens.
    function numTokens() external view returns (uint256) {
        return memeTokens.length;
    }
}
