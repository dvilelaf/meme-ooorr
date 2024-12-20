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
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, cast

from packages.dvilela.skills.memeooorr_abci.payloads import (
    ActionDecisionPayload,
    ActionPreparationPayload,
    ActionTweetPayload,
    AnalizeFeedbackPayload,
    CheckFundsPayload,
    CollectFeedbackPayload,
    DeploymentPayload,
    EngagePayload,
    LoadDatabasePayload,
    PostTweetPayload,
    PullMemesPayload,
    TransactionMultiplexerPayload,
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
    def pending_tweet(self) -> Optional[List]:
        """Get the pending tweet."""
        pending_tweet_str = self.db.get("pending_tweet", None)
        return json.loads(pending_tweet_str) if pending_tweet_str else []

    @property
    def latest_tweet(self) -> Dict:
        """Get the latest_tweet."""
        return cast(dict, json.loads(cast(str, self.db.get("latest_tweet", "{}"))))

    @property
    def token_data(self) -> Dict:
        """Get the token data."""
        return cast(dict, json.loads(cast(str, self.db.get_strict("token_data"))))

    @property
    def feedback(self) -> Optional[List]:
        """Get the feedback."""
        feedback = self.db.get("feedback", None)
        return json.loads(feedback) if feedback else None

    @property
    def most_voted_tx_hash(self) -> Optional[str]:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def tx_flag(self) -> Optional[str]:
        """Get the tx_flag."""
        return cast(str, self.db.get("tx_flag", None))

    @property
    def final_tx_hash(self) -> str:
        """Get the verified tx hash."""
        return cast(str, self.db.get_strict("final_tx_hash"))

    @property
    def participants_to_memes(self) -> DeserializedCollection:
        """Get the participants_to_memes."""
        return self._get_deserialized("participants_to_memes")

    @property
    def meme_coins(self) -> List[Dict]:
        """Get the meme_coins."""
        return cast(list, json.loads(cast(str, self.db.get("meme_coins", "[]"))))

    @property
    def token_action(self) -> Dict:
        """Get the token action."""
        return cast(dict, json.loads(cast(str, self.db.get("token_action", "{}"))))

    @property
    def feedback_period_max_hours_delta(self) -> int:
        """Get the feedback_period_max_hours_delta."""
        return cast(int, self.db.get("feedback_period_max_hours_delta", 0))


class LoadDatabaseRound(CollectSameUntilThresholdRound):
    """LoadDatabaseRound"""

    payload_class = LoadDatabasePayload
    synchronized_data_class = SynchronizedData
    collection_key = get_name(SynchronizedData.participants_to_db)
    selection_key = (
        get_name(SynchronizedData.persona),
        get_name(SynchronizedData.latest_tweet),
    )

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
                    get_name(SynchronizedData.latest_tweet): payload["latest_tweet"],
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    required_class_attributes = ()


class PostTweetRound(
    CollectSameUntilThresholdRound
):  # pylint: disable=too-many-return-statements
    """PostTweetRound"""

    payload_class = PostTweetPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            payload = PostTweetPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )
            latest_tweet_str = payload.latest_tweet
            if latest_tweet_str is None:
                return self.synchronized_data, Event.ERROR
            latest_tweet = json.loads(latest_tweet_str)

            # API errors
            if latest_tweet is None:
                return self.synchronized_data, Event.ERROR

            feedback = cast(SynchronizedData, self.synchronized_data).feedback

            # Wait
            if latest_tweet.get("wait", False):
                return self.synchronized_data, Event.WAIT

            # Collect feedback
            if latest_tweet == {} and not feedback:
                return self.synchronized_data, Event.DONE

            self.context.logger.info(
                f"recieved feedback_period_max_hours_delta: {payload.feedback_period_max_hours_delta}"
            )

            # Remove posted tweets from pending and into latest, then reset
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.pending_tweet): "[]",
                    get_name(SynchronizedData.latest_tweet): json.dumps(
                        latest_tweet, sort_keys=True
                    ),
                    get_name(
                        SynchronizedData.feedback_period_max_hours_delta
                    ): payload.feedback_period_max_hours_delta,
                },
            )
            return synchronized_data, Event.WAIT

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class CollectFeedbackRound(CollectSameUntilThresholdRound):
    """CollectFeedbackRound"""

    payload_class = CollectFeedbackPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            feedback = json.loads(self.most_voted_payload)

            # API error
            if feedback is None:
                return self.synchronized_data, Event.ERROR

            # Not enough replies
            if len(feedback) < self.context.params.min_feedback_replies:
                return self.synchronized_data, Event.NOT_ENOUGH_FEEDBACK

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


