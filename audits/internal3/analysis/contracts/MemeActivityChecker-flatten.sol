// Sources flattened with hardhat v2.22.15 https://hardhat.org

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// Meme Factory interface
interface IMemeFactory {
    function mapAccountActivities(address multisig) external view returns (uint256);
}

/// @dev Zero address.
error ZeroAddress();

/// @dev Zero value.
error ZeroValue();

/// @title MemeActivityChecker - Smart contract for meme contract interaction service staking activity check
/// @author Aleksandr Kuperman - <aleksandr.kuperman@valory.xyz>
/// @author Andrey Lebedev - <andrey.lebedev@valory.xyz>
/// @author David Vilela - <david.vilelafreire@valory.xyz>
contract MemeActivityChecker {
    // Liveness ratio in the format of 1e18
    uint256 public immutable livenessRatio;
    // Meme Factory contract address
    address public immutable memeFactory;

    /// @dev StakingNativeToken initialization.
    /// @param _memeFactory Meme Factory contract address.
    /// @param _livenessRatio Liveness ratio in the format of 1e18.
    constructor(address _memeFactory, uint256 _livenessRatio) {
        // Check the zero address
        if (_memeFactory == address(0)) {
            revert ZeroAddress();
        }

        // Check for zero value
        if (_livenessRatio == 0) {
            revert ZeroValue();
        }

        memeFactory = _memeFactory;
        livenessRatio = _livenessRatio;
    }

    /// @dev Gets service multisig nonces.
    /// @param multisig Service multisig address.
    /// @return nonces Set of a single service multisig nonce.
    function getMultisigNonces(address multisig) external view virtual returns (uint256[] memory nonces) {
        nonces = new uint256[](1);
        // The nonce is equal to the meme factory contract interaction corresponding to a multisig activity
        nonces[0] = IMemeFactory(memeFactory).mapAccountActivities(multisig);
    }

    /// @dev Checks if the service multisig liveness ratio passes the defined liveness threshold.
    /// @notice The formula for calculating the ratio is the following:
    ///         currentNonce - service multisig nonce at time now (block.timestamp);
    ///         lastNonce - service multisig nonce at the previous checkpoint or staking time (tsStart);
    ///         ratio = (currentNonce - lastNonce) / (block.timestamp - tsStart).
    /// @param curNonces Current service multisig set of a single nonce.
    /// @param lastNonces Last service multisig set of a single nonce.
    /// @param ts Time difference between current and last timestamps.
    /// @return ratioPass True, if the liveness ratio passes the check.
    function isRatioPass(
        uint256[] memory curNonces,
        uint256[] memory lastNonces,
        uint256 ts
    ) external view virtual returns (bool ratioPass) {
        // If the checkpoint was called in the exact same block, the ratio is zero
        // If the current nonce is not greater than the last nonce, the ratio is zero
        if (ts > 0 && curNonces[0] > lastNonces[0]) {
            uint256 ratio = ((curNonces[0] - lastNonces[0]) * 1e18) / ts;
            ratioPass = (ratio >= livenessRatio);
        }
    }
}
