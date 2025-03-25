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

"""This package contains the rounds of MemeooorrAbciApp."""

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, cast

from packages.dvilela.skills.memeooorr_abci.payloads import (
    ActionDecisionPayload,
    ActionPreparationPayload,
    ActionTweetPayload,
    CallCheckpointPayload,
    CheckFundsPayload,
    CheckStakingPayload,
    CollectFeedbackPayload,
    EngageTwitterPayload,
    LoadDatabasePayload,
    MechPayload,
    PostTxDecisionMakingPayload,
    PullMemesPayload,
    TransactionLoopCheckPayload,
)
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    BaseTxPayload,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
    MechMetadata,
)


class StakingState(Enum):
    """Staking state enumeration for the staking."""

    UNSTAKED = 0
    STAKED = 1
    EVICTED = 2


class Event(Enum):
    """MemeooorrAbciApp Events"""

    DONE = "done"
    NO_FUNDS = "no_funds"
    SETTLE = "settle"
    REFINE = "refine"
    ERROR = "ERROR"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    NOT_ENOUGH_FEEDBACK = "not_enough_feedback"
    WAIT = "wait"
    NO_MEMES = "no_memes"
    TO_DEPLOY = "to_deploy"
    TO_ACTION_TWEET = "to_action_tweet"
    ACTION = "action"
    MISSING_TWEET = "missing_tweet"
    MECH = "mech"
    RETRY = "retry"
    NONE = "none"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def participants_to_db(self) -> DeserializedCollection:
        """Get the participants_to_db."""
        return self._get_deserialized("participants_to_db")

    @property
    def persona(self) -> Optional[str]:
        """Get the persona."""
        return cast(str, self.db.get("persona", None))

    @property
    def meme_coins(self) -> List[Dict]:
        """Get the meme_coins."""
        return cast(list, json.loads(cast(str, self.db.get("meme_coins", "[]"))))

    @property
    def pending_tweet(self) -> Optional[List]:
        """Get the pending tweet."""
        pending_tweet_str = self.db.get("pending_tweet", None)
        return json.loads(pending_tweet_str) if pending_tweet_str else []

    @property
    def feedback(self) -> List:
        """Get the feedback."""
        feedback = self.db.get("feedback", None)
        return json.loads(feedback) if feedback else []

    @property
    def token_action(self) -> Dict:
        """Get the token action."""
        return cast(dict, json.loads(cast(str, self.db.get("token_action", "{}"))))

    @property
    def most_voted_tx_hash(self) -> Optional[str]:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def final_tx_hash(self) -> Optional[str]:
        """Get the verified tx hash."""
        return self.db.get("final_tx_hash", None)

    @property
    def tx_submitter(self) -> str:
        """Get the round that submitted a tx to transaction_settlement_abci."""
        return str(self.db.get_strict("tx_submitter"))

    @property
    def is_staking_kpi_met(self) -> Optional[bool]:
        """Get the is_staking_kpi_met."""
        return bool(self.db.get("is_staking_kpi_met", None))

    @property
    def participant_to_staking(self) -> DeserializedCollection:
        """Get the participants to the staking round."""
        return self._get_deserialized("participant_to_staking")

    @property
    def mech_requests(self) -> List[MechMetadata]:
        """Get the mech requests."""
        serialized = self.db.get("mech_requests", "[]")
        if serialized is None:
            serialized = "[]"
        requests = json.loads(serialized)
        return [MechMetadata(**metadata_item) for metadata_item in requests]

    @property
    def mech_responses(self) -> List[MechInteractionResponse]:
        """Get the mech responses."""
        responses = self.db.get("mech_responses", "[]")
        if isinstance(responses, str):
            responses = json.loads(responses)
        return [MechInteractionResponse(**response_item) for response_item in responses]

    @property
    def tx_loop_count(self) -> int:
        """Get the loop count for retrying transaction."""
        return int(self.db.get("tx_loop_count", 0))  # type: ignore

    @property
    def mech_for_twitter(self) -> bool:
        """Get the mech for twitter."""
        return bool(self.db.get("mech_for_twitter", False))


class EventRoundBase(CollectSameUntilThresholdRound):
    """EventRoundBase"""

    synchronized_data_class = SynchronizedData
    payload_class = BaseTxPayload  # will be overwritten
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            event = Event(self.most_voted_payload)
            return self.synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class DataclassEncoder(json.JSONEncoder):
    """A custom JSON encoder for dataclasses."""

    def default(self, o: Any) -> Any:
        """The default JSON encoder."""
        if is_dataclass(o):
            return asdict(o)
        return super().default(o)


