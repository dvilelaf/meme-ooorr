// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BuyBackBurnerBase} from "./BuyBackBurnerBase.sol";

// Bridge interface
interface IBridge {
    /// @dev Initiates a token withdrawal from Arbitrum to Ethereum
    /// @param l1Token L1 address of token.
    /// @param to Destination address.
    /// @param amount Amount of tokens withdrawn.
    /// @return Encoded Unique identifier for withdrawal.
    function outboundTransfer(address l1Token, address to, uint256 amount, bytes calldata data)
        external payable returns (bytes memory);
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

/// @title BuyBackBurnerArbitrum - BuyBackBurner implementation contract for Arbitrum
contract BuyBackBurnerArbitrum is BuyBackBurnerBase {
    // OLAS address on L1
    address public olasL1;

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @return leftovers msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(
        uint256 olasAmount,
        uint256,
        bytes memory
    ) internal virtual override returns (uint256 leftovers) {
        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, olasAmount);

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).outboundTransfer(olasL1, OLAS_BURNER, olasAmount, "0x");

        leftovers = msg.value;
    }

    /// @dev BuyBackBurner initializer.
    /// @param payload Initializer payload.
    function _initialize(bytes memory payload) internal override virtual {
        (olas, nativeToken, oracle, l2TokenRelayer, balancerVault, balancerPoolId, maxSlippage) =
            abi.decode(payload, (address, address, address, address, address, bytes32, uint256));

        // Calculate OLAS L1 address
        uint160 offset = uint160(0x1111000000000000000000000000000000001111);
        unchecked {
            olasL1 = address(uint160(olas) - offset);
        }
    }
}