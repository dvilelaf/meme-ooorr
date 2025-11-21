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

"""This module contains the information about the rounds that is used by the Http handler."""


ROUNDS_INFO = {
    "action_decision_round": {
        "name": "Deciding Next Action",
        "description": "Evaluates current meme tokens and chooses a strategic move—investing, unleashing, collecting, or doing nothing—to optimise returns",
    },
    "action_preparation_round": {
        "name": "Preparing Action Transaction",
        "description": "Constructs the exact on-chain command for the chosen token action, ensuring all parameters are set for successful execution",
    },
    "action_tweet_round": {
        "name": "Posting Action Tweet",
        "description": "Notifies followers about the executed token action, reinforcing engagement and transparency in the ongoing narrative",
    },
    "check_funds_round": {
        "name": "Checking Funds",
        "description": "Verifies available currency to ensure the feasibility of deploying tokens or conducting further actions",
    },
    "check_late_tx_hashes_round": {
        "name": "Checking late transaction hashes",
        "description": "Checks late transaction hashes",
    },
    "check_transaction_history_round": {
        "name": "Checking the transaction history",
        "description": "Checks the transaction history",
    },
    "collect_feedback_round": {
        "name": "Collecting Feedback",
        "description": "Compiles replies from the latest tweet, extracting conditions and sentiments that guide future persona or strategy adjustments",
    },
    "collect_signature_round": {
        "name": "Collecting agent signatures",
        "description": "Collects agent signatures for a transaction",
    },
    "engage_twitter_round": {
        "name": "Engaging with other agents",
        "description": "Responds to tweets from other agents",
    },
    "finalization_round": {
        "name": "Sending a transaction",
        "description": "Sends a transaction for mining",
    },
    "load_database_round": {
        "name": "Loading Database",
        "description": "Retrieves saved persona and latest tweet data from storage, ensuring the activity restarts with consistent context",
    },
    "pull_memes_round": {
        "name": "Pulling Meme Data",
        "description": "Fetches updated information on existing meme tokens, determining which may benefit from actions like hearting or unleashing",
    },
    "randomness_transaction_submission_round": {
        "name": "Getting some randomness",
        "description": "Gets randomness from a decentralized randomness source",
    },
    "registration_round": {
        "name": "Registering agents ",
        "description": "Initializes the agent registration process",
    },
    "registration_startup_round": {
        "name": "Registering agents at startup",
        "description": "Initializes the agent registration process",
    },
    "reset_and_pause_round": {
        "name": "Cleaning up and sleeping for some time",
        "description": "Cleans up and sleeps for some time before running again",
    },
    "reset_round": {
        "name": "Cleaning up and resetting",
        "description": "Cleans up and resets the agent",
    },
    "select_keeper_transaction_submission_a_round": {
        "name": "Selecting an agent to send the transaction",
        "description": "Selects an agent to send the transaction",
    },
    "select_keeper_transaction_submission_b_after_timeout_round": {
        "name": "Selecting an agent to send the transaction",
        "description": "Selects an agent to send the transaction",
    },
    "select_keeper_transaction_submission_b_round": {
        "name": "Selecting an agent to send the transaction",
        "description": "Selects an agent to send the transaction",
    },
    "synchronize_late_messages_round": {
        "name": "Synchronizing late messages",
        "description": "Synchronizes late messages",
    },
    "transaction_multiplexer_round": {
        "name": "Orchestrating Transactions",
        "description": "Coordinates multiple blockchain operations into a coherent sequence, ensuring efficient and timely execution of strategic steps",
    },
    "validate_transaction_round": {
        "name": "Validating the transaction",
        "description": "Checks that the transaction was successful",
    },
    "call_checkpoint_round": {
        "name": "Calling checkpoint",
        "description": "Verifies if service is staked and enough time has passed to trigger a checkpoint call",
    },
    "check_staking_round": {
        "name": "Checking staking",
        "description": "Verifies staking status and KPIs including transaction count and liveness requirements",
    },
    "post_tx_decision_making_round": {
        "name": "Post Transaction Decision Making",
        "description": "Evaluates transaction outcomes and determines next actions based on success/failure status",
    },
    "transaction_loop_check_round": {
        "name": "Transaction Loop Check",
        "description": "Checks if the transaction settlement ABCI is in an infinite loop and breaks it if it is",
    },
    "failed_mech_request_round": {
        "name": "Failed Mech Request",
        "description": "Handles a failed Mech request",
    },
    "failed_mech_response_round": {
        "name": "Failed Mech Response",
        "description": "Handles a failed Mech response",
    },
    "mech_request_round": {
        "name": "Mech Request",
        "description": "Handles a Mech request",
    },
    "mech_response_round": {
        "name": "Mech Response",
        "description": "Handles a Mech response",
    },
    "post_mech_response_round": {
        "name": "Post Mech response",
        "description": "Handles a post Mech response",
    },
    "mech_purchase_subscription_round": {
        "name": "Preparing an NVM purchase subscription tx",
        "description": "Preparing a transaction to purchase an NVM subscription, in order to interact with an NVM Mech",
        "transitions": {},
    },
    "fetch_performance_data_round": {
        "name": "Fetching agent performance summary",
        "description": "Fetches the agent performance summary data",
    },
}
