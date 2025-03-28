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

"""FFW Tenderly"""

import os

import requests
from dotenv import load_dotenv


load_dotenv(override=True)

TENDERLY_ADMIN_RPC = os.getenv("TENDERLY_ADMIN_RPC")

json_data = {
    "jsonrpc": "2.0",
    "method": "tenderly_setNextBlockTimestamp",
    "params": ["1734109475"],
    "id": "1234",
}

# seconds = hex(1 * 60 * 60)

# json_data = {
#     "jsonrpc": "2.0",
#     "method": "evm_increaseTime",
#     "params": [str(seconds)],
# }


response = requests.post(
    url=TENDERLY_ADMIN_RPC,
    headers={"Content-Type": "application/json"},
    json=json_data,
    timeout=300,
)

print(response)