class LoadDatabaseRound(CollectSameUntilThresholdRound):
    """LoadDatabaseRound"""

    payload_class = LoadDatabasePayload
    synchronized_data_class = SynchronizedData
    collection_key = get_name(SynchronizedData.participants_to_db)
    selection_key = (get_name(SynchronizedData.persona),)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            payload = dict(zip(self.selection_key, self.most_voted_payload_values))

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.persona): payload["persona"],
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    extended_requirements = ()


class CheckStakingRound(CollectSameUntilThresholdRound):
    """CheckStakingRound"""

    payload_class = CheckStakingPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            payload = CheckStakingPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.is_staking_kpi_met
                    ): payload.is_staking_kpi_met,
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class PullMemesRound(CollectSameUntilThresholdRound):
    """PullMemesRound"""

    payload_class = PullMemesPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            if self.most_voted_payload is None:
                meme_coins = []
            else:
                meme_coins = json.loads(self.most_voted_payload)

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.meme_coins): json.dumps(
                        meme_coins, sort_keys=True
                    ),
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    # Event.ROUND_TIMEOUT  # this needs to be mentioned for static checkers


class CollectFeedbackRound(CollectSameUntilThresholdRound):
    """CollectFeedbackRound"""

    payload_class = CollectFeedbackPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            feedback = json.loads(self.most_voted_payload)

            # API error
            if feedback is None:
                return self.synchronized_data, Event.ERROR

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.feedback): json.dumps(
                        feedback, sort_keys=True
                    )
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class EngageTwitterRound(CollectSameUntilThresholdRound):
    """EngageTwitterRound handles Twitter engagement decisions and mech requests"""

    payload_class = EngageTwitterPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(  # pylint: disable=too-many-return-statements
        self,
    ) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = EngageTwitterPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            self.context.logger.info(f"EngageTwitterRound payload recived: {payload}")
            event = Event(payload.event)
            # checking if event is mech
            if event == Event.MECH:
                # Handle mech requests if present
                if hasattr(payload, "mech_request") and payload.mech_request:
                    try:
                        mech_requests = json.loads(payload.mech_request)

                        # Update synchronized data with new mech requests
                        synchronized_data = self.synchronized_data.update(
                            synchronized_data_class=SynchronizedData,
                            **{
                                get_name(SynchronizedData.mech_requests): json.dumps(
                                    mech_requests, cls=DataclassEncoder
                                ),
                            },
                        )
                        return synchronized_data, Event.MECH
                    except json.JSONDecodeError as e:
                        self.context.logger.error(f"Failed to parse mech_request: {e}")
                        return self.synchronized_data, Event.ERROR

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.mech_for_twitter): False,
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


# This post mech round is the Happy path for the mech_interaction_abci
class MechRoundBase(CollectSameUntilThresholdRound):
    """Base class for Mech-related rounds to reduce code duplication"""

    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    # children classes should set this to the appropriate payload class
    payload_class = MechPayload

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # Create payload instance using the subclass's payload_class
            payload = self.payload_class(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            self.context.logger.info(
                f"{self.__class__.__name__} payload received: {payload}"
            )

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(
                        SynchronizedData.mech_for_twitter
                    ): payload.mech_for_twitter,
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class PostMechResponseRound(MechRoundBase):
    """PostMechResponseRound"""

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class FailedMechRequestRound(MechRoundBase):
    """FailedMechRequestRound"""

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT , Event.ERROR


class FailedMechResponseRound(MechRoundBase):
    """FailedMechResponseRound handles the case where the mech response is not received.

    It is always going to end in EngageTwitterRound.
    """

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT , Event.ERROR


class ActionDecisionRound(CollectSameUntilThresholdRound):
    """ActionDecisionRound"""

    payload_class = ActionDecisionPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.WAIT
            payload = ActionDecisionPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )
            event = Event(payload.event)
            synchronized_data = self.synchronized_data

            if event == Event.DONE:
                token_action = {
                    "action": payload.action,
                    "token_address": payload.token_address,
                    "token_nonce": payload.token_nonce,
                    "token_name": payload.token_name,
                    "token_ticker": payload.token_ticker,
                    "token_supply": payload.token_supply,
                    "amount": payload.amount,
                    "tweet": payload.tweet,
                }

                synchronized_data = synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(SynchronizedData.token_action): json.dumps(
                            token_action, sort_keys=True
                        ),
                    },
                )

                if payload.new_persona:
                    synchronized_data = synchronized_data.update(
                        synchronized_data_class=SynchronizedData,
                        **{
                            get_name(SynchronizedData.persona): payload.new_persona,
                        },
                    )

            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class ActionPreparationRound(CollectSameUntilThresholdRound):
    """ActionPreparationRound"""

    payload_class = ActionPreparationPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = ActionPreparationPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            # Error preparing the transaction
            if payload.tx_hash is None:
                return self.synchronized_data, Event.ERROR

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                    get_name(SynchronizedData.tx_submitter): payload.tx_submitter,
                },
            )

            # Transaction has been settled already
            if payload.tx_hash == "":
                return synchronized_data, Event.DONE

            # The tx has been prepared
            return synchronized_data, Event.SETTLE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class ActionTweetRound(EventRoundBase):
    """ActionTweetRound"""

    payload_class = ActionTweetPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.ERROR, Event.MISSING_TWEET


