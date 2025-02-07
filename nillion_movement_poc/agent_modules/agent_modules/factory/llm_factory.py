import os
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_core.callbacks import CallbackManager
from langchain_core.tracers import ConsoleCallbackHandler

from agent_modules.database.const.models import NILLION_MODEL, OPENAI_MODEL, AGENT_MODEL, GROQ_MODEL, ANTHROPIC_MODEL, DEEPSEEK_MODEL
from agent_modules.database.types.llm_config import LLMConfig

class LLMFactory:
    """Factory for creating LLM instances"""
    
    _providers = {
        "openai": (ChatOpenAI, OPENAI_MODEL),
        "anthropic": (ChatAnthropic, ANTHROPIC_MODEL),
        "groq": (ChatGroq, GROQ_MODEL),
        "ollama": (ChatOllama, AGENT_MODEL),
        "deepseek": (ChatOllama, DEEPSEEK_MODEL),
        "nillion": (ChatOpenAI, NILLION_MODEL)
    }

    @classmethod
    def create_llm(cls, provider: str, config: LLMConfig) -> BaseChatModel:
        llm_class, default_model = cls._providers.get(provider.lower(), cls._providers["groq"])
        model = config.model or default_model
        
        # Create a simple callback manager that won't cause tracing issues
        callback_manager = CallbackManager([ConsoleCallbackHandler()])
        
        kwargs = {
            "model": model,
            "temperature": config.temperature,
            "streaming": True,
            # "callback_manager": callback_manager # Disable for cleaner logs
        }

        if provider.lower() == "ollama":
            kwargs.update({
                "base_url": "http://localhost:11434",
                "format": "json",
                "callbacks": None  # Explicitly disable callbacks for Ollama
            })
        elif provider.lower() == "nillion":
            load_dotenv()
            kwargs.update({
                "openai_api_base": os.getenv("NILLION_API_URL"),
                "openai_api_key": os.getenv("NILLION_API_KEY"),
            })
            
        return llm_class(**kwargs)