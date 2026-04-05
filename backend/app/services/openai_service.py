from .llm_service import LLMService, strip_think_blocks


OpenAIService = LLMService

__all__ = ["LLMService", "OpenAIService", "strip_think_blocks"]
