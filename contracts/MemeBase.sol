// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory, Meme} from "./MemeFactory.sol";

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
