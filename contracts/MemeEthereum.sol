// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

interface IWETH {
    function deposit() external payable;
}

/// @title MemeEthereum - a smart contract factory for Meme Token creation on Ethereum.
contract MemeEthereum is MemeFactory {
    // Base UniswapV3 pool cardinality that corresponds to 720 seconds window (720 / 12 seconds per block)
    uint16 public constant POOL_CARDINALITY = 60;

    /// @dev MemeEthereum constructor
    constructor(
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue
    ) MemeFactory(_nativeToken, _uniV3PositionManager, _buyBackBurner, _minNativeTokenValue) {}

    /// @dev Gets required UniswapV3 pool cardinality.
    /// @return Pool cardinality.
    function _observationCardinalityNext() internal virtual override pure returns (uint16) {
        return POOL_CARDINALITY;
    }

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @notice MemeEthereum has no launch campaign, hence x = 0.
    /// @return Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign() internal override view returns (uint256) {
        return scheduledForAscendance;
    }

    /// @dev Native token amount to wrap.
    /// @param nativeTokenAmount Native token amount to be wrapped.
    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
