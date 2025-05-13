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
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, Type, Union
from uuid import uuid4

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import (
    ALTERNATIVE_MODEL_TWITTER_PROMPT,
    ENFORCE_ACTION_COMMAND,
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


# Define a context holder for interaction processing
@dataclass
class InteractionContext:
    """Holds the context required for processing multiple Twitter interactions within a single period."""

    pending_tweets: dict
    previous_tweets: Optional[List[dict]]
    persona: str
    new_interacted_tweet_ids: List[int]


class BaseTweetBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
    """Base behaviour for tweet-related actions."""

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
        tweet_ids = yield from self._call_tweepy(
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

        self.context.logger.info(f"Replying to tweet with ID: {tweet_id}")
        tweet = {"text": text}
        if quote:
            tweet["attachment_url"] = f"https://x.com/{user_name}/status/{tweet_id}"
        else:
            tweet["reply_to"] = tweet_id
        tweet_ids = yield from self._call_tweepy(
            method="post",
            tweets=[tweet],
        )
        return tweet_ids is not None and tweet_ids

    def like_tweet(self, tweet_id: str) -> Generator[None, None, bool]:
        """Like a tweet"""
        self.context.logger.info(f"Liking tweet with ID: {tweet_id}")
        try:
            response = yield from self._call_tweepy(
                method="like_tweet", tweet_id=tweet_id
            )
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for like_tweet ID {tweet_id} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
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
            response = yield from self._call_tweepy(method="retweet", tweet_id=tweet_id)
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for retweet ID {tweet_id} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
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

    def follow_user(self, user_name: str) -> Generator[None, None, bool]:
        """Follow user"""
        self.context.logger.info(f"Following user with user_name: {user_name}")
        try:
            response = yield from self._call_tweepy(
                method="follow_by_username", username=user_name
            )
            if response is None:
                self.context.logger.error(
                    f"Tweepy call for follow_user user_name {user_name} failed (returned None). See previous logs for details."
                )
                return False

            if not response.get("success", False):
                error_message = response.get("error", "Unknown error occurred.")
                self.context.logger.error(
                    f"Error Following user with user_name {user_name}: {error_message}"
                )
                return False
            return response["success"]
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Exception following user with user_name {user_name}: {e}"
            )
            return False

    def _parse_mirrordb_tweet_details(
        self, json_value: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extracts and formats tweet details from MirrorDB json_value."""
        if not (
            isinstance(json_value, dict)
            and json_value.get("action") == "post"
            and isinstance(json_value.get("details"), dict)
        ):
            return None

        details = json_value["details"]
        timestamp_str = json_value.get("timestamp")
        tweet_id = details.get("tweet_id")
        text = details.get("text")

        if not (tweet_id and text and timestamp_str):
            return None

        timestamp = self.parse_iso_timestamp(timestamp_str)
        if timestamp is None:
            # Logged in parse_iso_timestamp
            return None

        return {
            "tweet_id": tweet_id,
            "text": text,
            "timestamp": timestamp,  # Store as timestamp float
            "created_at": timestamp_str,  # Keep original string too
        }

    def _process_mirrordb_attributes(
        self,
        all_attributes: Optional[List[Dict]],
        interactions_attr_def_id: int,
        limit: int,
        agent_id: int,  # Added for logging
    ) -> Optional[List[Dict]]:
        """Process attributes fetched from MirrorDB to extract posted tweets."""
        if not all_attributes or not isinstance(all_attributes, list):
            log_msg = (
                f"No attributes found for agent {agent_id}."
                if all_attributes is None
                else f"Unexpected response type from MirrorDB: {type(all_attributes)}. Expected list."
            )
            self.context.logger.info(log_msg)
            return None

        self.context.logger.info(
            f"Retrieved {len(all_attributes)} attributes from MirrorDB for agent {agent_id}."
        )
        posted_tweets = []
        for attr in all_attributes:
            if attr.get("attr_def_id") == interactions_attr_def_id:
                json_value = attr.get("json_value")
                # Ensure json_value is a dictionary before parsing
                if isinstance(json_value, dict):
                    tweet_details = self._parse_mirrordb_tweet_details(json_value)
                    if tweet_details:
                        posted_tweets.append(tweet_details)
                else:
                    self.context.logger.warning(
                        f"Attribute {attr.get('attribute_id')} has missing or invalid json_value."
                    )

        if not posted_tweets:
            self.context.logger.info(
                f"No 'post' interaction attributes found for agent {agent_id} with attr_def_id {interactions_attr_def_id}."
            )
            return None

        # Sort tweets by timestamp (most recent first)
        posted_tweets.sort(key=lambda x: x["timestamp"], reverse=True)
        self.context.logger.info(
            f"Found {len(posted_tweets)} posted tweets in MirrorDB attributes. Returning latest {limit}."
        )
        return posted_tweets[:limit]

    def _fetch_tweets_from_mirrordb(
        self, limit: int
    ) -> Generator[None, None, Optional[List[Dict]]]:
        """Fetch latest tweets from MirrorDB."""
        self.context.logger.info("Trying to get latest tweets from MirrorDB for agent")
        mirror_db_config_data = (
            yield from self.mirrordb_helper.mirror_db_registration_check()
        )

        if not mirror_db_config_data:
            self.context.logger.warning("No MirrorDB config found.")
            return None

        agent_id = mirror_db_config_data.get("agent_id")
        interactions_attr_def_id_raw = mirror_db_config_data.get(
            "twitter_interactions_attr_def_id"
        )

        if not agent_id or not interactions_attr_def_id_raw:
            self.context.logger.warning(
                "MirrorDB config missing agent_id or twitter_interactions_attr_def_id."
            )
            return None

        try:
            interactions_attr_def_id = int(interactions_attr_def_id_raw)
            endpoint = f"/api/agents/{agent_id}/attributes/"
            self.context.logger.info(f"Calling MirrorDB endpoint: GET {endpoint}")

            all_attributes = yield from self.mirrordb_helper.call_mirrordb(
                http_method="GET",
                endpoint=endpoint,
            )

            return self._process_mirrordb_attributes(
                all_attributes, interactions_attr_def_id, limit, agent_id
            )

        except (ValueError, TypeError) as e:
            self.context.logger.error(f"Error processing MirrorDB config ID: {e}")
            return None
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Error getting or processing attributes from MirrorDB: {e}"
            )
            return None

    def _fetch_tweets_from_kv(
        self, limit: int
    ) -> Generator[None, None, Optional[List[Dict]]]:
        """Fetch latest tweets from the local KV store as a fallback."""
        self.context.logger.info(
            f"Getting latest {limit} tweets from local DB as fallback."
        )
        tweets = yield from self.get_tweets_from_db()

        if not tweets:
            self.context.logger.info("No tweets found in local KV store.")
            return None

        # Process timestamps if needed (assuming 'created_at' might be ISO string)
        processed_tweets = []
        for tweet in tweets:
            # Ensure timestamp is float, parse if needed
            if "timestamp" not in tweet or not isinstance(
                tweet["timestamp"], (int, float)
            ):
                created_at = tweet.get("created_at")
                if created_at and isinstance(created_at, str):
                    timestamp = self.parse_iso_timestamp(created_at)
                    if timestamp:
                        tweet["timestamp"] = timestamp
                    else:
                        self.context.logger.warning(
                            f"Could not parse 'created_at' for tweet {tweet.get('tweet_id')}, skipping timestamp update."
                        )
                else:
                    self.context.logger.warning(
                        f"Tweet {tweet.get('tweet_id')} missing valid 'timestamp' and 'created_at'."
                    )
            processed_tweets.append(tweet)

        return processed_tweets[:limit]

    def get_previous_tweets(  # pylint: disable=too-many-locals
        self, limit: int = 5
    ) -> Generator[None, None, Optional[List[Dict]]]:
        """Get the latest tweets posted by the agent.

        Tries to fetch interaction attributes from MirrorDB first.
        Falls back to local KV store if MirrorDB fails or returns no results.

        Args:
            limit (int, optional): Maximum number of tweets to return. Defaults to 5.

        Returns:
            Generator yielding Optional[List[Dict]]: List of tweets or None
        """
        mirror_tweets = yield from self._fetch_tweets_from_mirrordb(limit)

        if mirror_tweets is not None:
            # MirrorDB succeeded, even if it returned an empty list []
            return mirror_tweets

        # Fallback to KV store if MirrorDB failed (returned None)
        self.context.logger.info(
            "Couldn't fetch tweets from MirrorDB. Falling back to local KV store."
        )
        kv_tweets = yield from self._fetch_tweets_from_kv(limit)

        return kv_tweets


def _format_previous_tweets_str(tweets: Optional[List[Dict]]) -> str:
    """Format the list of previous tweets into a string for the prompt."""
    if not tweets:
        return "No previous tweets"

    random.shuffle(tweets)
    return "\n\n".join(
        [
            f"tweet_id: {tweet['tweet_id']}\ntweet_text: {tweet['text']}\ntime: {datetime.fromtimestamp(tweet['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}"
            for tweet in tweets
        ]
    )


class CollectFeedbackBehaviour(
    BaseTweetBehaviour
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

    def get_feedback(self) -> Generator[None, None, Optional[List[Dict[str, Any]]]]:
        """Get the responses to our agent's tweets from MirrorDB."""

        self.context.logger.info(
            "Attempting to get replies to agent's tweets from MirrorDB."
        )

        all_replies = yield from self.get_replies_to_my_tweets_from_mirrordb(
            limit=100, skip=0
        )

        if all_replies is None or not all_replies:
            self.context.logger.info(
                "Returning empty list as no replies are available or retrieved."
            )
            return []

        self.context.logger.info(f"Retrieved {len(all_replies)} replies from MirrorDB.")

        # Sort by 'reply_timestamp' in descending order (most recent first).
        # Timestamps are ISO strings like "2024-01-15T12:30:45.123Z"
        all_replies.sort(key=lambda r: r.get("reply_timestamp", ""), reverse=True)

        # Keep only the most relevant (e.g., latest 10)
        feedback_to_return = all_replies[:10]

        return feedback_to_return


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

        # Handle differently based on mech_for_twitter state
        if self.synchronized_data.mech_for_twitter:
            (
                pending_tweets,
                interacted_tweet_ids,
            ) = yield from self._handle_mech_for_twitter()
        else:
            # Skip engagement if configured
            if self.params.skip_engagement:
                self.context.logger.info("Skipping engagement on Twitter")
                return Event.DONE.value, new_mech_requests
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
        if pending_tweets_data and pending_tweets_data.get(
            "pending_tweets_for_tw_mech"
        ):
            pending_tweets = json.loads(
                pending_tweets_data["pending_tweets_for_tw_mech"]
            )
        else:
            self.context.logger.warning(
                "No pending tweets found in KV store or value is empty."
            )

        # Fetch previously interacted tweets
        interacted_ids_data = yield from self._read_kv(
            keys=("interacted_tweet_ids_for_tw_mech",)
        )
        interacted_tweet_ids = []
        if interacted_ids_data and interacted_ids_data.get(
            "interacted_tweet_ids_for_tw_mech"
        ):
            interacted_tweet_ids = json.loads(
                interacted_ids_data["interacted_tweet_ids_for_tw_mech"]
            )
        else:
            self.context.logger.warning(
                "No interacted tweets found in KV store or value is empty."
            )

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
        pending_tweets: Dict = {}

        for agent_handle in agent_handles:
            # latest_tweets = None  # TODO: get from agent_db

            latest_tweets = yield from self.fetch_latest_tweets_from_mirror_db(
                agent_handle, 1
            )

            if not latest_tweets:
                self.context.logger.info(f"Couldn't get any tweets from {agent_handle}")
                continue

            tweet_data = latest_tweets[0]

            tweet_id = tweet_data["tweet_id"]
            # Skip previously interacted tweets
            if int(tweet_id) in interacted_tweet_ids:
                self.context.logger.info(
                    f"Tweet {tweet_id} was already interacted with"
                )
                continue

            pending_tweets[tweet_id] = {
                "text": tweet_data["text"],
                "user_name": tweet_data["user_name"],
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
    ) -> Generator[None, None, Tuple[str, Optional[List[Dict]]]]:
        """Prepare the prompt data for LLM decision making."""
        if self.synchronized_data.mech_for_twitter:
            prompt, previous_tweets = yield from self._prepare_mech_prompt_data(persona)
        else:
            prompt, previous_tweets = yield from self._prepare_standard_prompt_data(
                pending_tweets, persona
            )

        # saving the prompt to the kv store for retrying if llm response is invalid
        yield from self._write_kv({"last_prompt": prompt})

        return prompt, previous_tweets

    def _prepare_standard_prompt_data(
        self, pending_tweets: dict, persona: str
    ) -> Generator[None, None, Tuple[str, Optional[List[Dict]]]]:
        """Prepare prompt data when mech_for_twitter is False."""
        self.context.logger.info(
            "Standard engagement: using prompt for decision and introducing tools to LLM"
        )

        # Prepare other tweets data
        items_for_formatting: List[Tuple[Any, Any]] = []
        if pending_tweets:
            items_for_formatting = list(
                dict(
                    random.sample(list(pending_tweets.items()), len(pending_tweets))
                ).items()
            )

        other_tweets = "\n\n".join(
            [
                f"tweet_id: {t_id}\ntweet_text: {t_data['text']}\nuser_name: {t_data['user_name']}"
                for t_id, t_data in items_for_formatting
            ]
        )

        # Get previous tweets
        tweets = yield from self.get_previous_tweets()
        tweets = tweets[-5:] if tweets else None
        previous_tweets_str = _format_previous_tweets_str(tweets)
        # Keep original list/dict structure for return value, if needed later
        previous_tweets_for_return = (
            tweets if isinstance(tweets, (list, dict)) else None
        )

        is_staking_kpi_met = self.synchronized_data.is_staking_kpi_met
        extra_command = ENFORCE_ACTION_COMMAND if is_staking_kpi_met is False else ""

        prompt = TWITTER_DECISION_PROMPT.format(
            persona=persona,
            previous_tweets=previous_tweets_str,
            other_tweets=other_tweets,
            mech_response="",
            tools=self.generate_mech_tool_info(),
            time=self.get_sync_time_str(),
            extra_command=extra_command,
        )

        # Save data for future mech responses
        yield from self._save_standard_kv_data(tweets, pending_tweets)

        return prompt, previous_tweets_for_return

    def _save_standard_kv_data(
        self, tweets: Optional[List[Dict]], pending_tweets: dict
    ) -> Generator[None, None, None]:
        """Save data to KV store for potential future mech responses."""
        self.context.logger.info(
            "Saving standard prompt data (previous tweets, pending tweets) to KV store for potential future mech use"
        )
        yield from self._write_kv({"previous_tweets_for_tw_mech": json.dumps(tweets)})
        yield from self._write_kv(
            {"other_tweets_for_tw_mech": json.dumps(pending_tweets)}
        )

    def _prepare_mech_prompt_data(
        self, persona: str
    ) -> Generator[None, None, Tuple[str, Optional[List[Dict]]]]:
        """Prepare prompt data when mech_for_twitter is True."""
        # Read saved data for mech response
        previous_tweets_data = yield from self._get_stored_kv_data(
            "previous_tweets_for_tw_mech", []
        )
        other_tweets_data = yield from self._get_stored_kv_data(
            "other_tweets_for_tw_mech", {}
        )

        # Ensure previous_tweets is Optional[List[Dict]]
        previous_tweets = (
            previous_tweets_data if isinstance(previous_tweets_data, list) else None
        )
        previous_tweets_str = _format_previous_tweets_str(previous_tweets)

        # Ensure other_tweets is str (formatted string)
        other_tweets_str = (
            "\n\n".join(
                [
                    f"tweet_id: {t_id}\ntweet_text: {t_data['text']}\nuser_name: {t_data['user_name']}"
                    for t_id, t_data in other_tweets_data.items()
                ]
            )
            if isinstance(other_tweets_data, dict)
            else "No other tweets found"
        )

        # Check mech responses (optional, for logging or validation)
        if not self.synchronized_data.mech_responses:
            self.context.logger.error("No mech responses found")

        # Determine media type summary for the prompt
        mech_summary = yield from self._determine_mech_summary()

        # Prepare prompt with mech response summary
        subprompt_with_mech_response = MECH_RESPONSE_SUBPROMPT.format(
            mech_response=mech_summary
        )

        prompt = TWITTER_DECISION_PROMPT.format(
            persona=persona,
            previous_tweets=previous_tweets_str,
            other_tweets=other_tweets_str,
            mech_response=subprompt_with_mech_response,
            tools=self.generate_mech_tool_info(),
            time=self.get_sync_time_str(),
            extra_command="",
        )

        # Clear stored data
        yield from self._clear_mech_kv_data()

        return prompt, previous_tweets

    def _clear_mech_kv_data(self) -> Generator[None, None, None]:
        """Clear KV store entries related to mech twitter interaction."""
        self.context.logger.info(
            "Clearing mech-related twitter data from KV store: previous_tweets, other_tweets, interacted_ids, pending_tweets"
        )
        yield from self._write_kv({"previous_tweets_for_tw_mech": ""})
        yield from self._write_kv({"other_tweets_for_tw_mech": ""})
        yield from self._write_kv({"interacted_tweet_ids_for_tw_mech": ""})
        yield from self._write_kv({"pending_tweets_for_tw_mech": ""})

    def _get_latest_media_info(self) -> Generator[None, None, Optional[Dict]]:
        """Reads and parses the 'latest_media_info' from the KV store."""
        try:
            media_info_data = yield from self._read_kv(keys=("latest_media_info",))
            if (
                not media_info_data
                or "latest_media_info" not in media_info_data
                or not media_info_data["latest_media_info"]
            ):
                self.context.logger.warning(
                    "Could not find valid 'latest_media_info' in KV store."
                )
                return None

            media_info = json.loads(media_info_data["latest_media_info"])
            return media_info
        except json.JSONDecodeError:
            self.context.logger.error(
                "Failed to parse 'latest_media_info' JSON from KV store."
            )
            return None
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Error reading or processing 'latest_media_info' from KV: {e}"
            )
            return None

    def _determine_mech_summary(self) -> Generator[None, None, str]:
        """Determine the mech summary string based on media info in KV store."""
        mech_summary = "The mech response processing failed, proceed with tweet_with_media action."  # Default/Fallback
        media_info = yield from self._get_latest_media_info()

        if media_info:
            media_type = media_info.get("type")
            if media_type == "image":
                mech_summary = "The previous tool execution generated an image."
            elif media_type == "video":
                mech_summary = "The previous tool execution generated a video."
            else:
                self.context.logger.warning(
                    f"Found media info in KV store, but type was unexpected: {media_type}"
                )
        # If media_info is None, the error/warning is already logged by _get_latest_media_info

        return mech_summary

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

    def _validate_mech_llm_response(self, json_response: dict) -> bool:
        """Validate LLM response when mech_for_twitter is True."""
        tweet_action = json_response.get("tweet_action")
        if not isinstance(tweet_action, dict):
            self.context.logger.error(
                "Invalid LLM response: expected tweet_action object when mech_for_twitter is True"
            )
            return False

        # Check both possible field names: action_type (schema format) and action (actual response format)
        action = tweet_action.get("action_type", tweet_action.get("action"))
        if action != "tweet_with_media":
            self.context.logger.error(
                f"Invalid action type: {action}. Only 'tweet_with_media' is allowed when mech_for_twitter is True"
            )
            return False

        if "text" not in tweet_action:
            self.context.logger.error(
                "Invalid tweet_with_media action: missing 'text' field"
            )
            return False

        return True

    def _validate_non_mech_tweet_action(
        self, tweet_action: Union[dict, List[dict]]
    ) -> bool:
        """Validate the tweet_action part of the LLM response when mech_for_twitter is False."""
        actions_to_check = (
            tweet_action if isinstance(tweet_action, list) else [tweet_action]
        )

        for action_item in actions_to_check:
            if not isinstance(action_item, dict):
                # Basic type check for safety, although schema should handle this.
                continue
            action_type = action_item.get("action_type", action_item.get("action"))
            if action_type == "tweet_with_media":
                self.context.logger.error(
                    "Invalid action: 'tweet_with_media' is not allowed when mech_for_twitter is False"
                )
                return False
        return True

    def _validate_non_mech_tool_action(self, tool_action: dict) -> bool:
        """Validate the tool_action part of the LLM response when mech_for_twitter is False."""
        if not isinstance(tool_action, dict):
            self.context.logger.error(
                f"Invalid tool_action format: expected dict, got {type(tool_action)}"
            )
            return False

        if "tool_name" not in tool_action or "tool_input" not in tool_action:
            self.context.logger.error(
                f"Invalid tool_action format: missing required fields. Got: {tool_action}"
            )
            return False
        return True

    def _validate_non_mech_llm_response(self, json_response: dict) -> bool:
        """Validate LLM response when mech_for_twitter is False."""
        tweet_action = json_response.get("tweet_action")
        if tweet_action is not None and self._validate_non_mech_tweet_action(
            tweet_action
        ):
            return True

        tool_action = json_response.get("tool_action")
        if tool_action is not None and self._validate_non_mech_tool_action(tool_action):
            return True

        self.context.logger.error(
            "Invalid LLM response: neither valid tweet_action nor valid tool_action found"
        )
        return False

    def _validate_llm_response(self, json_response: dict) -> bool:
        """Validate that the LLM response adheres to expected format based on context."""
        if not isinstance(json_response, dict):
            self.context.logger.error(
                f"Invalid LLM response format: expected dict, got {type(json_response)}"
            )
            return False

        if self.synchronized_data.mech_for_twitter:
            return self._validate_mech_llm_response(json_response)

        return self._validate_non_mech_llm_response(json_response)

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
        previous_tweets: Optional[List[dict]],
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

        # Create context object
        context = InteractionContext(
            pending_tweets=pending_tweets,
            previous_tweets=previous_tweets,
            persona=persona,
            new_interacted_tweet_ids=new_interacted_tweet_ids,
        )

        for interaction in tweet_actions:
            # Process each interaction
            yield from self._process_single_interaction(
                interaction, context  # Pass the context object
            )

        return Event.DONE.value, context.new_interacted_tweet_ids, []

    def _process_single_interaction(  # pylint: disable=too-many-locals
        self,
        interaction: dict,
        context: InteractionContext,  # Use InteractionContext
    ) -> Generator[None, None, None]:
        """Process a single tweet interaction."""
        # Ensure interaction is a dictionary
        if not isinstance(interaction, dict):
            self.context.logger.error(f"Invalid interaction format: {interaction}")
            return

        tweet_id = interaction.get("selected_tweet_id", None)
        user_name = interaction.get("user_name", None)
        action = interaction.get("action", None)
        text = interaction.get("text", None)

        # Validate action and parameters (using context)
        if not self._validate_interaction(
            action, tweet_id, user_name, context.pending_tweets
        ):
            return

        # Add random delay to avoid rate limiting
        delay = secrets.randbelow(5)
        self.context.logger.info(f"Sleeping for {delay} seconds")
        yield from self.sleep(delay)

        # Handle tweet action based on type
        if action == "tweet":
            yield from self._handle_new_tweet(
                text, context.previous_tweets, context.persona
            )
        elif action == "tweet_with_media":
            # Delegate to the new handler
            success = yield from self._handle_media_tweet(text)
            if not success:
                self.context.logger.error("Failed to handle tweet_with_media action.")
                # Potentially return or handle error differently if needed
        else:
            yield from self._handle_tweet_interaction(
                action,
                tweet_id,
                text,
                user_name,
                context.pending_tweets,  # Pass needed context items
                context.new_interacted_tweet_ids,
            )

    def _handle_media_tweet(self, text: str) -> Generator[None, None, bool]:
        """Handles the 'tweet_with_media' action, including fetching, uploading, posting, and clearing KV."""
        # Read the combined media info from kv store
        media_info = yield from self._get_latest_media_info()

        if not media_info:
            # Error already logged by helper
            return False  # Indicate failure

        media_path = media_info.get("path")
        media_type = media_info.get("type")

        if not media_path or not media_type:
            self.context.logger.error(
                "Media info from KV store is missing 'path' or 'type'."
            )
            # Clear potentially incomplete info? Or leave it? Let's clear it for safety.
            yield from self._write_kv({"latest_media_info": ""})
            return False  # Indicate failure

        self.context.logger.info(
            f"Extracted media path: {media_path}, type: {media_type}"
        )

        # Clear the media info from KV store *after* successfully extracting path and type
        yield from self._write_kv({"latest_media_info": ""})
        self.context.logger.info("Cleared latest_media_info from KV store.")

        # Ensure media_path is a valid string path (already checked by .get implicitly somewhat)
        if not isinstance(media_path, str):
            self.context.logger.error(f"Invalid media path type: {type(media_path)}")
            return False  # Indicate failure

        # Post tweet with the uploaded media ID
        tweet_ids = yield from self._call_tweepy(
            method="post", tweets=[{"text": text, "image_paths": [media_path]}]
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting tweet with media to Twitter.")
            return False  # Indicate failure

        latest_tweet = {
            "tweet_id": tweet_ids[0],
            "text": text,
            "media_path": media_path,
            "timestamp": self.get_sync_timestamp(),
        }

        # Write latest tweet to the database
        yield from self.store_tweet(latest_tweet)
        self.context.logger.info("Wrote latest tweet with media to db")
        return True  # Indicate success

    def _validate_interaction(
        self, action: str, tweet_id: str, user_name: str, pending_tweets: dict
    ) -> bool:
        """Validate tweet interaction parameters."""
        if action == "none":
            self.context.logger.error("Action is none")
            return False

        # Treat tweet_with_media like tweet - it doesn't need a tweet_id
        # Also, 'follow' action does not need a tweet_id for this specific check.
        if (
            action not in ["tweet", "tweet_with_media", "follow"]
            and str(tweet_id) not in pending_tweets.keys()
        ):
            self.context.logger.error(
                f"Action is {action} but tweet_id is not valid [{tweet_id}]"
            )
            return False

        if action == "follow" and (
            not user_name
            or user_name not in [t["user_name"] for t in pending_tweets.values()]
        ):
            self.context.logger.error(
                f"Action is {action} but user_name is not valid [{user_name}]"
            )
            return False

        return True

    def _handle_new_tweet(
        self, text: str, previous_tweets: Optional[List[Dict]], persona: str
    ) -> Generator[None, None, None]:
        """Handle creating a new tweet."""
        # Format the previous tweets list into a string for the prompt
        previous_tweets_str = _format_previous_tweets_str(previous_tweets)

        # Optionally, replace the tweet with one generated by the alternative model
        new_text = yield from self.replace_tweet_with_alternative_model(
            ALTERNATIVE_MODEL_TWITTER_PROMPT.format(
                persona=persona,
                previous_tweets=previous_tweets_str,
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
        tweet_id: Optional[str],  # Can be None for follow
        text: Optional[str],
        user_name: Optional[str],  # Target for follow
        pending_tweets: dict,
        new_interacted_tweet_ids: List[int],
    ) -> Generator[None, None, None]:
        """Handle interaction with an existing tweet or user."""
        if text and not is_tweet_valid(text):
            self.context.logger.error("The tweet is too long.")
            return

        user_name_for_quote: Optional[str] = None

        if action == "follow":
            if not user_name:  # Safeguard, should be validated by _validate_interaction
                self.context.logger.error(
                    "Follow action initiated but no user_name provided."
                )
                return
            self.context.logger.info(f"Trying to {action} user {user_name}")
        else:  # For like, retweet, reply, quote
            if (
                tweet_id is None
            ):  # Safeguard, should be validated by _validate_interaction
                self.context.logger.error(
                    f"Action {action} initiated but no tweet_id provided."
                )
                return

            self.context.logger.info(f"Trying to {action} tweet {tweet_id}")
            str_tweet_id = str(tweet_id)  # tweet_id is not None here

            if str_tweet_id not in pending_tweets:
                self.context.logger.error(
                    f"Tweet ID {tweet_id} not found in pending tweets for {action} interaction."
                )
                return

            if action == "quote":
                user_name_for_quote = pending_tweets[str_tweet_id].get("user_name")
                if not user_name_for_quote:
                    self.context.logger.error(
                        f"User name for tweet {tweet_id} not found in pending_tweets, required for quote."
                    )
                    return

        success = False
        if action == "like":
            # tweet_id is guaranteed to be non-None here by the checks above for non-follow actions
            success = yield from self.like_tweet(tweet_id)  # type: ignore
        elif action == "follow" and user_name:
            success = yield from self.follow_user(user_name)
        elif action == "retweet":
            # tweet_id is guaranteed to be non-None here
            success = yield from self.retweet(tweet_id)  # type: ignore
        elif action == "reply":
            # tweet_id is guaranteed to be non-None here
            success = yield from self.respond_tweet(tweet_id, text)  # type: ignore
        elif action == "quote":
            # tweet_id and user_name_for_quote are guaranteed to be non-None if we reach here
            success = yield from self.respond_tweet(
                tweet_id, text, quote=True, user_name=user_name_for_quote  # type: ignore
            )

        if success and action != "follow" and tweet_id is not None:
            new_interacted_tweet_ids.append(int(tweet_id))

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
        agent_handles = yield from self.mirrordb_helper.get_active_twitter_handles()
        if not agent_handles:
            self.context.logger.info(
                "No memeooorr handles from MirrorDB , Now trying subgraph"
            )
            agent_handles = yield from self.get_memeooorr_handles_from_subgraph()

        # TODO: filter out suspended accounts
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
