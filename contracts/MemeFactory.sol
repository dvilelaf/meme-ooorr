// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Creates an LP pair.
    function createPair(address tokenA, address tokenB) external returns (address pair);

    /// @dev Adds liquidity to the LP consisting of tokenA and tokenB.
    function addLiquidity(address tokenA, address tokenB, uint256 amountADesired, uint256 amountBDesired,
        uint256 amountAMin, uint256 amountBMin, address to, uint256 deadline)
        external returns (uint256 amountA, uint256 amountB, uint256 liquidity);
}

/// @title MemeFactory - a smart contract factory for Meme Token creation
/// @dev This contract let's:
///      1) Any msg.sender summons a meme by contributing at least 0.01 ETH.
///      2) Within 24h of a meme being summoned, any msg.sender can heart a meme (thereby becoming a hearter).
///         This requires the msg.sender to send a non-zero ETH value, which gets recorded as a contribution.
///      3) After 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for
///         the meme and schedules the distribution of the rest of the tokens to the hearters, proportional to their
///         contributions.
///      4) After the meme is being unleashed any hearter can collect their share of the meme token.
///      5) After 48h of a meme being summoned, any msg.sender can purge the uncollected meme token allocations of hearters.
/// @notice 10% of the ETH contributed to a meme gets converted into USDC upon unleashing of the meme, that can later be
///         converted to OLAS and scheduled for burning (on Ethereum mainnet). The remainder of the ETH contributed (90%)
///         is converted to USDC and contributed to an LP, together with 50% of the token supply of the meme.
///         The remaining 50% of the meme token supply goes to hearters. The LP token is held forever by MemeBase,
///         guaranteeing lasting liquidity in the meme token.
///
///         Example:
///         - Agent Smith would summonThisMeme with arguments Smiths Army, SMTH, 1_000_000_000 and $500 worth of ETH
///         - Agent Brown would heartThisMeme with $250 worth of ETH
///         - Agent Jones would heartThisMeme with $250 worth of ETH
///         - Any agent, let's say Brown, would call unleashThisMeme. This would:
///             - create a liquidity pool with $SMTH:$USDC, containing 500_000_000 SMTH tokens and $900 worth of USDC
///             - schedule $100 worth of OLAS for burning on Ethereum mainnet
///             - Brown would receive 125_000_000 worth of $SMTH
///         - Agent Smith would collectThisMeme and receive 250_000_000 worth of $SMTH
///         - Agent Jones would forget to collectThisMeme
///         - Any agent would call purgeThisMeme, which would cause Agent Jones's allocation of 125_000_000 worth of
///           $SMTH to be burned.
abstract contract MemeFactory {
    event OLASJourneyToAscendance(address indexed olas, uint256 amount);
    event Summoned(address indexed summoner, address indexed memeToken, uint256 ethContributed);
    event Hearted(address indexed hearter, address indexed memeToken, uint256 amount);
    event Unleashed(address indexed unleasher, address indexed memeToken, address indexed lpPairAddress,
        uint256 liquidity, uint256  burnPercentageOfStable);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 remainingAmount);

    // Meme Summon struct
    struct MemeSummon {
        // ETH contributed to the meme launch
        uint256 ethContributed;
        // Summon timestamp
        uint256 summonTime;
        // Unleash timestamp
        uint256 unleashTime;
        // Finalized hearters amount
        uint256 heartersAmount;
    }

    // Version number
    string public constant VERSION = "0.1.0";
    // Total supply minimum value
    uint256 public constant MIN_TOTAL_SUPPLY = 1_000_000 ether;
    // Unleash delay after token summoning
    uint256 public constant UNLEASH_DELAY = 24 hours;
    // Collect deadline from the token summoning time
    uint256 public constant COLLECT_DEADLINE = 48 hours;
    // Percentage of OLAS to burn (10%)
    uint256 public constant OLAS_BURN_PERCENTAGE = 10;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public constant LP_PERCENTAGE = 50;
    // L1 OLAS Burner address
    address public constant OLAS_BURNER = 0x51eb65012ca5cEB07320c497F4151aC207FEa4E0;
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Minimum value of native token deposit
    uint256 public immutable minNativeTokenValue;
    // OLAS token address
    address public immutable olas;
    // USDC token address
    address public immutable usdc;
    // WETH token address
    address public immutable weth;
    // Uniswap V2 router address
    address public immutable router;
    // Uniswap V2 factory address
    address public immutable factory;
    // Balancer Vault address
    address public immutable balancerVault;

    // Number of meme tokens
    uint256 public numTokens;
    // USDC scheduled to be converted to OLAS for Ascendance
    uint256 public scheduledForAscendance;

    // Map of meme token => Meme summon struct
    mapping(address => MemeSummon) public memeSummons;
    // Map of mem token => (map of hearter => ETH balance)
    mapping(address => mapping(address => uint256)) public memeHearters;
    // Map of account => activity counter
    mapping(address => uint256) public mapAccountActivities;
    // Set of all meme tokens created by this contract
    address[] public memeTokens;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _usdc,
        address _weth,
        address _router,
        address _factory,
        address _balancerVault,
        uint256 _minNativeTokenValue
    ) {
        olas = _olas;
        usdc = _usdc;
        weth = _weth;
        router = _router;
        factory = _factory;
        balancerVault = _balancerVault;
        minNativeTokenValue = _minNativeTokenValue;
    }

    /// @dev Buys USDC on UniswapV2 using ETH amount.
    /// @param ethAmount Input ETH amount.
    /// @return USDC amount bought.
    function _buyStableToken(uint256 ethAmount, uint256) internal virtual returns (uint256);

    /// @dev Buys OLAS on Balancer.
    /// @param usdcAmount USDC amount.
    /// @param limit OLAS minimum amount depending on the desired slippage.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 usdcAmount, uint256 limit) internal virtual returns (uint256);

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param OLASAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @param bridgePayload Optional additional bridge payload.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(
        uint256 OLASAmount,
        uint256 tokenGasLimit,
        bytes memory bridgePayload
    ) internal virtual returns (uint256);

    /// @dev Creates USDC + meme token LP and adds liquidity.
    /// @param memeToken Meme token address.
    /// @param usdcAmount USDC amount.
    /// @param memeTokenAmount Meme token amount.
    /// @return pair USDC + meme token LP address.
    /// @return liquidity Obtained LP liquidity.
    function _createUniswapPair(
        address memeToken,
        uint256 usdcAmount,
        uint256 memeTokenAmount
    ) internal returns (address pair, uint256 liquidity) {
        // Create the LP
        pair = IUniswap(factory).createPair(usdc, memeToken);

        // Approve tokens for router
        IERC20(usdc).approve(router, usdcAmount);
        IERC20(memeToken).approve(router, memeTokenAmount);

        // Add USDC + meme token liquidity
        (, , liquidity) = IUniswap(router).addLiquidity(
            usdc,
            memeToken,
            usdcAmount,
            memeTokenAmount,
            0, // Accept any amount of USDC
            0, // Accept any amount of meme token
            address(this),
            block.timestamp
        );
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    /// @param heartersAmount Total hearters meme token amount.
    /// @param hearterContribution Hearter contribution.
    /// @param totalETHCommitted Total ETH contributed for the token launch.
    function _collect(
        address memeToken,
        uint256 heartersAmount,
        uint256 hearterContribution,
        uint256 totalETHCommitted
    ) internal {
        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Allocate corresponding meme token amount to the hearter
        uint256 allocation = (heartersAmount * hearterContribution) / totalETHCommitted;

        // Zero the allocation
        memeHearters[memeToken][msg.sender] = 0;

        // Transfer meme token maount to the msg.sender
        memeTokenInstance.transfer(msg.sender, allocation);

        emit Collected(msg.sender, memeToken, allocation);
    }

    /// @dev Summons meme token.
    /// @param name Token name.
    /// @param symbol Token symbol.
    /// @param totalSupply Token total supply.
    function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        // Check for minimum ETH value
        require(msg.value >= minNativeTokenValue, "Minimum native token value is required to summon");
        // Check for minimum total supply
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Minimum total supply is not met");

        // Create a new token
        Meme newTokenInstance = new Meme(name, symbol, DECIMALS, totalSupply);
        address memeToken = address(newTokenInstance);

        // Initiate meme token map values
        memeSummons[memeToken] = MemeSummon(msg.value, block.timestamp, 0, 0);
        memeHearters[memeToken][msg.sender] = msg.value;

        // Push token into the global list of tokens
        memeTokens.push(memeToken);
        numTokens = memeTokens.length;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Summoned(msg.sender, memeToken, msg.value);
    }

    /// @dev Hearts the meme token with ETH contribution.
    /// @param memeToken Meme token address.
    function heartThisMeme(address memeToken) external payable {
        // Check for zero value
        require(msg.value > 0, "ETH amount must be greater than zero");

        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Get the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummon.ethContributed;

        // Check that the meme has been summoned
        require(totalETHCommitted > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(memeSummon.unleashTime == 0, "Meme already unleashed");

        // Update meme token map values
        totalETHCommitted += msg.value;
        memeSummon.ethContributed = totalETHCommitted;
        memeHearters[memeToken][msg.sender] += msg.value;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Hearted(msg.sender, memeToken, msg.value);
    }

    /// @dev Unleashes the meme token.
    /// @param memeToken Meme token address.
    /// @param limit Stable token minimum amount depending on the desired slippage, if applicable.
    function unleashThisMeme(address memeToken, uint256 limit) external {
        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Get the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummon.ethContributed;

        // Check if the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummon.summonTime + UNLEASH_DELAY, "Cannot unleash yet");

        // Buy USDC with the the total ETH committed
        // This might not be needed in other implementations, and the function would return the given value
        uint256 usdcAmount = _buyStableToken(totalETHCommitted, limit);

        // Put aside USDC to buy OLAS with the burn percentage of the total ETH committed
        uint256 burnPercentageOfUSDC = (usdcAmount * OLAS_BURN_PERCENTAGE) / 100;
        scheduledForAscendance += burnPercentageOfUSDC;

        // Adjust USDC amount
        usdcAmount -= burnPercentageOfUSDC;

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeTokenInstance = Meme(memeToken);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 lpTokenAmount = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - lpTokenAmount;

        // Create Uniswap pair with LP allocation
        (address pool, uint256 liquidity) = _createUniswapPair(memeToken, usdcAmount, lpTokenAmount);

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        if (hearterContribution > 0) {
            _collect(memeToken, hearterContribution, heartersAmount, totalETHCommitted);
        }

        emit Unleashed(msg.sender, memeToken, pool, liquidity, burnPercentageOfUSDC);
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    function collectThisMeme(address memeToken) external {
        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if the meme can be collected
        require(block.timestamp <= memeSummon.summonTime + COLLECT_DEADLINE, "Collect only allowed until 48 hours after summon");

        // Get hearter contribution
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        // Check for zero value
        require(hearterContribution > 0, "No token allocation");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Collect the token
        _collect(memeToken, hearterContribution, memeSummon.heartersAmount, memeSummon.ethContributed);
    }

    /// @dev Purges uncollected meme token allocation.
    /// @param memeToken Meme token address.
    function purgeThisMeme(address memeToken) external {
        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not summoned");
        // Check if enough time has passed since the meme was summoned
        require(block.timestamp > memeSummon.summonTime + COLLECT_DEADLINE, "Purge only allowed from 48 hours after summon");

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
    }

    /// @dev Converts collected USDC to OLAS and bridges OLAS to Ethereum mainnet for burn.
    /// @param limit OLAS minimum amount depending on the desired slippage.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @param bridgePayload Optional additional bridge payload.
    function scheduleOLASForAscendance(uint256 limit, uint256 tokenGasLimit, bytes memory bridgePayload) external payable {
        // TODO reentrancy throughout the contract
        require(scheduledForAscendance > 0, "Nothing to burn");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        uint256 OLASAmount = _buyOLAS(scheduledForAscendance, limit);

        scheduledForAscendance = 0;
        // Burn OLAS
        uint256 leftovers = _bridgeAndBurn(OLASAmount, tokenGasLimit, bridgePayload);

        // Send leftover amount, if any, back to the sender
        if (leftovers > 0) {
            // If the call fails, ignore to avoid the attack that would prevent this function from executing
            // solhint-disable-next-line avoid-low-level-calls
            tx.origin.call{value: leftovers}("");
        }
    }

    /// @dev Allows the contract to receive ETH
    receive() external payable {}
}