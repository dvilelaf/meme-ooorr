# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""This module contains the class to connect to an MemeFactory contract."""

import logging
from typing import Any, Dict, List, Optional, Union, cast

import web3
from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import EthereumApi


PUBLIC_ID = PublicId.from_str("dvilela/meme_factory:0.1.0")

_logger = logging.getLogger(
    f"aea.packages.{PUBLIC_ID.author}.contracts.{PUBLIC_ID.name}.contract"
)


class MemeFactoryContract(Contract):
    """The MemeFactory contract."""

    contract_id = PUBLIC_ID

    @classmethod
    def build_summon_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        token_name: str,
        token_ticker: str,
        total_supply: int = 1000000000000000000000000,  # 1 million tokens for default 18 decimals
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""

        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="summonThisMeme",
            args=[
                token_name,
                token_ticker,
                total_supply,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def build_heart_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        meme_nonce: str,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="heartThisMeme",
            args=[
                meme_nonce,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def build_unleash_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        meme_nonce: str,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="unleashThisMeme",
            args=[meme_nonce],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def build_collect_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        meme_address: str,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""
        meme_address = web3.Web3.to_checksum_address(meme_address)
        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="collectThisMeme",
            args=[
                meme_address,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def build_purge_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        meme_address: str,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""
        meme_address = web3.Web3.to_checksum_address(meme_address)
        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="purgeThisMeme",
            args=[
                meme_address,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def build_burn_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""

        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="scheduleForAscendance",
            args=[],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def get_token_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        tx_hash: str,
    ) -> Dict[str, Optional[str]]:
        """Get the data from the Summoned event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        tx_receipt = ledger_api.api.eth.get_transaction_receipt(tx_hash)  # type: ignore

        for log in tx_receipt["logs"]:
            try:
                event = contract_instance.events.Summoned().process_log(log)
                return {
                    "summoner": event.args["summoner"],
                    "token_nonce": event.args["memeNonce"],
                    "eth_contributed": event.args["amount"],
                }
            except web3.exceptions.MismatchedABI:
                continue

        return {"token_address": None, "summoner": None, "eth_contributed": None}

    @classmethod
    def get_meme_summons_info(
        cls, ledger_api: EthereumApi, contract_address: str, token_address: str
    ) -> Dict[str, Any]:
        """Get the data from the memeTokenNonces."""
        contract_instance = cls.get_instance(ledger_api, contract_address)

        meme_token_nonce = getattr(  # noqa
            contract_instance.functions, "memeTokenNonces"
        )  # noqa
        token_nonce = meme_token_nonce(token_address).call()

        meme_summons = getattr(contract_instance.functions, "memeSummons")  # noqa
        token_data = meme_summons(token_nonce).call()

        return {"token_data": token_data}

    @classmethod
    def get_summon_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        from_block: Optional[int] = None,
    ) -> Dict[str, List]:
        """Get the data from the Summoned event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)

        summon_events: Dict[str, List] = cls.get_events(  # type: ignore
            ledger_api, contract_address, "Summoned", from_block
        )["events"]
        nonce_to_event: Dict[str, Dict] = {e["token_nonce"]: e for e in summon_events}  # type: ignore

        meme_summons = getattr(contract_instance.functions, "memeSummons")  # noqa

        tokens = []
        for nonce in nonce_to_event.keys():
            summon_data = meme_summons(nonce).call()
            token_data = {
                "summoner": nonce_to_event[nonce]["summoner"],
                "token_nonce": nonce,
                "token_address": None,
                "token_name": summon_data[0],
                "token_ticker": summon_data[1],
                "token_supply": summon_data[2],
                "eth_contributed": summon_data[3],
                "summon_time": summon_data[4],
                "unleash_time": summon_data[5],
                "heart_count": summon_data[6],
                "position_id": summon_data[7],
                "is_native_first": summon_data[8],
                "decimals": 18,
            }
            tokens.append(token_data)

        return {"tokens": tokens}

    @classmethod
    def get_events(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        event_name: str,
        from_block: Optional[int] = None,
        to_block: Union[int, str] = "latest",
    ) -> JSONLike:
        """Get events."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        current_block = ledger_api.api.eth.get_block_number()

        if from_block is None:
            from_block = current_block - 86400  # approx 48h ago (2s per block)

        # Avoid parsing too many blocks at a time. This might take too long and
        # the connection could time out.
        MAX_BATCH_BLOCKS = 5000

        to_block = current_block - 1 if to_block == "latest" else to_block

        _logger.info(
            f"Getting {event_name} events from block {from_block} to {to_block} ({int(to_block) - int(from_block)} blocks)"
        )

        ranges: List[int] = list(
            range(from_block, cast(int, to_block), MAX_BATCH_BLOCKS)
        ) + [cast(int, to_block)]

        event = getattr(contract_instance.events, event_name)
        events = []
        for i in range(len(ranges) - 1):
            from_block = ranges[i]
            to_block = ranges[i + 1]
            new_events = []

            _logger.info(f"Block batch {from_block} to {to_block}...")

            while True:
                try:
                    new_events = event.create_filter(
                        fromBlock=from_block,  # exclusive
                        toBlock=to_block,  # inclusive
                    ).get_all_entries()  # limited to 10k entries for now
                    break
                # Gnosis RPCs sometimes returns:
                # ValueError: Filter with id: x does not exist
                # MismatchedABI: The event signature did not match the provided ABI
                # Retrying several times makes it work
                except ValueError as e:
                    _logger.error(e)
                except web3.exceptions.MismatchedABI as e:
                    _logger.error(e)

            events += new_events

        _logger.info(f"Got {len(events)} {event_name} events")

        if event_name == "Summoned":
            return dict(
                events=[
                    {
                        "summoner": e.args["summoner"],
                        "token_nonce": e.args["memeNonce"],
                        "eth_contributed": e.args["amount"],
                    }
                    for e in events
                ],
                latest_block=int(to_block),
            )

        if event_name == "Unleashed":
            return dict(
                events=[
                    {
                        "token_unleasher": e.args["unleasher"],
                        "token_nonce": e.args["memeNonce"],
                        "token_address": e.args["memeToken"],
                        "position_id": e.args["lpTokenId"],
                        "liquidity": e.args["liquidity"],
                    }
                    for e in events
                ],
                latest_block=int(to_block),
            )

        return {}
