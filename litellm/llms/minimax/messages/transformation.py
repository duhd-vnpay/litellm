"""
MiniMax Anthropic transformation config - extends AnthropicConfig for MiniMax's Anthropic-compatible API
"""
from typing import Optional

import litellm
from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str


class MinimaxMessagesConfig(AnthropicMessagesConfig):
    """
    MiniMax Anthropic configuration that extends AnthropicConfig.
    MiniMax provides an Anthropic-compatible API at:
    - International: https://api.minimax.io/anthropic
    - China: https://api.minimaxi.com/anthropic

    Supported models:
    - MiniMax-M2.1
    - MiniMax-M2.1-lightning
    - MiniMax-M2
    """

    @property
    def custom_llm_provider(self) -> Optional[str]:
        return "minimax"

    @staticmethod
    def get_api_key(api_key: Optional[str] = None) -> Optional[str]:
        """
        Get MiniMax API key from environment or parameters.
        """
        return api_key or get_secret_str("MINIMAX_API_KEY") or litellm.api_key

    @staticmethod
    def get_api_base(
        api_base: Optional[str] = None,
    ) -> str:
        """
        Get MiniMax API base URL.
        Defaults to international endpoint: https://api.minimax.io/anthropic
        For China, set to: https://api.minimaxi.com/anthropic
        """
        return (
            api_base
            or get_secret_str("MINIMAX_API_BASE")
            or "https://api.minimax.io/anthropic/v1/messages"
        )

    def get_complete_url(
        self,
        api_base: Optional[str],
        api_key: Optional[str],
        model: str,
        optional_params: dict,
        litellm_params: dict,
        stream: Optional[bool] = None,
    ) -> str:
        """
        Get the complete URL for MiniMax API.
        Override to ensure we use MiniMax's endpoint, not Anthropic's.
        """
        # Get the base URL (either provided or default MiniMax endpoint)
        base_url = self.get_api_base(api_base=api_base)

        # If the base URL already includes the full path, return it
        if base_url.endswith("/v1/messages"):
            return base_url

        # Handle OpenAI-compatible base URL (e.g. https://api.minimax.io/v1)
        # by appending only /messages instead of /v1/messages
        if base_url.endswith("/v1"):
            return f"{base_url}/messages"

        # Otherwise append the messages endpoint
        if base_url.endswith("/"):
            return f"{base_url}v1/messages"
        else:
            return f"{base_url}/v1/messages"

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: list,
        anthropic_messages_optional_request_params: dict,
        litellm_params,
        headers: dict,
    ) -> dict:
        """
        Override to strip unsupported parameters before sending to MiniMax.
        MiniMax Anthropic endpoint doesn't support output_config (structured output).
        """
        # Remove output_config if present - MiniMax doesn't support it
        anthropic_messages_optional_request_params.pop("output_config", None)

        # Call parent to handle standard transformation
        return super().transform_anthropic_messages_request(
            model=model,
            messages=messages,
            anthropic_messages_optional_request_params=anthropic_messages_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
