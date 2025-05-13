# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 David Vilela Freire
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains round behaviours of MemeooorrAbciApp."""

import json
import math
from abc import ABC
from typing import Any, Generator, Optional, Tuple, Type, cast

from aea.configurations.data_types import PublicId

from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    ActionPreparationPayload,
    ActionPreparationRound,
    CallCheckpointPayload,
    CallCheckpointRound,
    CheckFundsPayload,
    CheckFundsRound,
    CheckStakingPayload,
    CheckStakingRound,
    Event,
    PostTxDecisionMakingPayload,
    PostTxDecisionMakingRound,
    PullMemesPayload,
    PullMemesRound,
    StakingState,
    TransactionLoopCheckPayload,
    TransactionLoopCheckRound,
)
from packages.valory.contracts.gnosis_safe.contract import GnosisSafeContract
from packages.valory.contracts.mech_marketplace.contract import MechMarketplace
from packages.valory.contracts.staking_activity_checker.contract import (
    StakingActivityCheckerContract,
)
from packages.valory.contracts.staking_token.contract import StakingTokenContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.mech_interact_abci.behaviours.round_behaviour import (
    MechRequestBehaviour,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)
from packages.valory.skills.transaction_settlement_abci.rounds import TX_HASH_LENGTH


WaitableConditionType = Generator[None, None, Optional[bool]]


ETH_PRICE = 0

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
CHECKPOINT_FILENAME = "checkpoint.txt"
READ_MODE = "r"
WRITE_MODE = "w"

EMPTY_CALL_DATA = b"0x"
SAFE_GAS = 0
ZERO_VALUE = 0
TWO_MINUTES = 120
SUMMON_BLOCK_DELTA = 100000

# Liveness ratio from the staking contract is expressed in calls per 10**18 seconds.
LIVENESS_RATIO_SCALE_FACTOR = 10**18

# A safety margin in case there is a delay between the moment the KPI condition is
# satisfied, and the moment where the checkpoint is called.

# The REQUIRED_REQUESTS_SAFETY_MARGIN is set to 0 since we don't need additional buffer for mech requests.
# This differs from the trader implementation where a safety margin was used to account for potential delays.
# We may revisit this in the future if we need to add a safety margin for similar reasons.
REQUIRED_REQUESTS_SAFETY_MARGIN = 0


class ChainBehaviour(MemeooorrBaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """ChainBehaviour"""

    def _build_safe_tx_hash(
        self,
        to_address: str,
        value: int = ZERO_VALUE,
        data: bytes = EMPTY_CALL_DATA,
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash for a tx."""

        self.context.logger.info(
            f"Preparing Safe transaction [{self.synchronized_data.safe_contract_address}] value={value}"
        )

        # Prepare the safe transaction
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=to_address,
            value=value,
            data=data,
            safe_tx_gas=SAFE_GAS,
            chain_id=self.get_chain_id(),
        )

        # Check for errors
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                "Couldn't get safe tx hash. Expected response performative "
                f"{ContractApiMessage.Performative.STATE.value!r}, "  # type: ignore
                f"received {response_msg.performative.value!r}: {response_msg}."
            )
            return None

        # Extract the hash and check it has the correct length
        tx_hash: Optional[str] = cast(str, response_msg.state.body.get("tx_hash", None))

        if tx_hash is None or len(tx_hash) != TX_HASH_LENGTH:
            self.context.logger.error(
                "Something went wrong while trying to get the safe transaction hash. "
                f"Invalid hash {tx_hash!r} was returned."
            )
            return None

        # Transaction to hex
        tx_hash = tx_hash[2:]  # strip the 0x

        safe_tx_hash = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=value,
            safe_tx_gas=SAFE_GAS,
            to_address=to_address,
            data=data,
        )

        self.context.logger.info(f"Safe transaction hash is {safe_tx_hash}")

        return safe_tx_hash

    def default_error(
        self, contract_id: str, contract_callable: str, response_msg: ContractApiMessage
    ) -> None:
        """Return a default contract interaction error message."""
        self.context.logger.error(
            f"Could not successfully interact with the {contract_id} contract "
            f"using {contract_callable!r}: {response_msg}"
        )

    def contract_interaction_error(
        self, contract_id: str, contract_callable: str, response_msg: ContractApiMessage
    ) -> None:
        """Return a contract interaction error message."""
        # contracts can only return one message, i.e., multiple levels cannot exist.
        for level in ("info", "warning", "error"):
            msg = response_msg.raw_transaction.body.get(level, None)
            logger = getattr(self.context.logger, level)
            if msg is not None:
                logger(msg)
                return

        self.default_error(contract_id, contract_callable, response_msg)

    def contract_interact(  # pylint: disable=too-many-arguments
        self,
        performative: ContractApiMessage.Performative,
        contract_address: str,
        contract_public_id: PublicId,
        contract_callable: str,
        data_key: str,
        **kwargs: Any,
    ) -> Generator[None, None, Optional[Any]]:
        """Interact with a contract."""
        contract_id = str(contract_public_id)

        self.context.logger.info(
            f"Interacting with contract {contract_id} at address {contract_address}\n"
            f"Calling method {contract_callable} with parameters: {kwargs}"
        )

        response_msg = yield from self.get_contract_api_response(
            performative,
            contract_address,
            contract_id,
            contract_callable,
            **kwargs,
        )

        self.context.logger.info(f"Contract response: {response_msg}")

        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.default_error(contract_id, contract_callable, response_msg)
            return None

        data = response_msg.raw_transaction.body.get(data_key, None)
        if data is None:
            self.contract_interaction_error(
                contract_id, contract_callable, response_msg
            )
            return None

        return data

    def _get_liveness_ratio(self, chain: str) -> Generator[None, None, Optional[int]]:
        liveness_ratio = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.activity_checker_contract_address,
            contract_public_id=StakingActivityCheckerContract.contract_id,
            contract_callable="liveness_ratio",
            data_key="data",
            chain_id=chain,
        )

        if liveness_ratio is None or liveness_ratio == 0:
            self.context.logger.error(
                f"Invalid value for liveness ratio: {liveness_ratio}"
            )

        return liveness_ratio

    def _get_liveness_period(self, chain: str) -> Generator[None, None, Optional[int]]:
        liveness_period = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="get_liveness_period",
            data_key="data",
            chain_id=chain,
        )

        if liveness_period is None or liveness_period == 0:
            self.context.logger.error(
                f"Invalid value for liveness period: {liveness_period}"
            )

        return liveness_period

    def _get_ts_checkpoint(self, chain: str) -> Generator[None, None, Optional[int]]:
        """Get the ts checkpoint"""
        ts_checkpoint = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="ts_checkpoint",
            data_key="data",
            chain_id=chain,
        )
        return ts_checkpoint

    def _calculate_min_num_of_safe_tx_required(
        self, chain: str
    ) -> Generator[None, None, Optional[int]]:
        """Calculates the minimun number of tx to hit to unlock the staking rewards"""
        liveness_ratio = yield from self._get_liveness_ratio(chain)
        liveness_period = yield from self._get_liveness_period(chain)
        if not liveness_ratio or not liveness_period:
            return None

        current_timestamp = int(
            self.round_sequence.last_round_transition_timestamp.timestamp()
        )

        last_ts_checkpoint = yield from self._get_ts_checkpoint(
            chain=self.get_chain_id()
        )
        if last_ts_checkpoint is None:
            return None

        min_num_of_safe_tx_required = (
            math.ceil(
                max(liveness_period, (current_timestamp - last_ts_checkpoint))
                * liveness_ratio
                / LIVENESS_RATIO_SCALE_FACTOR
            )
            + REQUIRED_REQUESTS_SAFETY_MARGIN
        )

        return min_num_of_safe_tx_required

    def _get_multisig_nonces(
        self, chain: str, multisig: str
    ) -> Generator[None, None, Optional[int]]:
        multisig_nonces = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.activity_checker_contract_address,
            contract_public_id=StakingActivityCheckerContract.contract_id,
            contract_callable="get_multisig_nonces",
            data_key="data",
            chain_id=chain,
            multisig=multisig,
        )
        if multisig_nonces is None or len(multisig_nonces) == 0:
            return None
        return multisig_nonces[0]

    def _get_multisig_nonces_since_last_cp(
        self, chain: str, multisig: str
    ) -> Generator[None, None, Optional[int]]:
        multisig_nonces = yield from self._get_multisig_nonces(chain, multisig)
        if multisig_nonces is None:
            return None

        service_info = yield from self._get_service_info(chain)
        if service_info is None or len(service_info) == 0 or len(service_info[2]) == 0:
            self.context.logger.error(f"Error fetching service info {service_info}")
            return None

        multisig_nonces_on_last_checkpoint = service_info[2][0]

        multisig_nonces_since_last_cp = (
            multisig_nonces - multisig_nonces_on_last_checkpoint
        )
        self.context.logger.info(
            f"Number of safe transactions since last checkpoint: {multisig_nonces_since_last_cp}"
        )
        return multisig_nonces_since_last_cp

    def _get_service_staking_state(
        self, chain: str
    ) -> Generator[None, None, Optional[StakingState]]:
        self.context.logger.info(f"Getting service staking state for chain {chain}")
        self.context.logger.info(f"service_id: {self.params.on_chain_service_id}")
        self.context.logger.info(
            f"staking_token_contract_address: {self.params.staking_token_contract_address}"
        )

        service_id = self.params.on_chain_service_id
        if service_id is None:
            self.context.logger.warning(
                "Cannot perform any staking-related operations without a configured on-chain service id. "
                "Assuming service status 'UNSTAKED'."
            )
            return StakingState.UNSTAKED

        staking_token_contract_address = self.params.staking_token_contract_address
        if staking_token_contract_address == NULL_ADDRESS:
            self.context.logger.warning("The staking contract has not been configured")
            return StakingState.UNSTAKED

        service_staking_state = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="get_service_staking_state",
            data_key="data",
            service_id=service_id,
            chain_id=chain,
        )
        if service_staking_state is None:
            self.context.logger.warning(
                "Error fetching staking state for service."
                "Assuming service status 'UNSTAKED'."
            )
            return StakingState.UNSTAKED

        return StakingState(service_staking_state)

    def _is_staking_kpi_met(  # pylint: disable=too-many-return-statements
        self,
    ) -> Generator[
        None, None, Optional[bool]
    ]:  # pylint: disable=too-many-return-statements
        """Return whether the staking KPI has been met (only for staked services)."""
        # Check if service is staked
        service_staking_state = yield from self._get_service_staking_state(
            chain=self.get_chain_id()
        )

        self.context.logger.info(f"service_staking_state: {service_staking_state}")

        if service_staking_state != StakingState.STAKED:
            self.context.logger.info("Service is not staked")
            return False

        self.context.logger.info(
            f"Getting mech marketplace request count for {self.synchronized_data.safe_contract_address} from {self.params.mech_marketplace_config.mech_marketplace_address}"
        )
        # Get mech marketplace request count for this safe address
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,
            contract_address=self.params.mech_marketplace_config.mech_marketplace_address,
            contract_id=str(MechMarketplace.contract_id),
            contract_callable="get_request_count",
            chain_id=self.get_chain_id(),
            address=self.synchronized_data.safe_contract_address,
        )

        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the mech marketplace request count: {response_msg}"
            )
            return None

        # Assuming the contract API framework returns the count under the key "requests_count"
        # Adjust the key if necessary based on actual framework behavior for view functions.

        mech_request_count = cast(
            int, response_msg.state.body.get("requests_count", None)
        )

        if mech_request_count is None:
            self.context.logger.error(
                f"Could not parse mech marketplace request count from response: {response_msg.state.body}"
            )
            return None
        self.context.logger.info(f"{mech_request_count=}")

        # Get service info and previous mech request count
        service_info = yield from self._get_service_info(chain=self.get_chain_id())
        if service_info is None or len(service_info) == 0 or len(service_info[2]) == 0:
            self.context.logger.error(f"Error fetching service info {service_info}")
            return None

        self.context.logger.info(f"service_info: {service_info}")

        # Use requests count (position [1]) instead of multisig nonces (position [0])
        mech_request_count_on_last_checkpoint = service_info[2][1]
        self.context.logger.info(f"{mech_request_count_on_last_checkpoint=}")

        # Get last checkpoint timestamp
        last_ts_checkpoint = yield from self._get_ts_checkpoint(
            chain=self.get_chain_id()
        )
        if last_ts_checkpoint is None:
            self.context.logger.error("Could not get the last checkpoint timestamp")
            return None
        self.context.logger.info(f"{last_ts_checkpoint=}")

        # Get liveness period and ratio
        liveness_period = yield from self._get_liveness_period(
            chain=self.get_chain_id()
        )
        if liveness_period is None:
            self.context.logger.error("Could not get the liveness period")
            return None
        self.context.logger.info(f"{liveness_period=}")

        liveness_ratio = yield from self._get_liveness_ratio(chain=self.get_chain_id())
        if liveness_ratio is None:
            self.context.logger.error("Could not get the liveness ratio")
            return None
        self.context.logger.info(f"{liveness_ratio=}")

        # Calculate requests since last checkpoint
        mech_requests_since_last_cp = (
            mech_request_count - mech_request_count_on_last_checkpoint
        )
        self.context.logger.info(f"{mech_requests_since_last_cp=}")

        # Calculate current timestamp from round sequence
        current_timestamp = int(
            self.round_sequence.last_round_transition_timestamp.timestamp()
        )
        self.context.logger.info(f"{current_timestamp=}")

        self.context.logger.info(
            f"Calculating required_mech_requests with params: "
            f"liveness_period={liveness_period}, "
            f"current_timestamp={current_timestamp}, "
            f"last_ts_checkpoint={last_ts_checkpoint}, "
            f"liveness_ratio={liveness_ratio}, "
            f"LIVENESS_RATIO_SCALE_FACTOR={LIVENESS_RATIO_SCALE_FACTOR}, "
            f"REQUIRED_REQUESTS_SAFETY_MARGIN={REQUIRED_REQUESTS_SAFETY_MARGIN}"
        )

        # Calculate required requests
        required_mech_requests = (
            math.ceil(
                max(liveness_period, (current_timestamp - last_ts_checkpoint))
                * liveness_ratio
                / LIVENESS_RATIO_SCALE_FACTOR
            )
            + REQUIRED_REQUESTS_SAFETY_MARGIN
        )
        self.context.logger.info(f"{required_mech_requests=}")

        self.context.logger.info(
            f"Mech requests since last checkpoint: {mech_requests_since_last_cp} vs required: {required_mech_requests}"
        )

        # Return whether KPI is met
        return mech_requests_since_last_cp >= required_mech_requests

    def _get_service_info(
        self, chain: str
    ) -> Generator[None, None, Optional[Tuple[Any, Any, Tuple[Any, Any]]]]:
        """Get the service info."""
        service_id = self.params.on_chain_service_id
        if service_id is None:
            self.context.logger.warning(
                "Cannot perform any staking-related operations without a configured on-chain service id. "
                "Assuming service status 'UNSTAKED'."
            )
            return None

        service_info = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="get_service_info",
            data_key="data",
            service_id=service_id,
            chain_id=chain,
        )
        return service_info


class CheckFundsBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """CheckFundsBehaviour"""

    matching_round: Type[AbstractRound] = CheckFundsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = yield from self.get_event()

            payload = CheckFundsPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> Generator[None, None, str]:
        """Get the next event"""

        # Gas check
        native_balances = yield from self.get_native_balance()
        agent_native_balance = native_balances["agent"]

        if not agent_native_balance:
            return Event.NO_FUNDS.value

        if agent_native_balance < self.params.minimum_gas_balance:
            self.context.logger.info(
                f"Agent has insufficient funds for gas: {agent_native_balance} < {self.params.minimum_gas_balance}"
            )
            return Event.NO_FUNDS.value

        return Event.DONE.value


class CheckStakingBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """CheckStakingBehaviour"""

    matching_round: Type[AbstractRound] = CheckStakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            is_staking_kpi_met = yield from self._is_staking_kpi_met()

            self.context.logger.info(f"Is staking KPI met? {is_staking_kpi_met}")

            payload = CheckStakingPayload(
                sender=self.context.agent_address,
                is_staking_kpi_met=is_staking_kpi_met,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class PullMemesBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """PullMemesBehaviour"""

    matching_round: Type[AbstractRound] = PullMemesRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            meme_coins = yield from self.get_meme_coins()
            self.context.logger.info(f"Meme token list: {meme_coins}")

            payload = PullMemesPayload(
                sender=self.context.agent_address,
                meme_coins=json.dumps(meme_coins, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_block_number(self) -> Generator[None, None, Optional[int]]:
        """Get the block number"""

        # Call the ledger connection (equivalent to web3.py)
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_block_number",
            chain_id=self.get_chain_id(),
        )

        # Check for errors on the response
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving block number: {ledger_api_response}"
            )
            return None

        # Extract and return the block number
        block_number = cast(
            int, ledger_api_response.state.body["get_block_number_result"]
        )

        self.context.logger.error(f"Got block number: {block_number}")

        return block_number


class ActionPreparationBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """ActionPreparationBehaviour"""

    matching_round: Type[AbstractRound] = ActionPreparationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash = yield from self.get_tx_hash()

            payload = ActionPreparationPayload(
                sender=self.context.agent_address,
                tx_hash=tx_hash,
                tx_submitter=self.matching_round.auto_round_id(),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Get the action transaction hash"""

        token_action = self.synchronized_data.token_action

        # Action finished if we already have a final_tx_hash at this point
        if self.synchronized_data.final_tx_hash is not None:
            yield from self.post_action()
            return ""

        if not token_action:
            return None

        action = token_action["action"]

        contract_callable = f"build_{action}_tx"

        kwargs = {}

        if action in ["summon"]:
            kwargs["token_name"] = token_action["token_name"]
            kwargs["token_ticker"] = token_action["token_ticker"]
            kwargs["token_supply"] = int(token_action["token_supply"])

        if action in ["heart", "unleash"]:
            kwargs["meme_nonce"] = token_action["token_nonce"]

        if action in ["collect", "purge"]:
            kwargs["meme_address"] = token_action["token_address"]

        self.context.logger.info(f"Preparing the {action} transaction: kwargs={kwargs}")

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable=contract_callable,
            chain_id=self.get_chain_id(),
            **kwargs,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while building the {action} tx: {response_msg}"
            )
            return None

        data_bytes: Optional[bytes] = cast(
            bytes, response_msg.raw_transaction.body.get("data", None)
        )

        # Ensure that the data is not None
        if data_bytes is None:
            self.context.logger.error(
                f"Error while preparing the transaction: {response_msg}"
            )
            return None

        data_hex = data_bytes.hex()
        self.context.logger.info(f"Tx data is {data_hex}")

        # Check for errors
        if data_hex is None:
            return None

        # Prepare safe transaction
        value = (
            ZERO_VALUE
            if action not in ["summon", "heart"]
            else int(token_action["amount"])
        )  # to wei
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.get_meme_factory_address(),
            data=bytes.fromhex(data_hex),
            value=value,
        )

        return safe_tx_hash

    def post_action(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, None]:
        """Post action"""
        token_action = self.synchronized_data.token_action
        token_nonce = yield from self.get_token_nonce()

        self.context.logger.info(f"The {token_action['action']} has finished")

        if not token_nonce:
            self.context.logger.error("Token nonce is none")
            return

        if token_action == "summon":  # nosec
            # Read previous tokens from db
            db_data = yield from self._read_kv(keys=("tokens",))

            if db_data is None:
                self.context.logger.error(
                    "Error while loading tokens from the database"
                )
                tokens = []
            else:
                tokens = json.loads(db_data["tokens"]) if db_data["tokens"] else []

            # Write token to db
            token_action = self.synchronized_data.token_action
            token_data = {
                "token_name": token_action["token_name"],
                "token_ticker": token_action["token_ticker"],
                "total_supply": int(token_action["total_supply"]),
                "token_nonce": token_nonce,
            }
            tokens.append(token_data)
            yield from self._write_kv(
                {"summoned_tokens": json.dumps(tokens, sort_keys=True)}
            )
            self.context.logger.info("Wrote latest token to db")

            yield from self._write_kv(
                {"last_summon_timestamp": str(self.get_sync_timestamp())}
            )

    def get_token_nonce(
        self,
    ) -> Generator[None, None, Optional[int]]:
        """Get the data from the deployment event"""

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_token_data",
            tx_hash=self.synchronized_data.final_tx_hash,
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the token data: {response_msg}")
            return None

        token_nonce = cast(int, response_msg.state.body.get("token_nonce", None))
        self.context.logger.info(f"Token nonce is {token_nonce}")
        return token_nonce


class PostTxDecisionMakingBehaviour(
    ChainBehaviour
):  # pylint: disable=too-many-ancestors
    """PostTxDecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = PostTxDecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = "None"

            self.context.logger.info(
                f"Checking the tx submitter is the current round: {self.synchronized_data.tx_submitter}"
            )

            if (
                self.synchronized_data.tx_submitter
                == CallCheckpointBehaviour.matching_round.auto_round_id()
            ):
                event = Event.DONE.value

            if (
                self.synchronized_data.tx_submitter
                == ActionPreparationBehaviour.matching_round.auto_round_id()
            ):
                event = Event.ACTION.value

            if (
                self.synchronized_data.tx_submitter
                == MechRequestBehaviour.matching_round.auto_round_id()
            ):
                event = Event.MECH.value

            payload = PostTxDecisionMakingPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class CallCheckpointBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """Behaviour that calls the checkpoint contract function if the service is staked and if it is necessary."""

    matching_round = CallCheckpointRound

    def async_act(self) -> Generator:
        """Do the action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            checkpoint_tx_hex = yield from self.get_checkpoint_tx_hash()

            payload = CallCheckpointPayload(
                sender=self.context.agent_address,
                tx_submitter=self.matching_round.auto_round_id(),
                tx_hash=checkpoint_tx_hex,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()
            self.set_done()

    def get_checkpoint_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Get the checkpoint tx hash"""
        checkpoint_tx_hex = None

        staking_state = yield from self._get_service_staking_state(
            chain=self.get_chain_id()
        )

        if staking_state == StakingState.UNSTAKED:
            return checkpoint_tx_hex

        is_checkpoint_reached = yield from self._check_if_checkpoint_reached(
            chain=self.get_chain_id()
        )

        self.context.logger.info(
            f"Staking state: {staking_state}  is_checkpoint_reached: {is_checkpoint_reached}"
        )

        if is_checkpoint_reached and staking_state == StakingState.STAKED:
            self.context.logger.info("Checkpoint reached! Preparing checkpoint tx..")
            checkpoint_tx_hex = yield from self._prepare_checkpoint_tx(
                chain=self.get_chain_id()
            )

        return checkpoint_tx_hex

    def _get_next_checkpoint(self, chain: str) -> Generator[None, None, Optional[int]]:
        """Get the timestamp in which the next checkpoint is reached."""
        next_checkpoint = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="get_next_checkpoint_ts",
            data_key="data",
            chain_id=chain,
        )
        return next_checkpoint

    def _check_if_checkpoint_reached(
        self, chain: str
    ) -> Generator[None, None, Optional[bool]]:
        next_checkpoint = yield from self._get_next_checkpoint(chain)
        if next_checkpoint is None:
            return False

        if next_checkpoint == 0:
            return True

        synced_timestamp = int(
            self.round_sequence.last_round_transition_timestamp.timestamp()
        )
        self.context.logger.info(
            f"Next checkpoint: {next_checkpoint} vs synced timestamp: {synced_timestamp}"
        )
        return next_checkpoint <= synced_timestamp

    def _prepare_checkpoint_tx(
        self, chain: str
    ) -> Generator[None, None, Optional[str]]:
        checkpoint_data = yield from self.contract_interact(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,
            contract_address=self.params.staking_token_contract_address,
            contract_public_id=StakingTokenContract.contract_id,
            contract_callable="build_checkpoint_tx",
            data_key="data",
            chain_id=chain,
        )

        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.staking_token_contract_address,
            data=checkpoint_data,  # type: ignore
        )

        return safe_tx_hash


class TransactionLoopCheckBehaviour(
    ChainBehaviour
):  # pylint: disable=too-many-ancestors
    """Behaviour that checks if the transaction loop is still running."""

    matching_round = TransactionLoopCheckRound

    def async_act(self) -> Generator:
        """Do the action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"Checking if the transaction loop is still running. Counter: {self.synchronized_data.tx_loop_count} and increasing it by 1"
            )

            payload = TransactionLoopCheckPayload(
                sender=self.context.agent_address,
                counter=self.synchronized_data.tx_loop_count + 1,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
