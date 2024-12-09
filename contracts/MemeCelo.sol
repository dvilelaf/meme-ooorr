// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

/// @title MemeCelo - a smart contract factory for Meme Token creation on Celo.
contract MemeCelo is MemeFactory {
    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue
    ) MemeFactory(_olas, _nativeToken, _uniV3PositionManager, _buyBackBurner, _minNativeTokenValue) {}

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @notice MemeCelo has no launch campaign, hence x = 0.
    /// @return Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign() internal override view returns (uint256) {
        return scheduledForAscendance;
    }

    /// @dev Native token amount to wrap.
    /// @notice Celo's native token CELO is also an ERC20.
    function _wrap(uint256) internal virtual override {}
}
