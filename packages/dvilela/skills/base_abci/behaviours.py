import json

from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.dvilela.protocols.kv_store.dialogues import (
    KvStoreDialogue,
    KvStoreDialogues,
)
from packages.dvilela.protocols.kv_store.message import KvStoreMessage
from packages.dvilela.connections.kv_store.connection import (
    PUBLIC_ID as KV_STORE_CONNECTION_PUBLIC_ID,
)

from packages.valory.protocols.srr.dialogues import SrrDialogue, SrrDialogues
from packages.valory.protocols.srr.message import SrrMessage

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)

from typing import (
    Any,
    Dict,
    Generator,
    Optional,
    Tuple,
    cast,
)


class BaseSkillBehaviour(BaseBehaviour):
    """Base behaviour for all skill behaviours."""

    ### start of KV local DB realted methods

    def _read_kv(
        self,
        keys: Tuple[str, ...],
    ) -> Generator[None, None, Optional[Dict]]:
        """Send a request message from the skill context."""
        self.context.logger.info(f"Reading keys from db: {keys}")
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.READ_REQUEST,
            keys=keys,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self.do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        if response.performative != KvStoreMessage.Performative.READ_RESPONSE:
            return None

        data = {key: response.data.get(key, None) for key in keys}  # type: ignore

        return data

    def _write_kv(
        self,
        data: Dict[str, str],
    ) -> Generator[None, None, bool]:
        """Send a request message from the skill context."""
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.CREATE_OR_UPDATE_REQUEST,
            data=data,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self.do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        if response is None:
            self.context.logger.error(
                "Received None response from KV Store connection during write."
            )
            return False
        self.context.logger.info(
            f"KV Store write response performative: {response.performative}"
        )
        return response.performative == KvStoreMessage.Performative.SUCCESS

    def read_kv(
        self,
        keys: Tuple[str, ...],
    ) -> Generator[None, None, Optional[Dict]]:
        """
        Public wrapper for reading from key-value store.

        Args:
            keys: Tuple of keys to read from the store.

        Returns:
            Optional[Dict]: The data read from the store, or None if unsuccessful.
        """
        return (yield from self._read_kv(keys=keys))

    def write_kv(
        self,
        data: Dict[str, str],
    ) -> Generator[None, None, bool]:
        """
        Public wrapper for writing to key-value store.

        Args:
            data: Dictionary of key-value pairs to write to the store.

        Returns:
            bool: True if write was successful, False otherwise.
        """
        return (yield from self._write_kv(data=data))

    ### end of KV local DB realted methods
    def _call_genai(
        self,
        method: str,
        **kwargs: Optional[Dict[str, Any]],
    ) -> Generator[None, None, Optional[str]]:
        """Send a request message from the skill context."""

        payload_data: Dict[str, Any] = {
            "method": method,
            "kwargs": kwargs or {},
        }

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(GENAI_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(payload_data),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore
        response_error = response.error

        if response_error:
            self.context.logger.error(response_json)
            return None

        return response_json["response"]  # type: ignore


### start of LLM connection related methods


### end of LLM connection related methods