class CheckFundsRound(EventRoundBase):
    """CheckFundsRound"""

    payload_class = CheckFundsPayload  # type: ignore
    extended_requirements = ()
    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.NO_FUNDS


class PostTxDecisionMakingRound(EventRoundBase):
    """PostTxDecisionMakingRound"""

    payload_class = PostTxDecisionMakingPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.ACTION , Event.MECH


class CallCheckpointRound(CollectSameUntilThresholdRound):
    """A round for the checkpoint call preparation."""

    payload_class = CallCheckpointPayload
    synchronized_data_class = SynchronizedData
    extended_requirements = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = CallCheckpointPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            # Error preparing the transaction or no need to call the checkpoint
            if payload.tx_hash is None:
                return self.synchronized_data, Event.DONE

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                    get_name(SynchronizedData.tx_submitter): payload.tx_submitter,
                },
            )

            # The tx has been prepared
            return synchronized_data, Event.SETTLE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class TransactionLoopCheckRound(CollectSameUntilThresholdRound):
    """TransactionLoopCheckRound"""

    payload_class = TransactionLoopCheckPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            payload = TransactionLoopCheckPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            max_count = self.context.params.tx_loop_breaker_count

            if payload.counter >= max_count:
                self.context.logger.info(
                    f"Transaction loop breaker reached: {max_count}"
                )
                return self.synchronized_data, Event.DONE

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.tx_loop_count): payload.counter,
                },
            )

            return synchronized_data, Event.RETRY

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    extended_requirements = ()


class FinishedToResetRound(DegenerateRound):
    """FinishedToResetRound"""


class FinishedToSettlementRound(DegenerateRound):
    """FinishedToSettlementRound"""


class FinishedForMechRequestRound(DegenerateRound):
    """FinishedForMechRequestRound"""


class FinishedForMechResponseRound(DegenerateRound):
    """FinishedForMechResponseRound"""