class AnalizeFeedbackRound(CollectSameUntilThresholdRound):
    """AnalizeFeedbackRound"""

    payload_class = AnalizeFeedbackPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

            # Errors
            if not self.most_voted_payload:
                return self.synchronized_data, Event.ERROR

            analysis = json.loads(self.most_voted_payload)

            if not analysis:
                return self.synchronized_data, Event.ERROR

            # Update persona
            if not analysis.get("deploy", None):
                self.context.logger.info(f"Updated persona: {analysis['persona']}")
                synchronized_data = self.synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{get_name(SynchronizedData.persona): analysis["persona"]},
                )
                return synchronized_data, Event.REFINE

            # Deploy
            token_data = {
                "token_name": analysis["token_name"],
                "token_ticker": analysis["token_ticker"],
                "token_supply": analysis["token_supply"],
                "amount": analysis["amount"],
                "tweet": analysis["tweet"],
            }
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.token_data): json.dumps(
                        token_data, sort_keys=True
                    ),
                    get_name(SynchronizedData.pending_tweet): json.dumps(
                        [analysis["tweet"]]
                    ),
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class EventRoundBase(CollectSameUntilThresholdRound):
    """EventRoundBase"""

    synchronized_data_class = SynchronizedData
    payload_class = BaseTxPayload  # will be overwritten
    required_class_attributes = ()

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


class CheckFundsRound(EventRoundBase):
    """CheckFundsRound"""

    payload_class = CheckFundsPayload  # type: ignore
    required_class_attributes = ()
    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.NO_FUNDS


class DeploymentRound(CollectSameUntilThresholdRound):
    """DeploymentRound"""

    payload_class = DeploymentPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = DeploymentPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            # The token has been deployed
            if payload.token_nonce:
                token_data = cast(SynchronizedData, self.synchronized_data).token_data
                token_data["token_nonce"] = payload.token_nonce

                synchronized_data = self.synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(SynchronizedData.token_data): json.dumps(
                            token_data, sort_keys=True
                        ),
                        get_name(SynchronizedData.tx_flag): None,
                        get_name(SynchronizedData.pending_tweet): json.dumps(
                            token_data["tweet"]
                        ),
                    },
                )
                return synchronized_data, Event.DONE

            # Error preparing the deployment transaction
            if payload.tx_flag is None:
                return self.synchronized_data, Event.ERROR

            # The deployment tx has been prepared
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                    get_name(SynchronizedData.tx_flag): payload.tx_flag,
                },
            )
            return synchronized_data, Event.SETTLE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class PostAnnouncementRound(CollectSameUntilThresholdRound):
    """PostAnnouncementRound"""

    payload_class = PostTweetPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.WAIT

        if self.threshold_reached:
            latest_tweet = json.loads(self.most_voted_payload)

            # API errors
            if latest_tweet is None:
                return self.synchronized_data, Event.ERROR

            # Reset everything
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.pending_tweet): "[]",
                    get_name(SynchronizedData.latest_tweet): "{}",
                    get_name(SynchronizedData.token_data): "{}",
                    get_name(SynchronizedData.persona): self.context.params.persona,
                    get_name(SynchronizedData.feedback): None,
                    get_name(SynchronizedData.tx_flag): None,
                    get_name(SynchronizedData.most_voted_tx_hash): None,
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
    required_class_attributes = ()

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


class ActionDecisionRound(CollectSameUntilThresholdRound):
    """ActionDecisionRound"""

    payload_class = ActionDecisionPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

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
                    "token_nonce": payload.token_nonce,
                    "token_address": payload.token_address,
                    "action": payload.action,
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
    required_class_attributes = ()

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

            tweet = cast(SynchronizedData, self.synchronized_data).token_action["tweet"]

            # The tx has been prepared
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                    get_name(SynchronizedData.tx_flag): payload.tx_flag,
                    get_name(SynchronizedData.pending_tweet): json.dumps(
                        {"text": tweet}, sort_keys=True
                    ),  # schedule tweet
                },
            )
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
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.ERROR


class TransactionMultiplexerRound(EventRoundBase):
    """ActionTweetRound"""

    payload_class = TransactionMultiplexerPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.TO_DEPLOY, Event.TO_ACTION_TWEET


class EngageRound(EventRoundBase):
    """EngageRound"""

    payload_class = EngagePayload  # type: ignore
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.ERROR, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class FinishedToResetRound(DegenerateRound):
    """FinishedToResetRound"""


class FinishedToSettlementRound(DegenerateRound):
    """FinishedToSettlementRound"""


