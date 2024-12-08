// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IUniswapV3} from "./interfaces/IUniswapV3.sol";
import {TickMath} from "./libraries/TickMath.sol";

/// @dev Only `owner` has a privilege, but the `sender` was provided.
/// @param sender Sender address.
/// @param owner Required sender address as an owner.
error OwnerOnly(address sender, address owner);

/// @dev Provided zero address.
error ZeroAddress();

/// @dev The contract is already initialized.
error AlreadyInitialized();

/// @title BuyBackBurner - BuyBackBurner implementation contract
contract BuyBackBurner {
    event ImplementationUpdated(address indexed implementation);
    event OwnerUpdated(address indexed owner);

    // Version number
    string public constant VERSION = "0.0.1";
    // Code position in storage is keccak256("BUY_BACK_BURNER_PROXY") = "c6d7bd4bd971fa336816fe30b665cc6caccce8b123cc8ea692d132f342c4fc19"
    bytes32 public constant BUY_BACK_BURNER_PROXY = 0xc6d7bd4bd971fa336816fe30b665cc6caccce8b123cc8ea692d132f342c4fc19;
    // L1 OLAS Burner address
    address public constant OLAS_BURNER = 0x51eb65012ca5cEB07320c497F4151aC207FEa4E0;
    // Max allowed price deviation for TWAP pool values (10%) in 1e18 format
    uint256 public constant MAX_ALLOWED_DEVIATION = 1e17;
    // Seconds ago to look back for TWAP pool values
    uint32 public constant SECONDS_AGO = 1800;

    // Contract owner
    address public owner;

    function _getTwapFromOracle(address pool) internal view returns (uint256 priceX96) {
        // Query the pool for the current and historical tick
        uint32[] memory secondsAgos = new uint32[](2);
        // Start of the period
        secondsAgos[0] = SECONDS_AGO;

        // Fetch the tick cumulative values from the pool
        (int56[] memory tickCumulatives, ) = IUniswapV3(pool).observe(secondsAgos);

        // Calculate the average tick over the time period
        int56 tickCumulativeDelta = tickCumulatives[1] - tickCumulatives[0];
        int24 averageTick = int24(tickCumulativeDelta / int56(int32(SECONDS_AGO)));

        // Convert the average tick to sqrtPriceX96
        uint160 sqrtPriceX96 = TickMath.getSqrtRatioAtTick(averageTick);

        // Calculate the price using the sqrtPriceX96
        priceX96 = (uint256(sqrtPriceX96) * uint256(sqrtPriceX96)) / (1 << 192);
    }

    /// @dev BuyBackBurner initializer.
    function initialize() external{
        if (owner != address(0)) {
            revert AlreadyInitialized();
        }

        owner = msg.sender;
    }

    /// @dev Changes the implementation contract address.
    /// @param newImplementation New implementation contract address.
    function changeImplementation(address newImplementation) external {
        // Check for the ownership
        if (msg.sender != owner) {
            revert OwnerOnly(msg.sender, owner);
        }

        // Check for zero address
        if (newImplementation == address(0)) {
            revert ZeroAddress();
        }

        // Store the implementation address
        assembly {
            sstore(BUY_BACK_BURNER_PROXY, newImplementation)
        }

        emit ImplementationUpdated(newImplementation);
    }

    /// @dev Changes contract owner address.
    /// @param newOwner Address of a new owner.
    function changeOwner(address newOwner) external virtual {
        // Check for the ownership
        if (msg.sender != owner) {
            revert OwnerOnly(msg.sender, owner);
        }

        // Check for the zero address
        if (newOwner == address(0)) {
            revert ZeroAddress();
        }

        owner = newOwner;
        emit OwnerUpdated(newOwner);
    }

    function checkPoolPrices(
        address nativeToken,
        address memeToken,
        address uniV3PositionManager,
        uint24 fee,
        bool isNativeFirst
    ) external {
        // Get factory address
        address factory = IUniswapV3(uniV3PositionManager).factory();

        (address token0, address token1) = isNativeFirst ? (nativeToken, memeToken) : (memeToken, nativeToken);

        // Verify pool reserves before proceeding
        address pool = IUniswapV3(factory).getPool(token0, token1, fee);
        require(pool != address(0), "Pool does not exist");

        // Get current pool reserves
        (uint160 sqrtPriceX96, , uint16 observationCardinality, , , , ) = IUniswapV3(pool).slot0();
        // Check observation cardinality
        if (observationCardinality < 2) {
            // Increase observation cardinality to get more accurate twap
            IUniswapV3(pool).increaseObservationCardinalityNext(60);
            return;
        }

        // Check if the pool has sufficient observation history
        (uint32 oldestTimestamp, , , ) = IUniswapV3(pool).observations(0);
        if (oldestTimestamp + SECONDS_AGO >= block.timestamp) {
            return;
        }

        // Check TWAP or historical data
        uint256 twapPrice = _getTwapFromOracle(pool);
        // Get instant price
        uint256 instantPrice = (uint256(sqrtPriceX96) * uint256(sqrtPriceX96)) / (1 << 192);

        uint256 deviation;
        if (twapPrice > 0) {
            deviation = (instantPrice > twapPrice) ?
                ((instantPrice - twapPrice) * 1e18) / twapPrice :
                ((twapPrice - instantPrice) * 1e18) / twapPrice;
        }

        require(deviation <= MAX_ALLOWED_DEVIATION, "Price deviation too high");
    }
}