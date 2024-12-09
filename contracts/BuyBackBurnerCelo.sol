// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BuyBackBurner} from "./BuyBackBurner.sol";

// Bridge interface
interface IBridge {
    /// @dev Transfers tokens through Wormhole portal.
    function transferTokens(address token, uint256 amount, uint16 recipientChain, bytes32 recipient, uint256 arbiterFee,
        uint32 nonce) external payable returns (uint64 sequence);
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

// UniswapV2 interface
interface IUniswap {
    /// @dev Swaps an exact amount of input tokens along the route determined by the path.
    function swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, address[] calldata path, address to,
        uint256 deadline) external returns (uint256[] memory amounts);
}

/// @title BuyBackBurnerCelo - BuyBackBurner implementation contract for Celo
contract BuyBackBurnerCelo is BuyBackBurner {
    // Wormhole bridging decimals cutoff
    uint256 public constant WORMHOLE_BRIDGING_CUTOFF = 1e10;
    // Ethereum mainnet chain Id in Wormhole format
    uint16 public constant WORMHOLE_ETH_CHAIN_ID = 2;

    // Ubeswap router address
    address public router;

    // Contract nonce
    uint256 public nonce;
    // OLAS leftovers from bridging
    uint256 public olasLeftovers;

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @return leftovers msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(
        uint256 olasAmount,
        uint256,
        bytes memory
    ) internal virtual override returns (uint256 leftovers) {
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

        leftovers = msg.value;
    }

    /// @dev Performs swap for OLAS on DEX.
    /// @param nativeTokenAmount Native token amount.
    /// @return olasAmount Obtained OLAS amount.
    function _performSwap(uint256 nativeTokenAmount) internal virtual override returns (uint256 olasAmount) {
        // Approve nativeToken for the router
        IERC20(nativeToken).approve(router, nativeTokenAmount);

        address[] memory path = new address[](2);
        path[0] = nativeToken;
        path[1] = olas;

        // Swap nativeToken for OLAS
        uint256[] memory amounts = IUniswap(router).swapExactTokensForTokens(
            nativeTokenAmount,
            0,
            path,
            address(this),
            block.timestamp
        );

        // Record OLAS amount
        olasAmount = amounts[1];
    }

    /// @dev BuyBackBurner initializer.
    /// @param payload Initializer payload.
    function _initialize(bytes memory payload) internal override virtual {
        (olas, nativeToken, oracle, l2TokenRelayer, router, maxSlippage) =
            abi.decode(payload, (address, address, address, address, address, uint256));
    }
}