class MemeooorrAbciApp(AbciApp[Event]):
    """MemeooorrAbciApp"""

    initial_round_cls: AppState = LoadDatabaseRound
    initial_states: Set[AppState] = {
        LoadDatabaseRound,
        PostTweetRound,
        TransactionMultiplexerRound,
    }
    transition_function: AbciAppTransitionFunction = {
        LoadDatabaseRound: {
            Event.DONE: PullMemesRound,
            Event.NO_MAJORITY: LoadDatabaseRound,
            Event.ROUND_TIMEOUT: LoadDatabaseRound,
        },
        PullMemesRound: {
            Event.DONE: PostTweetRound,
            Event.NO_MAJORITY: PullMemesRound,
            Event.ROUND_TIMEOUT: PullMemesRound,
        },
        PostTweetRound: {
            Event.DONE: CollectFeedbackRound,
            Event.ERROR: PostTweetRound,
            Event.WAIT: ActionDecisionRound,
            Event.NO_MAJORITY: PostTweetRound,
            Event.ROUND_TIMEOUT: PostTweetRound,
        },
        CollectFeedbackRound: {
            Event.DONE: AnalizeFeedbackRound,
            Event.ERROR: CollectFeedbackRound,
            Event.NOT_ENOUGH_FEEDBACK: ActionDecisionRound,
            Event.NO_MAJORITY: CollectFeedbackRound,
            Event.ROUND_TIMEOUT: CollectFeedbackRound,
        },
        AnalizeFeedbackRound: {
            Event.DONE: DeploymentRound,
            Event.REFINE: ActionDecisionRound,
            Event.ERROR: AnalizeFeedbackRound,
            Event.NO_MAJORITY: AnalizeFeedbackRound,
            Event.ROUND_TIMEOUT: AnalizeFeedbackRound,
        },
        DeploymentRound: {
            Event.DONE: PostAnnouncementRound,
            Event.SETTLE: CheckFundsRound,
            Event.ERROR: DeploymentRound,
            Event.NO_MAJORITY: DeploymentRound,
            Event.ROUND_TIMEOUT: DeploymentRound,
        },
        PostAnnouncementRound: {
            Event.DONE: ActionDecisionRound,
            Event.ERROR: PostAnnouncementRound,
            Event.NO_MAJORITY: PostAnnouncementRound,
            Event.ROUND_TIMEOUT: PostAnnouncementRound,
            Event.WAIT: PostAnnouncementRound,  # This will never happen. Just for static analysys.
        },
        ActionDecisionRound: {
            Event.DONE: ActionPreparationRound,
            Event.WAIT: EngageRound,
            Event.NO_MAJORITY: ActionDecisionRound,
            Event.ROUND_TIMEOUT: ActionDecisionRound,
        },
        ActionPreparationRound: {
            Event.DONE: ActionTweetRound,  # This will never happen
            Event.ERROR: EngageRound,
            Event.SETTLE: CheckFundsRound,
            Event.NO_MAJORITY: ActionPreparationRound,
            Event.ROUND_TIMEOUT: ActionPreparationRound,
        },
        ActionTweetRound: {
            Event.DONE: EngageRound,
            Event.ERROR: ActionTweetRound,
            Event.NO_MAJORITY: ActionTweetRound,
            Event.ROUND_TIMEOUT: ActionTweetRound,
        },
        EngageRound: {
            Event.DONE: FinishedToResetRound,
            Event.ERROR: EngageRound,
            Event.NO_MAJORITY: EngageRound,
            Event.ROUND_TIMEOUT: EngageRound,
        },
        CheckFundsRound: {
            Event.DONE: FinishedToSettlementRound,
            Event.NO_FUNDS: CheckFundsRound,
            Event.NO_MAJORITY: CheckFundsRound,
            Event.ROUND_TIMEOUT: CheckFundsRound,
        },
        TransactionMultiplexerRound: {
            Event.DONE: TransactionMultiplexerRound,
            Event.TO_DEPLOY: DeploymentRound,
            Event.TO_ACTION_TWEET: ActionTweetRound,
            Event.NO_MAJORITY: TransactionMultiplexerRound,
            Event.ROUND_TIMEOUT: TransactionMultiplexerRound,
        },
        FinishedToResetRound: {},
        FinishedToSettlementRound: {},
    }
    final_states: Set[AppState] = {FinishedToResetRound, FinishedToSettlementRound}
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset(
        ["persona", "latest_tweet", "feedback", "feedback_period_max_hours_delta"]
    )
    db_pre_conditions: Dict[AppState, Set[str]] = {
        LoadDatabaseRound: set(),
        PostTweetRound: set(),
        TransactionMultiplexerRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedToResetRound: set(),
        FinishedToSettlementRound: {"most_voted_tx_hash"},
    }
