#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
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


"""Updates fetched agent with correct config"""
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv


AGENT_NAME = "agents_fun"

PATH_TO_VAR = {
    # Chains
    "config/ledger_apis/base/address": "BASE_LEDGER_RPC",
    "config/ledger_apis/base/chain_id": "BASE_LEDGER_CHAIN_ID",
    # Params
    "models/params/args/setup/all_participants": "ALL_PARTICIPANTS",
    "models/params/args/reset_tendermint_after": "RESET_TENDERMINT_AFTER",
    "models/params/args/reset_pause_duration": "RESET_PAUSE_DURATION",
    "models/params/args/termination_from_block": "TERMINATION_FROM_BLOCK",
    "models/params/args/on_chain_service_id": "ON_CHAIN_SERVICE_ID",
    "models/params/args/minimum_gas_balance": "MINIMUM_GAS_BALANCE",
    "models/params/args/min_feedback_replies": "MIN_FEEDBACK_REPLIES",
    "models/params/args/setup/safe_contract_address": "SAFE_CONTRACT_ADDRESS",
    "models/params/args/persona": "PERSONA",
    "models/params/args/skip_engagement": "SKIP_ENGAGEMENT",
    "models/params/args/staking_token_contract_address": "STAKING_TOKEN_CONTRACT_ADDRESS",
    "models/params/args/activity_checker_contract_address": "ACTIVITY_CHECKER_CONTRACT_ADDRESS",
    # Twikit connection
    # "config/twikit_username": "TWIKIT_USERNAME",
    # "config/twikit_email": "TWIKIT_EMAIL",
    # "config/twikit_password": "TWIKIT_PASSWORD",
    # "config/twikit_cookies": "TWIKIT_COOKIES",
    # "config/twikit_disable_tweets": "TWIKIT_DISABLE_TWEETS",
    # "config/twikit_skip_connection": "TWIKIT_SKIP_CONNECTION",
    # Tweepy connection
    "config/tweepy_consumer_api_key": "TWEEPY_CONSUMER_API_KEY",
    "config/tweepy_consumer_api_key_secret": "TWEEPY_CONSUMER_API_KEY_SECRET",
    "config/tweepy_bearer_token": "TWEEPY_BEARER_TOKEN",
    "config/tweepy_access_token": "TWEEPY_ACCESS_TOKEN",
    "config/tweepy_access_token_secret": "TWEEPY_ACCESS_TOKEN_SECRET",
    # Genai connection
    "config/genai_api_key": "GENAI_API_KEY",
    # Store
    "config/store_path": "STORE_PATH",
    # Mirror DB
    "config/mirror_db_base_url": "MIRROR_DB_BASE_URL",
    # Fireworks API
    "models/params/args/alternative_model_for_tweets": "ALTERNATIVE_MODEL_FOR_TWEETS",
    "models/params/args/fireworks_api_key": "FIREWORKS_API_KEY",
    # Cooldown
    "models/params/args/summon_cooldown_seconds": "SUMMON_COOLDOWN_SECONDS",
}

CONFIG_REGEX = r"\${.*?:(.*)}"


def find_and_replace(config, path, new_value):
    """Find and replace a variable"""

    # Find the correct section where this variable fits
    section_indexes = []
    for i, section in enumerate(config):
        value = section
        try:
            for part in path:
                value = value[part]
            section_indexes.append(i)
        except KeyError:
            continue

    if not section_indexes:
        raise ValueError(f"Could not update {path}")

    # To persist the changes in the config variable,
    # access iterating the path parts but the last part
    for section_index in section_indexes:
        sub_dic = config[section_index]
        for part in path[:-1]:
            sub_dic = sub_dic[part]

        # Now, get the whole string value
        old_str_value = sub_dic[path[-1]]

        # Extract the old variable value
        match = re.match(CONFIG_REGEX, old_str_value)
        old_var_value = match.groups()[0]

        # Replace the old variable with the secret value in the complete string
        new_str_value = old_str_value.replace(old_var_value, new_value)
        sub_dic[path[-1]] = new_str_value

    return config


def main() -> None:
    """Main"""
    load_dotenv()

    # Load the aea config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "r", encoding="utf-8") as file:
        config = list(yaml.safe_load_all(file))

    # Search and replace all the secrets
    for path, var in PATH_TO_VAR.items():
        try:
            new_value = os.getenv(var)
            if new_value is None:
                print(f"Env var {var} is not set")
                continue
            config = find_and_replace(config, path.split("/"), new_value)
        except Exception as e:
            raise ValueError(f"Could not update {path}") from e

    # Dump the updated config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "w", encoding="utf-8") as file:
        yaml.dump_all(config, file, sort_keys=False)


if __name__ == "__main__":
    main()
