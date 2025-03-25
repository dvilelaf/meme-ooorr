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
import random
import secrets
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, Type, Union
from uuid import uuid4

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import (
    ALTERNATIVE_MODEL_TWITTER_PROMPT,
    MECH_RESPONSE_SUBPROMPT,
    TWITTER_DECISION_PROMPT,
    build_decision_schema,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    ActionTweetPayload,
    ActionTweetRound,
    CollectFeedbackPayload,
    CollectFeedbackRound,
    EngageTwitterPayload,
    EngageTwitterRound,
    Event,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.mech_interact_abci.states.base import MechMetadata


MAX_TWEET_CHARS = 280
JSON_RESPONSE_REGEXES = [r"json.?({.*})", r"json({.*})", r"\`\`\`json(.*)\`\`\`"]
MAX_TWEET_PREPARATIONS_RETRIES = 3


def is_tweet_valid(tweet: str) -> bool:
    """Checks a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"] <= MAX_TWEET_CHARS


class BaseTweetBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
    """BaseTweetBehaviour"""

    matching_round: Type[AbstractRound] = None  # type: ignore

    def store_tweet(
        self, tweet: Union[dict, List[dict]]
    ) -> Generator[None, None, bool]:
        """Store tweet"""
        tweets = yield from self.get_tweets_from_db()
        if isinstance(tweet, list):
            tweets.extend(tweet)
        else:
            tweets.append(tweet)
        yield from self._write_kv({"tweets": json.dumps(tweets)})
        return True

    def post_tweet(
        self, tweet: List[str], store: bool = True
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""
        self.context.logger.info(f"Posting tweet: {tweet}")

        # Post the tweet
        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[{"text": t} for t in tweet],
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting to Twitter.")
            return None

        latest_tweet = {
            "tweet_id": tweet_ids[0],
            "text": tweet,
            "timestamp": self.get_sync_timestamp(),
        }

        # Write latest tweet to the database
        if store:
            yield from self.store_tweet(latest_tweet)
            self.context.logger.info("Wrote latest tweet to db")

        return latest_tweet

    def respond_tweet(
        self,
        tweet_id: str,
        text: str,
        quote: bool = False,
        user_name: Optional[str] = None,
    ) -> Generator[None, None, bool]:
        """Like a tweet"""

        self.context.logger.info(f"Liking tweet with ID: {tweet_id}")
        tweet = {"text": text}
        if quote:
            tweet["attachment_url"] = f"https://x.com/{user_name}/status/{tweet_id}"
        else:
            tweet["reply_to"] = tweet_id
        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[tweet],
        )
        return tweet_ids is not None and tweet_ids

    def like_tweet(self, tweet_id: str) -> Generator[None, None, bool]:
        """Like a tweet"""
        self.context.logger.info(f"Liking tweet with ID: {tweet_id}")

        try:
            response = yield from self._call_twikit(
                method="like_tweet", tweet_id=tweet_id
            )
            if response is None or not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error liking tweet with ID {tweet_id}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Exception liking tweet with ID {tweet_id}: {e}")
            return False

    def retweet(self, tweet_id: str) -> Generator[None, None, bool]:
        """Retweet"""
        self.context.logger.info(f"Retweeting tweet with ID: {tweet_id}")

        try:
            response = yield from self._call_twikit(method="retweet", tweet_id=tweet_id)
            if response is None or not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error retweeting tweet with ID {tweet_id}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception retweeting tweet with ID {tweet_id}: {e}"
            )
            return False

    def follow_user(self, user_id: str) -> Generator[None, None, bool]:
        """Follow user"""
        self.context.logger.info(f"Following user with ID: {user_id}")
        try:
            response = yield from self._call_twikit(
                method="follow_user", user_id=user_id
            )
            if response is None or not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error Following user with ID {user_id}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception following user with ID {user_id}: {e}"
            )
            return False

    def get_previous_tweets(
        self, limit: int = 5
    ) -> Generator[None, None, Optional[List[Dict]]]:
        """Get the latest tweets

        Args:
            limit (int, optional): Maximum number of tweets to return. Defaults to 5.

        Returns:
            Generator yielding Optional[List[Dict]]: List of tweets or None
        """
        # Try to get tweets from MirrorDB
        self.context.logger.info("Trying to get latest tweets from MirrorDB for agent")
        mirror_db_config_data = yield from self._mirror_db_registration_check()

        if mirror_db_config_data:  # pylint: disable=too-many-nested-blocks
            self.context.logger.info(f"Mirror Db config = {mirror_db_config_data}")

            agent_id = mirror_db_config_data.get("agent_id")  # type: ignore

            if agent_id:
                try:
                    mirror_db_response = yield from self._call_mirrordb(
                        method="get_latest_tweets",
                        agent_id=agent_id,
                    )
                    self.context.logger.info(f"MirrorDB response: {mirror_db_response}")

                    if (
                        "detail" in mirror_db_response
                        and mirror_db_response["detail"]
                        == "No tweets found for the associated Twitter accounts"
                    ):
                        mirror_db_response = None

                    if mirror_db_response:
                        for tweet in mirror_db_response:
                            created_at = tweet.get("created_at")
                            if created_at:
                                tweet["timestamp"] = datetime.fromisoformat(
                                    created_at
                                ).timestamp()
                        return mirror_db_response[:limit]
                except Exception as e:  # pylint: disable=broad-except
                    self.context.logger.error(
                        f"Error getting tweets from MirrorDB: {e}"
                    )

        # Fallback to get_tweets_from_db if MirrorDB fails or returns no results
        self.context.logger.info(
            f"Couldn't fetch tweets from MirrorDB Getting latest {limit} tweets from local DB as fallback"
        )
        tweets = yield from self.get_tweets_from_db()

        if tweets:
            for tweet in tweets:
                created_at = tweet.get("created_at")
                if created_at:
                    tweet["timestamp"] = datetime.fromisoformat(created_at).timestamp()
            return tweets[:limit]

        return None


class CollectFeedbackBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """CollectFeedbackBehaviour"""

    matching_round: Type[AbstractRound] = CollectFeedbackRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            feedback = yield from self.get_feedback()

            payload = CollectFeedbackPayload(
                sender=self.context.agent_address,
                feedback=json.dumps(feedback, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_feedback(self) -> Generator[None, None, Optional[List]]:
        """Get the responses"""

        # Search new replies
        tweets = yield from self.get_tweets_from_db()
        if not tweets:
            self.context.logger.error("No tweets yet")
            return []
        latest_tweet = tweets[-1]
        query = f"conversation_id:{latest_tweet['tweet_id']}"
        feedback = yield from self._call_twikit(method="search", query=query, count=100)

        if feedback is None:
            self.context.logger.error(
                "Could not retrieve any replies due to an API error"
            )
            return None

        if not feedback:
            self.context.logger.error("No tweets match the query")
            return []

        self.context.logger.info(f"Retrieved {len(feedback)} replies")

        # Sort tweets by popularity using a weighted sum (views + quotes + retweets)
        feedback = list(
            sorted(
                feedback,
                key=lambda t: int(t.get("view_count", 0) or 0)
                + 3 * int(t.get("retweet_count", 0) or 0)
                + 5 * int(t.get("quote_count", 0) or 0),
                reverse=True,
            )
        )

        # Keep only the most relevant tweet to avoid sending too many tokens to the LLM
        feedback = feedback[:10]

        return feedback


class EngageTwitterBehaviour(BaseTweetBehaviour):  # pylint: disable=too-many-ancestors
    """EngageTwitterBehaviour"""

    matching_round: Type[AbstractRound] = EngageTwitterRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event, new_mech_requests = yield from self.get_event()

            if new_mech_requests:
                mech_requests = json.dumps(new_mech_requests, sort_keys=True)
                self.context.logger.info(f"Mech Requests JSON: {mech_requests}")

            # Determine mech_request value based on event type
            mech_request = (
                json.dumps(new_mech_requests, sort_keys=True)
                if event == Event.MECH.value
                else None
            )

            # Create payload with appropriate mech_request value
            payload = EngageTwitterPayload(
                sender=self.context.agent_address,
                event=event,
                mech_request=mech_request,
                tx_submitter=self.matching_round.auto_round_id(),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> Generator[None, None, Tuple[str, List]]:
        """
        Get the next event for Twitter engagement.

        Returns:
            Tuple[str, List]: Event type and any new mech requests.
        """
        new_mech_requests: List[Dict[str, Any]] = []

        # Skip engagement if configured
        if self.params.skip_engagement:
            self.context.logger.info("Skipping engagement on Twitter")
            return Event.DONE.value, new_mech_requests

        # Handle differently based on mech_for_twitter state
        if self.synchronized_data.mech_for_twitter:
            (
                pending_tweets,
                interacted_tweet_ids,
            ) = yield from self._handle_mech_for_twitter()
        else:
            (
                pending_tweets,
                interacted_tweet_ids,
            ) = yield from self._handle_regular_engagement()

        # Process interactions
        (
            event,
            new_interacted_tweet_ids,
            new_mech_requests,
        ) = yield from self.interact_twitter(pending_tweets)

        # Handle results based on event type
        if event == Event.MECH.value:
            return event, new_mech_requests

        if event == Event.DONE.value:
            yield from self._update_interacted_tweets(
                interacted_tweet_ids, new_interacted_tweet_ids
            )

        return event, new_mech_requests

    def _handle_mech_for_twitter(self) -> Generator[None, None, Tuple[dict, list]]:
        """
        Handle Twitter engagement when mech_for_twitter is True.

        Returns:
            Tuple[dict, list]: Pending tweets and interacted tweet IDs.
        """
        self.context.logger.info(
            "Mech for twitter detected, using Mech response for decision"
        )

        # Fetch pending tweets from db
        pending_tweets_data = yield from self._read_kv(
            keys=("pending_tweets_for_tw_mech",)
        )
        pending_tweets = {}
        if pending_tweets_data:
            pending_tweets = json.loads(
                pending_tweets_data["pending_tweets_for_tw_mech"]
            )
        else:
            self.context.logger.error("No pending tweets found in KV store")

        # Fetch previously interacted tweets
        interacted_ids_data = yield from self._read_kv(
            keys=("interacted_tweet_ids_for_tw_mech",)
        )
        interacted_tweet_ids = []
        if interacted_ids_data:
            interacted_tweet_ids = json.loads(
                interacted_ids_data["interacted_tweet_ids_for_tw_mech"]
            )
        else:
            self.context.logger.error("No interacted tweets found in KV store")

        return pending_tweets, interacted_tweet_ids

    def _handle_regular_engagement(self) -> Generator[None, None, Tuple[dict, list]]:
        """
        Handle Twitter engagement when mech_for_twitter is False.

        Returns:
            Tuple[dict, list]: Pending tweets and interacted tweet IDs.
        """
        # Get other memeooorr handles
        agent_handles = yield from self.get_agent_handles()
        self.context.logger.info(f"Not suspended users: {agent_handles}")

        if not agent_handles:
            self.context.logger.error("No valid Twitter handles")
            return {}, []

        # Load previously interacted tweets
        interacted_tweet_ids = yield from self._get_interacted_tweet_ids()

        # Get latest tweets from each agent - CHANGE HERE: convert list to set
        pending_tweets = yield from self._collect_pending_tweets(
            agent_handles, set(interacted_tweet_ids)
        )

        # Store data for mech processing
        yield from self._store_engagement_data(interacted_tweet_ids, pending_tweets)

        return pending_tweets, interacted_tweet_ids

    def _get_interacted_tweet_ids(self) -> Generator[None, None, list]:
        """Get previously interacted tweet IDs from the database."""
        db_data = yield from self._read_kv(keys=("interacted_tweet_ids",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            return []

        return json.loads(db_data["interacted_tweet_ids"] or "[]")

    def _collect_pending_tweets(
        self, agent_handles: list[str], interacted_tweet_ids: set[int]
    ) -> Generator[None, None, dict]:
        """Collect pending tweets from agent handles that haven't been interacted with."""
        pending_tweets = {}

        for agent_handle in agent_handles:
            latest_tweets = yield from self._call_twikit(
                method="get_user_tweets",
                twitter_handle=agent_handle,
            )

            if not latest_tweets:
                self.context.logger.info(f"Couldn't get any tweets from {agent_handle}")
                continue

            tweet_id = latest_tweets[0]["id"]

            # Skip previously interacted tweets
            if int(tweet_id) in interacted_tweet_ids:
                self.context.logger.info(
                    f"Tweet {tweet_id} was already interacted with"
                )
                continue

            pending_tweets[tweet_id] = {
                "text": latest_tweets[0]["text"],
                "user_name": latest_tweets[0]["user_name"],
                "user_id": latest_tweets[0]["user_id"],
            }

        return pending_tweets

    def _store_engagement_data(
        self, interacted_tweet_ids: list[int], pending_tweets: dict[str, dict[str, str]]
    ) -> Generator[None, None, None]:
        """Store engagement data in the database for mech processing."""
        yield from self._write_kv(
            {
                "interacted_tweet_ids_for_tw_mech": json.dumps(
                    interacted_tweet_ids, sort_keys=True
                )
            }
        )
        self.context.logger.info("Wrote interacted tweet ids to db")

        yield from self._write_kv(
            {"pending_tweets_for_tw_mech": json.dumps(pending_tweets, sort_keys=True)}
        )
        self.context.logger.info("Wrote pending tweets to db")

    def _update_interacted_tweets(
        self, interacted_tweet_ids: list[int], new_interacted_tweet_ids: list[int]
    ) -> Generator[None, None, None]:
        """Update the list of interacted tweets in the database."""
        interacted_tweet_ids.extend(new_interacted_tweet_ids)
        yield from self._write_kv(
            {"interacted_tweet_ids": json.dumps(interacted_tweet_ids, sort_keys=True)}
        )
        self.context.logger.info("Updated interacted tweets in db")

    def interact_twitter(  # pylint: disable=too-many-locals
        self, pending_tweets: dict
    ) -> Generator[None, None, Tuple[str, List, List]]:
        """Decide whether to interact with tweets based on the persona's preferences."""
        new_interacted_tweet_ids: List[int] = []
        persona = yield from self.get_persona()

        # Track retry attempts
        max_retries = 3
        retry_count = 0
        valid_response = False
        json_response = None

        # Try to get the previously stored prompt first
        stored_prompt_data = yield from self._read_kv(keys=("last_prompt",))
        stored_prompt = (
            stored_prompt_data.get("last_prompt") if stored_prompt_data else None
        )

        # Check if we should use a stored prompt or generate a new one
        if stored_prompt and retry_count > 0:
            self.context.logger.info("Using previously stored prompt")
            prompt = stored_prompt
            # We still need previous_tweets for potential media handling
            previous_tweets = yield from self._get_stored_kv_data(
                "previous_tweets_for_tw_mech", {}
            )
        else:
            # Generate a new prompt and store it
            prompt, previous_tweets = yield from self._prepare_prompt_data(
                pending_tweets, persona
            )

        while not valid_response and retry_count < max_retries:
            # Get LLM decision about how to interact with tweets
            llm_response = yield from self._get_llm_decision(prompt)
            if llm_response is None:
                self.context.logger.error("Error getting a response from the LLM.")
                return Event.ERROR.value, new_interacted_tweet_ids, []

            # Parse LLM response
            try:
                json_response = json.loads(llm_response)
                self.context.logger.info(
                    f"LLM response after JSON parsing: {json_response}"
                )

                # Validate response format
                if json_response is not None and self._validate_llm_response(
                    json_response
                ):
                    valid_response = True
                else:
                    retry_count += 1
                    self.context.logger.warning(
                        f"Invalid response format from LLM (attempt {retry_count}/{max_retries})"
                    )
                    # If we need to retry, use the stored prompt
                    if retry_count > 0 and stored_prompt:
                        prompt = stored_prompt

            except json.JSONDecodeError as e:
                self.context.logger.error(f"Error decoding LLM response: {e}")
                self.context.logger.error(f"LLM Response: {llm_response}")
                retry_count += 1
                # If we need to retry, use the stored prompt
                if retry_count > 0 and stored_prompt:
                    prompt = stored_prompt
                continue

        # If we couldn't get a valid response after max retries
        if not valid_response or json_response is None:
            self.context.logger.error(
                f"Failed to get valid response after {max_retries} attempts"
            )
            return Event.ERROR.value, new_interacted_tweet_ids, []

        # At this point, json_response must be valid and not None
        assert json_response is not None, "json_response should not be None here"

        # Handle tool action if present
        if "tool_action" in json_response and json_response["tool_action"] is not None:
            # The validation should have already caught this, but double-check
            if self.synchronized_data.mech_for_twitter:
                self.context.logger.error(
                    "LLM provided a tool action when mech_for_twitter is True. "
                    "This should not happen after our validation."
                )
                return Event.ERROR.value, new_interacted_tweet_ids, []

            # Handle the tool action normally
            event, new_interacted_tweet_id, mech_request = self._handle_tool_action(
                json_response
            )
            return event, new_interacted_tweet_id, mech_request

        # Handle tweet actions if present
        if "tweet_action" in json_response:
            (
                event,
                new_interacted_tweet_id,
                mech_request,
            ) = yield from self._handle_tweet_actions(
                json_response,
                pending_tweets,
                previous_tweets,
                persona,
                new_interacted_tweet_ids,
            )
            return event, new_interacted_tweet_id, mech_request

        # This point should not be reached due to our validation
        self.context.logger.error("Invalid response from the LLM.")
        return Event.ERROR.value, new_interacted_tweet_ids, []

    def _prepare_prompt_data(
        self, pending_tweets: dict, persona: str
    ) -> Generator[None, None, Tuple[str, dict]]:
        """Prepare the prompt data for LLM decision making."""
        previous_tweets = {}

        if self.synchronized_data.mech_for_twitter:
            # Read saved data for mech response
            previous_tweets = yield from self._get_stored_kv_data(
                "previous_tweets_for_tw_mech", {}
            )
            other_tweets = yield from self._get_stored_kv_data(
                "other_tweets_for_tw_mech", {}
            )

            # Prepare prompt with mech response
            mech_responses = self.synchronized_data.mech_responses
            if not mech_responses:
                self.context.logger.error("No mech responses found")

            subprompt_with_mech_response = MECH_RESPONSE_SUBPROMPT.format(
                mech_response=mech_responses,
            )

            prompt = TWITTER_DECISION_PROMPT.format(
                persona=persona,
                previous_tweets=previous_tweets,
                other_tweets=other_tweets,
                mech_response=subprompt_with_mech_response,
                tools=self.generate_mech_tool_info(),
                time=self.get_sync_time_str(),
            )

            # Clear stored data
            self.context.logger.info(
                "Clearing all the pending tweets, interacted tweet id, previous tweets and other tweets from db"
            )
            yield from self._write_kv({"previous_tweets_for_tw_mech": ""})
            yield from self._write_kv({"other_tweets_for_tw_mech": ""})
            yield from self._write_kv({"interacted_tweet_ids_for_tw_mech": ""})
            yield from self._write_kv({"pending_tweets_for_tw_mech": ""})
        else:
            # Standard approach
            self.context.logger.info(
                "No Mech for twitter detected, using prompt for decision and introducing tools to LLM"
            )

            # Prepare other tweets data
            other_tweets = "\n\n".join(
                [
                    f"tweet_id: {t_id}\ntweet_text: {t_data['text']}\nuser_id: {t_data['user_id']}"
                    for t_id, t_data in dict(
                        random.sample(list(pending_tweets.items()), len(pending_tweets))
                    ).items()
                ]
            )

            # Get previous tweets
            tweets = yield from self.get_previous_tweets()
            tweets = tweets[-5:] if tweets else None

            if tweets:
                random.shuffle(tweets)
                previous_tweets_str = "\n\n".join(
                    [
                        f"tweet_id: {tweet['tweet_id']}\ntweet_text: {tweet['text']}\ntime: {datetime.fromtimestamp(tweet['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}"
                        for tweet in tweets
                    ]
                )
            else:
                previous_tweets_str = "No previous tweets"

            previous_tweets = tweets if isinstance(tweets, dict) else {}

            prompt = TWITTER_DECISION_PROMPT.format(
                persona=persona,
                previous_tweets=previous_tweets_str,
                other_tweets=other_tweets,
                mech_response="",
                tools=self.generate_mech_tool_info(),
                time=self.get_sync_time_str(),
            )

            # Save data for future mech responses
            self.context.logger.info("Saving previous tweets and other tweets to db")
            yield from self._write_kv(
                {"previous_tweets_for_tw_mech": json.dumps(tweets)}
            )
            self.context.logger.info("Wrote previous tweets to db")
            yield from self._write_kv(
                {"other_tweets_for_tw_mech": json.dumps(pending_tweets)}
            )
            self.context.logger.info("Wrote other tweets to db")

        # saving the prompt to the kv store for retrying if llm response is invalid
        yield from self._write_kv({"last_prompt": prompt})

        return prompt, previous_tweets

    def _get_stored_kv_data(
        self, key: str, default_value: Any
    ) -> Generator[None, None, Any]:
        """Helper to get and parse stored KV data."""
        data = yield from self._read_kv(keys=(key,))
        if not data:
            self.context.logger.error(f"No {key} found in KV store")
            return default_value
        return json.loads(data[key])

    def _get_llm_decision(self, prompt: str) -> Generator[None, None, Optional[str]]:
        """Get decision from LLM."""
        self.context.logger.info(f"Prompting the LLM for a decision: {prompt}")
        llm_response = yield from self._call_genai(
            prompt=prompt,
            schema=build_decision_schema(),
        )
        self.context.logger.info(f"LLM response for twitter decision: {llm_response}")
        return llm_response

    def _validate_llm_response(  # pylint: disable=too-many-return-statements
        self, json_response: dict
    ) -> bool:
        """Validate that the LLM response has either valid tweet_action or valid tool_action"""
        # If mech_for_twitter is True, only tweet_action with 'tweet_with_media' is allowed
        if self.synchronized_data.mech_for_twitter:
            if (
                "tweet_action" in json_response
                and json_response["tweet_action"] is not None
            ):
                # Check both possible field names: action_type (schema format) and action (actual response format)
                action = json_response["tweet_action"].get(
                    "action_type", json_response["tweet_action"].get("action")
                )
                if action == "tweet_with_media":
                    # Ensure we have the required text field for media tweet
                    if "text" in json_response["tweet_action"]:
                        return True

                    self.context.logger.error(
                        "Invalid tweet_with_media action: missing 'text' field"
                    )
                    return False

                self.context.logger.error(
                    f"Invalid action type: {action}. Only 'tweet_with_media' is allowed when mech_for_twitter is True"
                )
                return False

            self.context.logger.error(
                "Invalid LLM response: expected tweet_action with type 'tweet_with_media' when mech_for_twitter is True"
            )
            return False

        # Normal validation when mech_for_twitter is False
        if (
            "tweet_action" in json_response
            and json_response["tweet_action"] is not None
        ):
            # For non-mech context, tweet_with_media should not be allowed
            if isinstance(json_response["tweet_action"], list):
                for action in json_response["tweet_action"]:
                    action_type = action.get("action")
                    if action_type == "tweet_with_media":
                        self.context.logger.error(
                            "Invalid action: 'tweet_with_media' is not allowed when mech_for_twitter is False"
                        )
                        return False
            else:
                action_type = json_response["tweet_action"].get(
                    "action_type", json_response["tweet_action"].get("action")
                )
                if action_type == "tweet_with_media":
                    self.context.logger.error(
                        "Invalid action: 'tweet_with_media' is not allowed when mech_for_twitter is False"
                    )
                    return False
            return True

        if "tool_action" in json_response and json_response["tool_action"] is not None:
            # Ensure tool_action has both required fields
            if (
                "tool_name" not in json_response["tool_action"]
                or "tool_input" not in json_response["tool_action"]
            ):
                self.context.logger.error(
                    f"Invalid tool_action format: missing required fields. Got: {json_response['tool_action']}"
                )
                return False
            return True

        self.context.logger.error(
            "Invalid LLM response: neither tweet_action nor tool_action is valid"
        )
        return False

    def _handle_tool_action(self, json_response: dict) -> Tuple[str, List, List]:
        """Handle tool action from LLM response."""
        self.context.logger.info("Tool action detected")

        # Validate that we have both tool_name and tool_input
        if (
            "tool_action" not in json_response
            or not json_response["tool_action"]
            or "tool_name" not in json_response["tool_action"]
            or "tool_input" not in json_response["tool_action"]
        ):
            self.context.logger.error(
                "Invalid tool action: missing tool_name or tool_input"
            )
            return Event.ERROR.value, [], []

        new_mech_requests = []
        nonce = str(uuid4())
        tool_name = json_response["tool_action"]["tool_name"]
        tool_input = json_response["tool_action"]["tool_input"]

        new_mech_requests.append(
            asdict(
                MechMetadata(
                    nonce=nonce,
                    tool=tool_name,
                    prompt=tool_input,
                )
            )
        )

        return Event.MECH.value, [], new_mech_requests

    def _handle_tweet_actions(  # pylint: disable=too-many-arguments
        self,
        json_response: dict,
        pending_tweets: dict,
        previous_tweets: dict,
        persona: str,
        new_interacted_tweet_ids: List[int],
    ) -> Generator[None, None, Tuple[str, List, List]]:
        """Handle tweet actions from LLM response."""
        self.context.logger.info("Tweet action detected")
        tweet_actions = json_response["tweet_action"]

        # Ensure tweet_actions is a list
        if isinstance(tweet_actions, str):
            tweet_actions = [{"action": tweet_actions}]
        elif not isinstance(tweet_actions, list):
            tweet_actions = [tweet_actions]

        for interaction in tweet_actions:
            # Process each interaction
            yield from self._process_single_interaction(
                interaction,
                pending_tweets,
                previous_tweets,
                persona,
                new_interacted_tweet_ids,
            )

        return Event.DONE.value, new_interacted_tweet_ids, []

    def _process_single_interaction(  # pylint: disable=too-many-arguments
        self,
        interaction: dict,
        pending_tweets: dict,
        previous_tweets: dict,
        persona: str,
        new_interacted_tweet_ids: List[int],
    ) -> Generator[None, None, None]:
        """Process a single tweet interaction."""
        # Ensure interaction is a dictionary
        if not isinstance(interaction, dict):
            self.context.logger.error(f"Invalid interaction format: {interaction}")
            return

        tweet_id = interaction.get("selected_tweet_id", None)
        user_id = interaction.get("user_id", None)
        action = interaction.get("action", None)
        text = interaction.get("text", None)
        media_path = interaction.get("media_path", None)

        # Validate action and parameters
        if not self._validate_interaction(action, tweet_id, user_id, pending_tweets):
            return

        # Add random delay to avoid rate limiting
        delay = secrets.randbelow(5)
        self.context.logger.info(f"Sleeping for {delay} seconds")
        yield from self.sleep(delay)

        # Handle tweet action based on type
        if action == "tweet":
            yield from self._handle_new_tweet(text, previous_tweets, persona)
        elif action == "tweet_with_media":
            # fetching the media path from kv store
            media_path = yield from self._read_kv(keys=("latest_image_path",))
            self.context.logger.info(f"Media path from kv store: {media_path}")
            if not media_path:
                self.context.logger.error(
                    "No media path found in KV store for tweet_with_media action"
                )
                return
            yield from self._handle_tweet_with_media(text, previous_tweets, persona)
        else:
            yield from self._handle_tweet_interaction(
                action,
                tweet_id,
                text,
                user_id,
                pending_tweets,
                new_interacted_tweet_ids,
            )

    def _validate_interaction(
        self, action: str, tweet_id: str, user_id: str, pending_tweets: dict
    ) -> bool:
        """Validate tweet interaction parameters."""
        if action == "none":
            self.context.logger.error("Action is none")
            return False

        # Treat tweet_with_media like tweet - it doesn't need a tweet_id
        if (
            action not in ["tweet", "tweet_with_media"]
            and str(tweet_id) not in pending_tweets.keys()
        ):
            self.context.logger.error(
                f"Action is {action} but tweet_id is not valid [{tweet_id}]"
            )
            return False

        if action == "follow" and (
            not user_id
            or user_id not in [t["user_id"] for t in pending_tweets.values()]
        ):
            self.context.logger.error(
                f"Action is {action} but user_id is not valid [{user_id}]"
            )
            return False

        return True

    def _handle_new_tweet(
        self, text: str, previous_tweets: dict, persona: str
    ) -> Generator[None, None, None]:
        """Handle creating a new tweet."""
        # Optionally, replace the tweet with one generated by the alternative model
        new_text = yield from self.replace_tweet_with_alternative_model(
            ALTERNATIVE_MODEL_TWITTER_PROMPT.format(
                persona=persona,
                previous_tweets=previous_tweets,
            )
        )
        text = new_text or text

        if not is_tweet_valid(text):
            self.context.logger.error("The tweet is too long.")
            return

        yield from self.post_tweet(tweet=[text], store=True)

    def _handle_tweet_interaction(  # pylint: disable=too-many-arguments
        self,
        action: str,
        tweet_id: str,
        text: str,
        user_id: str,
        pending_tweets: dict,
        new_interacted_tweet_ids: List[int],
    ) -> Generator[None, None, None]:
        """Handle interaction with an existing tweet."""
        if text and not is_tweet_valid(text):
            self.context.logger.error("The tweet is too long.")
            return

        self.context.logger.info(f"Trying to {action} tweet {tweet_id}")
        user_name = pending_tweets[str(tweet_id)]["user_name"]

        if action == "like":
            liked = yield from self.like_tweet(tweet_id)
            if liked:
                new_interacted_tweet_ids.append(int(tweet_id))

        elif action == "follow" and user_id:
            followed = yield from self.follow_user(user_id)
            if followed:
                new_interacted_tweet_ids.append(int(tweet_id))

        elif action == "retweet":
            retweeted = yield from self.retweet(tweet_id)
            if retweeted:
                new_interacted_tweet_ids.append(int(tweet_id))

        elif action == "reply":
            responded = yield from self.respond_tweet(tweet_id, text)
            if responded:
                new_interacted_tweet_ids.append(int(tweet_id))

        elif action == "quote":
            quoted = yield from self.respond_tweet(
                tweet_id, text, quote=True, user_name=user_name
            )
            if quoted:
                new_interacted_tweet_ids.append(int(tweet_id))

    def _handle_tweet_with_media(
        self, text: str, previous_tweets: dict, persona: str
    ) -> Generator[None, None, None]:
        """Handle creating a new tweet with media."""
        # Optionally, replace the tweet with one generated by the alternative model
        new_text = yield from self.replace_tweet_with_alternative_model(
            ALTERNATIVE_MODEL_TWITTER_PROMPT.format(
                persona=persona,
                previous_tweets=previous_tweets,
            )
        )
        text = new_text or text

        if not is_tweet_valid(text):
            self.context.logger.error("The tweet is too long.")
            return

        # Get the latest image path from the database
        db_data = yield from self._read_kv(keys=("latest_image_path",))

        if not db_data or "latest_image_path" not in db_data:
            self.context.logger.error(
                "No image path found for tweet_with_media action."
            )
            return

        image_path = db_data["latest_image_path"]
        self.context.logger.info(f"Using image from path: {image_path}")

        # Upload the media first
        media_id = yield from self._call_twikit(
            method="upload_media",
            media_path=image_path,  # Pass the path as a string, not as a dictionary
        )

        if not media_id:
            self.context.logger.error(f"Failed to upload media from path: {image_path}")
            return

        # Post tweet with the uploaded media ID
        self.context.logger.info(f"Posting tweet with media_id: {media_id}")
        tweet_ids = yield from self._call_twikit(
            method="post", tweets=[{"text": text, "media_ids": [media_id]}]
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting tweet with media to Twitter.")
            return

        latest_tweet = {
            "tweet_id": tweet_ids[0],
            "text": text,
            "media_path": image_path,
            "timestamp": self.get_sync_timestamp(),
        }

        # Write latest tweet to the database
        yield from self.store_tweet(latest_tweet)
        self.context.logger.info("Wrote latest tweet with media to db")

    def generate_mech_tool_info(self) -> str:
        """Generate tool info"""

        tools_dict = self.params.tools_for_mech
        tools_info = "\n" + "\n".join(
            [
                f"- {tool_name}: {tool_description}"
                for tool_name, tool_description in tools_dict.items()
            ]
        )
        self.context.logger.info(tools_info)
        return tools_info

    def get_agent_handles(self) -> Generator[None, None, List[str]]:
        """Get the agent handles"""
        agent_handles = yield from self.get_memeooorr_handles_from_mirror_db()
        if agent_handles:
            # Filter out suspended accounts
            agent_handles = yield from self._call_twikit(
                method="filter_suspended_users",
                user_names=agent_handles,
            )

        else:
            # using subgraph to get memeooorr handles as a fallback
            self.context.logger.info(
                "No memeooorr handles from MirrorDB , Now trying subgraph"
            )
            agent_handles = yield from self.get_memeooorr_handles_from_subgraph()
            # filter out suspended accounts
            agent_handles = yield from self._call_twikit(
                method="filter_suspended_users",
                user_names=agent_handles,
            )

        return agent_handles


class ActionTweetBehaviour(BaseTweetBehaviour):  # pylint: disable=too-many-ancestors
    """ActionTweetBehaviour"""

    matching_round: Type[AbstractRound] = ActionTweetRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = yield from self.get_event()

            payload = ActionTweetPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> Generator[None, None, str]:
        """Get the next event"""
        pending_tweet = self.synchronized_data.token_action["tweet"]
        if not pending_tweet:
            self.context.logger.info("Post-action tweet is missing")
            return Event.MISSING_TWEET.value
        self.context.logger.info("Sending the action tweet...")
        latest_tweet = yield from self.post_tweet(tweet=[pending_tweet], store=False)
        return Event.DONE.value if latest_tweet else Event.ERROR.value
