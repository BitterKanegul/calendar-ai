from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from config import settings
import os
from dotenv import load_dotenv
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig
import json
load_dotenv(dotenv_path=f'.env.{settings.ENV}')

class MessagesOnlyRedisSaver(AsyncRedisSaver):
    """Custom Redis checkpointer that only saves message fields."""
    
    def _filter_state_for_checkpoint(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Filter state to only include message fields and confirmation state."""
        message_fields = {
            'router_messages',
            'create_messages',
            'delete_messages',
            'list_messages',
            'update_messages',
            'email_messages',
            'leisure_messages',
            'awaiting_confirmation',
            'resolution_plan',
            'resolution_type',
            'confirmation_type',
            'confirmation_data',
        }
        
        # Only keep message fields from the state
        filtered_state = {
            key: value for key, value in state.items() 
            if key in message_fields
        }
        
        return filtered_state
    
    def _filter_versions_for_checkpoint(self, versions: Dict[str, Any]) -> Dict[str, Any]:
        """Filter channel_versions to only include message field versions."""
        message_fields = {
            'router_messages',
            'create_messages',
            'delete_messages',
            'list_messages',
            'update_messages',
            'email_messages',
            'leisure_messages',
            'awaiting_confirmation',
            'resolution_plan',
            'resolution_type',
            'confirmation_type',
            'confirmation_data',
        }
        
        # Only keep versions for message fields
        filtered_versions = {
            key: value for key, value in versions.items() 
            if key in message_fields
        }
        
        return filtered_versions
    
    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Dict[str, Any],
        metadata: Dict[str, Any],
        new_versions: Dict[str, Any]
    ) -> RunnableConfig:
        """Override aput to filter checkpoint data before saving."""
        # Filter the checkpoint to only include messages
        if 'channel_values' in checkpoint:
            checkpoint['channel_values'] = self._filter_state_for_checkpoint(
                checkpoint['channel_values']
            )
        
        # Filter the channel_versions to only include message field versions
        if 'channel_versions' in checkpoint:
            checkpoint['channel_versions'] = self._filter_versions_for_checkpoint(
                checkpoint['channel_versions']
            )

        # Filter new_versions to only include message field versions
        filtered_new_versions = self._filter_versions_for_checkpoint(new_versions)

        return await super().aput(config, checkpoint, metadata, filtered_new_versions)

# dont forget ttl

async def get_checkpointer():
    checkpointer = None
    REDIS_URL = settings.redis_url  
    async with MessagesOnlyRedisSaver.from_conn_string(REDIS_URL) as _checkpointer:
        await _checkpointer.asetup()
        checkpointer = _checkpointer
    

    return checkpointer

