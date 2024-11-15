// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

// Bridge interface
interface IBridge {
    /// @dev Transfers tokens through Wormhole portal.
    function transferTokens(
        address token,
        uint256 amount,
        uint16 recipientChain,
        bytes32 recipient,
        uint256 arbiterFee,
        uint32 nonce
    ) external payable returns (uint64 sequence);
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

// Oracle interface
interface IOracle {
    /// @dev Gets latest round token price data.
    function latestRoundData()
        external returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Swaps exact amount of ETH for a specified token.
    function swapExactTokensForTokens(uint256 amountOutMin, address[] calldata path, address to, uint256 deadline)
        external payable returns (uint256[] memory amounts);

    /// @dev Swaps an exact amount of input tokens along the route determined by the path. 
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

/// @title MemeCelo - a smart contract factory for Meme Token creation on Celo.
contract MemeCelo is MemeFactory {
    // Slippage parameter (3%)
    uint256 public constant SLIPPAGE = 97;
    // Wormhole bridging decimals cutoff
    uint256 public constant WORMHOLE_BRIDGING_CUTOFF = 1e10;
    // Ethereum mainnet chain Id in Wormhole format
    uint16 public constant WORMHOLE_ETH_CHAIN_ID = 2;

    // CELO token address
    address public immutable celo;
    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Oracle address
    address public immutable oracle;

    // Contract nonce
    uint256 public nonce;
    // OLAS leftovers from bridging
    uint256 public olasLeftovers;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _referenceToken,
        address _router,
        address _factory,
        uint256 _minNativeTokenValue,
        address _celo,
        address _l2TokenRelayer,
        address _oracle
    ) MemeFactory(_olas, _referenceToken, _router, _factory, _minNativeTokenValue) {
        celo = _celo;
        l2TokenRelayer = _l2TokenRelayer;
        oracle = _oracle;
    }

    /// @dev Buys cUSD on UniswapV2 using Celo amount.
    /// @param nativeTokenAmount Input Celo amount.
    /// @return Stable token amount bought.
    function _convertToReferenceToken(uint256 nativeTokenAmount, uint256) internal override returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = celo;
        path[1] = referenceToken;

        // Calculate price by Oracle
        (, int256 answerPrice, , , ) = IOracle(oracle).latestRoundData();
        require(answerPrice > 0, "Oracle price is incorrect");

        // Oracle returns 8 decimals, cUSD has 18 decimals, need to additionally divide by 100 to account for slippage
        // ETH: 18 decimals, cUSD: 18 decimals, percentage: 2 decimals; denominator = 8 + 2 = 10
        uint256 limit = uint256(answerPrice) * nativeTokenAmount * SLIPPAGE / 1e10;

        // Approve reference token
        IERC20(celo).approve(router, nativeTokenAmount);

        // Swap CELO for cUSD
        uint256[] memory amounts = IUniswap(router).swapExactTokensForTokens(
            nativeTokenAmount,
            limit,
            path,
            address(this),
            block.timestamp
        );

        // Return the cUSD amount bought
        return amounts[1];
    }

    /// @dev Buys OLAS on UniswapV2.
    /// @param referenceTokenAmount CELO amount.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 referenceTokenAmount, uint256 limit) internal override returns (uint256) {
        address[] memory path = new address[](3);
        path[0] = referenceToken;
        path[1] = celo;
        path[2] = olas;

        // Approve reference token
        IERC20(referenceToken).approve(router, referenceTokenAmount);

        // Swap cUSD for OLAS
        // This will go via two pools - not a problem as Ubeswap has both
        uint256[] memory amounts = IUniswap(router).swapExactTokensForTokens(
            referenceTokenAmount,
            limit,
            path,
            address(this),
            block.timestamp
        );

        // Return the OLAS amount bought
        return amounts[1];
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 olasAmount, uint256, bytes memory) internal override returns (uint256) {
        // Get OLAS leftovers from previous transfers and adjust the amount to transfer
        olasAmount += olasLeftovers;

        // Round transfer amount to the cutoff value
        uint256 transferAmount = olasAmount / WORMHOLE_BRIDGING_CUTOFF;
        transferAmount *= WORMHOLE_BRIDGING_CUTOFF;

        // Check for zero value
        require(transferAmount > 0, "Amount is too small for bridging");

        // Update OLAS leftovers
        olasLeftovers = olasAmount - transferAmount;

        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, transferAmount);

        // Bridge arguments
        bytes32 olasBurner = bytes32(uint256(uint160(OLAS_BURNER)));
        uint256 localNonce = nonce;

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).transferTokens(olas, transferAmount, WORMHOLE_ETH_CHAIN_ID, olasBurner, 0, uint32(nonce));

        // Adjust nonce
        nonce = localNonce + 1;

        emit OLASJourneyToAscendance(olas, transferAmount);

        return msg.value;
    }
}
