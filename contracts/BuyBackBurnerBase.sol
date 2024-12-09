// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BuyBackBurner} from "./BuyBackBurner.sol";

// Balancer interface
interface IBalancer {
    enum SwapKind { GIVEN_IN, GIVEN_OUT }

    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    /// @dev Swaps tokens on Balancer.
    function swap(SingleSwap memory singleSwap, FundManagement memory funds, uint256 limit, uint256 deadline)
    external payable returns (uint256);
}

// Bridge interface
interface IBridge {
    /// @dev Initiates a withdrawal from L2 to L1 to a target account on L1.
    /// @param l2Token Address of the L2 token to withdraw.
    /// @param to Recipient account on L1.
    /// @param amount Amount of the L2 token to withdraw.
    /// @param minGasLimit Minimum gas limit to use for the transaction.
    /// @param extraData Extra data attached to the withdrawal.
    function withdrawTo(address l2Token, address to, uint256 amount, uint32 minGasLimit, bytes calldata extraData) external;
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);

    /// @dev Gets the amount of tokens owned by a specified account.
    /// @param account Account address.
    /// @return Amount of tokens owned.
    function balanceOf(address account) external view returns (uint256);
}

/// @title BuyBackBurnerBase - BuyBackBurner implementation contract for Base
contract BuyBackBurnerBase is BuyBackBurner {
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;

    // Balancer vault address
    address public balancerVault;
    // Balancer pool Id
    bytes32 public balancerPoolId;

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @return leftovers msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(
        uint256 olasAmount,
        uint256 tokenGasLimit,
        bytes memory
    ) internal virtual override returns (uint256 leftovers) {
        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, olasAmount);

        // Check for sufficient minimum gas limit
        if (tokenGasLimit < TOKEN_GAS_LIMIT) {
            tokenGasLimit = TOKEN_GAS_LIMIT;
        }

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).withdrawTo(olas, OLAS_BURNER, olasAmount, uint32(tokenGasLimit), "0x");

        leftovers = msg.value;
    }

    /// @dev Performs swap for OLAS on DEX.
    /// @param nativeTokenAmount Native token amount.
    /// @return olasAmount Obtained OLAS amount.
    function _performSwap(uint256 nativeTokenAmount) internal virtual override returns (uint256 olasAmount) {
        // Approve nativeToken for the Balancer Vault
        IERC20(nativeToken).approve(balancerVault, nativeTokenAmount);

        // Prepare Balancer data for the nativeToken-OLAS pool
        IBalancer.SingleSwap memory singleSwap = IBalancer.SingleSwap(balancerPoolId, IBalancer.SwapKind.GIVEN_IN,
            nativeToken, olas, nativeTokenAmount, "0x");
        IBalancer.FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false,
            payable(address(this)), false);

        // Perform swap
        olasAmount = IBalancer(balancerVault).swap(singleSwap, fundManagement, 0, block.timestamp);
    }

    /// @dev BuyBackBurner initializer.
    /// @param payload Initializer payload.
    function _initialize(bytes memory payload) internal override virtual {
        (olas, nativeToken, oracle, l2TokenRelayer, balancerVault, balancerPoolId, maxSlippage) =
            abi.decode(payload, (address, address, address, address, address, bytes32, uint256));
    }
}