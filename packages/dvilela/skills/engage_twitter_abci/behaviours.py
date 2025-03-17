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

"""This package contains round behaviours of EngageTwitterAbciApp."""

import json
import random
import secrets
from datetime import datetime
from typing import Dict, Generator, List, Optional, Set, Tuple, Type, Union

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.engage_twitter_abci.prompts import (
    ALTERNATIVE_MODEL_TWITTER_PROMPT,
    TWITTER_DECISION_PROMPT,
    build_twitter_action_schema,
)
from packages.dvilela.skills.engage_twitter_abci.rounds import (
    EngageTwitterAbciApp,
    EngageTwitterPayload,
    EngageTwitterRound,
    Event,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)


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


class EngageTwitterBehaviour(BaseTweetBehaviour):  # pylint: disable=too-many-ancestors
    """EngageTwitterBehaviour"""

    matching_round: Type[AbstractRound] = EngageTwitterRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = yield from self.get_event()

            payload = EngageTwitterPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> Generator[None, None, str]:
        """Get the next event"""

        if self.params.skip_engagement:
            self.context.logger.info("Skipping engagement on Twitter")
            return Event.DONE.value

        # Get other memeooorr handles
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

        self.context.logger.info(f"Not suspended users: {agent_handles}")

        if not agent_handles:
            self.context.logger.error("No valid Twitter handles")
            return Event.DONE.value

        # Load previously responded tweets
        db_data = yield from self._read_kv(keys=("interacted_tweet_ids",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            interacted_tweet_ids = []
        else:
            interacted_tweet_ids = json.loads(db_data["interacted_tweet_ids"] or "[]")

        # Get their latest tweet
        pending_tweets = {}
        for agent_handle in agent_handles:
            # By default only 1 tweet is retrieved (the latest one)
            latest_tweets = yield from self._call_twikit(
                method="get_user_tweets",
                twitter_handle=agent_handle,
            )
            if not latest_tweets:
                self.context.logger.info("Couldn't get any tweets")
                continue
            tweet_id = latest_tweets[0]["id"]

            # Only respond to not previously interacted tweets
            if int(tweet_id) in interacted_tweet_ids:
                self.context.logger.info("Tweet was already interacted with")
                continue

            pending_tweets[tweet_id] = {
                "text": latest_tweets[0]["text"],
                "user_name": latest_tweets[0]["user_name"],
                "user_id": latest_tweets[0]["user_id"],
            }

        # Build and post interactions
        event, new_interacted_tweet_ids = yield from self.interact_twitter(
            pending_tweets
        )

        if event == Event.DONE.value:
            interacted_tweet_ids.extend(new_interacted_tweet_ids)
            # Write latest responded tweets to the database
            yield from self._write_kv(
                {
                    "interacted_tweet_ids": json.dumps(
                        interacted_tweet_ids, sort_keys=True
                    )
                }
            )
            self.context.logger.info("Wrote latest tweet to db")

        return event

    def interact_twitter(  # pylint: disable=too-many-locals,too-many-statements
        self, pending_tweets: dict
    ) -> Generator[None, None, Tuple[str, List]]:
        """Decide whether to like a tweet based on the persona."""
        new_interacted_tweet_ids: List[str] = []
        persona = yield from self.get_persona()

        other_tweets = "\n\n".join(
            [
                f"tweet_id: {t_id}\ntweet_text: {t_data['text']}\nuser_id: {t_data['user_id']}"
                for t_id, t_data in dict(
                    random.sample(list(pending_tweets.items()), len(pending_tweets))
                ).items()
            ]
        )

        tweets = yield from self.get_previous_tweets()  # type: ignore
        tweets = tweets[-5:] if tweets else None  # type: ignore

        if tweets:
            random.shuffle(tweets)
            previous_tweets = "\n\n".join(
                [
                    f"tweet_id: {tweet['tweet_id']}\ntweet_text: {tweet['text']}\ntime: {datetime.fromtimestamp(tweet['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}"
                    for tweet in tweets
                ]
            )
        else:
            previous_tweets = "No previous tweets"

        prompt = TWITTER_DECISION_PROMPT.format(
            persona=persona,
            previous_tweets=previous_tweets,
            other_tweets=other_tweets,
            time=self.get_sync_time_str(),
        )

        llm_response = yield from self._call_genai(
            method="generate_content",
            kwargs={"prompt": prompt, "schema": build_twitter_action_schema()},
        )
        self.context.logger.info(f"LLM response for twitter decision: {llm_response}")

        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return Event.ERROR.value, new_interacted_tweet_ids

        json_response = json.loads(llm_response)

        for interaction in json_response:
            tweet_id = interaction.get("selected_tweet_id", None)
            user_id = interaction.get("user_id", None)
            action = interaction.get("action", None)
            text = interaction.get("text", None)

            if action == "none":
                self.context.logger.error("Action is none")
                continue

            if action != "tweet" and str(tweet_id) not in pending_tweets.keys():
                self.context.logger.error(
                    f"Action is {action} but tweet_id is not valid [{tweet_id}]"
                )
                continue

            if action == "follow" and (
                not user_id
                or user_id not in [t["user_id"] for t in pending_tweets.values()]
            ):
                self.context.logger.error(
                    f"Action is {action} but user_id is not valid [{user_id}]"
                )
                continue

            # use yield from self.sleep(1) to simulate a delay use secrests to randomize the delay
            # adding random delay to avoid rate limiting
            delay = secrets.randbelow(5)
            self.context.logger.info(f"Sleeping for {delay} seconds")
            yield from self.sleep(delay)

            self.context.logger.info("Sending a new tweet")
            if action == "tweet":
                # Optionally, replace the tweet with one generated by the alternative LLM
                new_text = yield from self.replace_tweet_with_alternative_model(
                    ALTERNATIVE_MODEL_TWITTER_PROMPT.format(
                        persona=persona,
                        previous_tweets=previous_tweets,
                    )
                )
                text = new_text or text
                yield from self.post_tweet(tweet=[text], store=True)
                continue

            self.context.logger.info(f"Trying to {action} tweet {tweet_id}")
            user_name = pending_tweets[str(tweet_id)]["user_name"]

            if action == "like":
                liked = yield from self.like_tweet(tweet_id)
                if liked:
                    new_interacted_tweet_ids.append(tweet_id)
                continue

            if action == "follow" and user_id:
                followed = yield from self.follow_user(user_id)
                if followed:
                    new_interacted_tweet_ids.append(tweet_id)
                continue

            if action == "retweet":
                retweeted = yield from self.retweet(tweet_id)
                if retweeted:
                    new_interacted_tweet_ids.append(tweet_id)
                continue

            if not is_tweet_valid(text):
                self.context.logger.error("The tweet is too long.")
                continue

            if action == "reply":
                responded = yield from self.respond_tweet(tweet_id, text)
                if responded:
                    new_interacted_tweet_ids.append(tweet_id)

            if action == "quote":
                quoted = yield from self.respond_tweet(
                    tweet_id, text, quote=True, user_name=user_name
                )
                if quoted:
                    new_interacted_tweet_ids.append(tweet_id)

        return Event.DONE.value, new_interacted_tweet_ids


class EngageTwitterRoundBehaviour(AbstractRoundBehaviour):
    """EngageTwitterRoundBehaviour"""

    initial_behaviour_cls = EngageTwitterBehaviour
    abci_app_cls = EngageTwitterAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        EngageTwitterBehaviour,
    ]