class MemeooorrAbciApp(AbciApp[Event]):
    """MemeooorrAbciApp"""

    initial_round_cls: AppState = LoadDatabaseRound
    initial_states: Set[AppState] = {
        LoadDatabaseRound,
        PullMemesRound,
        ActionPreparationRound,
        PostTxDecisionMakingRound,
        PostMechResponseRound,
        TransactionLoopCheckRound,
        FailedMechRequestRound,
        FailedMechResponseRound,
    }
    transition_function: AbciAppTransitionFunction = {
        LoadDatabaseRound: {
            Event.DONE: CheckStakingRound,
            Event.NO_MAJORITY: LoadDatabaseRound,
            Event.ROUND_TIMEOUT: LoadDatabaseRound,
        },
        CheckStakingRound: {
            Event.DONE: PullMemesRound,
            Event.NO_MAJORITY: CheckStakingRound,
            Event.ROUND_TIMEOUT: CheckStakingRound,
        },
        PullMemesRound: {
            Event.DONE: CollectFeedbackRound,
            Event.NO_MAJORITY: PullMemesRound,
            Event.ROUND_TIMEOUT: PullMemesRound,
        },
        CollectFeedbackRound: {
            Event.DONE: EngageTwitterRound,
            Event.ERROR: EngageTwitterRound,
            Event.NO_MAJORITY: CollectFeedbackRound,
            Event.ROUND_TIMEOUT: CollectFeedbackRound,
        },
        EngageTwitterRound: {
            Event.DONE: ActionDecisionRound,
            Event.MECH: FinishedForMechRequestRound,
            Event.ERROR: EngageTwitterRound,
            Event.NO_MAJORITY: EngageTwitterRound,
            Event.ROUND_TIMEOUT: EngageTwitterRound,
        },
        ActionDecisionRound: {
            Event.DONE: ActionPreparationRound,
            Event.WAIT: CallCheckpointRound,
            Event.NO_MAJORITY: ActionDecisionRound,
            Event.ROUND_TIMEOUT: ActionDecisionRound,
        },
        ActionPreparationRound: {
            Event.DONE: ActionTweetRound,  # This will never happen
            Event.ERROR: CallCheckpointRound,
            Event.SETTLE: CheckFundsRound,
            Event.NO_MAJORITY: ActionPreparationRound,
            Event.ROUND_TIMEOUT: ActionPreparationRound,
        },
        ActionTweetRound: {
            Event.DONE: CallCheckpointRound,
            Event.ERROR: CallCheckpointRound,
            Event.MISSING_TWEET: CallCheckpointRound,
            Event.NO_MAJORITY: ActionTweetRound,
            Event.ROUND_TIMEOUT: ActionTweetRound,
        },
        CheckFundsRound: {
            Event.DONE: FinishedToSettlementRound,
            Event.NO_FUNDS: CheckFundsRound,
            Event.NO_MAJORITY: CheckFundsRound,
            Event.ROUND_TIMEOUT: CheckFundsRound,
        },
        PostTxDecisionMakingRound: {
            Event.DONE: FinishedToResetRound,
            Event.ACTION: ActionPreparationRound,
            Event.NO_MAJORITY: PostTxDecisionMakingRound,
            Event.ROUND_TIMEOUT: PostTxDecisionMakingRound,
            Event.MECH: FinishedForMechResponseRound,
        },
        CallCheckpointRound: {
            Event.DONE: FinishedToResetRound,
            Event.SETTLE: FinishedToSettlementRound,
            Event.ROUND_TIMEOUT: CallCheckpointRound,
            Event.NO_MAJORITY: CallCheckpointRound,
        },
        PostMechResponseRound: {
            Event.DONE: EngageTwitterRound,
            Event.NO_MAJORITY: PostMechResponseRound,
            Event.ROUND_TIMEOUT: PostMechResponseRound,
        },
        TransactionLoopCheckRound: {
            Event.DONE: FinishedToResetRound,
            Event.RETRY: FinishedToSettlementRound,
            Event.NO_MAJORITY: TransactionLoopCheckRound,
            Event.ROUND_TIMEOUT: TransactionLoopCheckRound,
        },
        FailedMechRequestRound: {
            Event.DONE: EngageTwitterRound,
            Event.NO_MAJORITY: EngageTwitterRound,
            Event.ROUND_TIMEOUT: EngageTwitterRound,
            Event.ERROR: EngageTwitterRound,
        },
        FailedMechResponseRound: {
            Event.DONE: EngageTwitterRound,
            Event.NO_MAJORITY: EngageTwitterRound,
            Event.ROUND_TIMEOUT: EngageTwitterRound,
            Event.ERROR: EngageTwitterRound,
        },
        FinishedToResetRound: {},
        FinishedToSettlementRound: {},
        FinishedForMechRequestRound: {},
        FinishedForMechResponseRound: {},
    }
    final_states: Set[AppState] = {
        FinishedToResetRound,
        FinishedToSettlementRound,
        FinishedForMechRequestRound,
        FinishedForMechResponseRound,
    }
    event_to_timeout: EventToTimeout = {Event.ROUND_TIMEOUT: 30}
    cross_period_persisted_keys: FrozenSet[str] = frozenset(["persona"])
    db_pre_conditions: Dict[AppState, Set[str]] = {
        LoadDatabaseRound: set(),
        PullMemesRound: set(),
        ActionPreparationRound: set(),
        PostTxDecisionMakingRound: set(),
        TransactionLoopCheckRound: set(),
        PostMechResponseRound: set(),
        FailedMechRequestRound: set(),
        FailedMechResponseRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedToResetRound: set(),
        FinishedForMechRequestRound: set(),
        FinishedForMechResponseRound: set(),
        FinishedToSettlementRound: {"most_voted_tx_hash"},
    }
