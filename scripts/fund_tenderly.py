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

"""This script handles funding wallets on Tenderly"""

import os
from typing import List

import requests
from dotenv import load_dotenv


load_dotenv(override=True)

TENDERLY_ADMIN_RPC = os.getenv("TENDERLY_ADMIN_RPC")

FUND_REQUIREMENTS = {
    "wallets": {
        "agent_memeooorr": "0x7CAcF58b8447C8220dD54aCAfCC6Cad2D58C4f37",
        "safe_memeooorr": "0x66aE2AFb05a970221956ca61F1E34bB2357458db",
    },
    "funds": {
        "native": 10000,  # in ETH
        "0x54330d28ca3357F294334BDC454a032e7f353416": 100000,  # Olas on Base
    },
}


def _fund_wallet(  # nosec
    admin_rpc: str,
    wallet_addresses: List[str],
    amount: int,
    native_or_token_address: str = "native",
) -> None:
    print(f"Funding wallets {wallet_addresses} with token {native_or_token_address}...")
    if native_or_token_address == "native":  # nosec
        json_data = {
            "jsonrpc": "2.0",
            "method": "tenderly_setBalance",
            "params": [
                wallet_addresses,
                hex(int(amount * 1e18)),  # to wei
            ],
            "id": "1234",
        }
    else:
        json_data = {
            "jsonrpc": "2.0",
            "method": "tenderly_setErc20Balance",
            "params": [
                native_or_token_address,
                wallet_addresses,
                hex(int(amount * 1e18)),  # to wei
            ],
            "id": "1234",
        }

    response = requests.post(
        url=admin_rpc,
        timeout=300,
        headers={"Content-Type": "application/json"},
        json=json_data,
    )
    if response.status_code != 200:
        print(response.status_code)
        try:
            print(response.json())
        except requests.exceptions.JSONDecodeError:
            pass


if __name__ == "__main__":
    for fund_type, _amount in FUND_REQUIREMENTS[
        "funds"
    ].items():  # pylint: disable=redefined-outer-name
        _native_or_token_address = "native" if fund_type == "native" else fund_type

        _fund_wallet(
            admin_rpc=TENDERLY_ADMIN_RPC,
            wallet_addresses=list(FUND_REQUIREMENTS["wallets"].values()),
            amount=_amount,
            native_or_token_address=_native_or_token_address,
        )
