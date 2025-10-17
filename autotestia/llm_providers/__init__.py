from .base import LLMProvider
from .openai_compatible import OpenAICompatibleProvider
from .google import GoogleProvider
from .anthropic import AnthropicProvider
# from .replicate import ReplicateProvider # Placeholder
from .. import config

def get_provider(
    provider_name: str = config.LLM_PROVIDER,
    model_name: str = config.GENERATOR_MODEL, # Default to generator
    api_keys: dict = None
) -> LLMProvider:
    """Factory function to get an instance of an LLM provider."""
    provider_name = provider_name.lower()
    
    if provider_name in ["openai", "openrouter", "ollama"]:
        return OpenAICompatibleProvider(provider=provider_name, model_name=model_name, api_keys=api_keys)
    elif provider_name == "google":
        return GoogleProvider(model_name=model_name, api_keys=api_keys)
    elif provider_name == "anthropic":
        return AnthropicProvider(model_name=model_name, api_keys=api_keys)
    # elif provider_name == "replicate":
    #     return ReplicateProvider(model_name=model_name, api_keys=api_keys)
    elif provider_name == "stub":
        # A stub provider can be a simple class that returns dummy data
        # For now, we can handle it here or create a StubProvider class.
        # Let's assume for now agents will handle the "stub" case directly if no client is returned.
        raise ValueError("Stub provider should be handled by the agent, not instantiated here.")
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}")
