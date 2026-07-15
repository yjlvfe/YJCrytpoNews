"""
YJCryptoNews v3.0 - Shared AI Client
Multi-provider LLM client with automatic fallback
"""
import logging
import os
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)


# Multi-provider chain (order = priority) - محسن للغة العربية
PROVIDER_CHAIN = [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_env": "GROQ_API_KEY",
        "models": {
            "translation": "allam-2-7b",          # Arabic-native model (الأولوية للعربي)
            "summarization": "llama-3.1-8b-instant",
            "enrichment": "llama-3.3-70b-versatile",
            "arabic_specialist": "allam-2-7b",
        },
        "max_tokens": {
            "translation": 4096,
            "summarization": 1024,
            "enrichment": 8192,
        },
        "temperature": {
            "translation": 0.15,  # أقل حرارة للترجمة الأدق
            "summarization": 0.1,
            "enrichment": 0.3,
        },
        "timeout": 30,
    },
    {
        "name": "groq_fallback",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_env": "GROQ_API_KEY",
        "models": {
            "translation": "llama-3.3-70b-versatile",  # احتياطي قوي
            "summarization": "llama-3.1-8b-instant",
            "enrichment": "llama-3.3-70b-versatile",
        },
        "max_tokens": {
            "translation": 4096,
            "summarization": 1024,
            "enrichment": 8192,
        },
        "temperature": {
            "translation": 0.2,
            "summarization": 0.1,
            "enrichment": 0.3,
        },
        "timeout": 30,
    },
    {
        "name": "nvidia_nim",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "api_key_env": "NVIDIA_API_KEY",
        "models": {
            "translation": "meta/llama-3.1-70b-instruct",
            "summarization": "meta/llama-3.1-8b-instruct",
            "enrichment": "nvidia/nemotron-3-ultra-550b-a55b",
        },
        "max_tokens": {
            "translation": 4096,
            "summarization": 1024,
            "enrichment": 8192,
        },
        "temperature": {
            "translation": 0.2,
            "summarization": 0.1,
            "enrichment": 0.3,
        },
        "timeout": 30,
    },
    {
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": {
            "translation": "deepseek/deepseek-chat",
            "summarization": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "enrichment": "deepseek/deepseek-chat",
        },
        "max_tokens": {
            "translation": 4096,
            "summarization": 1024,
            "enrichment": 8192,
        },
        "temperature": {
            "translation": 0.2,
            "summarization": 0.1,
            "enrichment": 0.3,
        },
        "timeout": 45,
    },
    {
        "name": "mistral",
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "api_key_env": "MISTRAL_API_KEY",
        "models": {
            "translation": "mistral-small-latest",
            "summarization": "open-mistral-nemo",
            "enrichment": "mistral-small-latest",
        },
        "max_tokens": {
            "translation": 4096,
            "summarization": 1024,
            "enrichment": 8192,
        },
        "temperature": {
            "translation": 0.2,
            "summarization": 0.1,
            "enrichment": 0.3,
        },
        "timeout": 60,
    },
]


class AIClient:
    """Multi-provider AI client with automatic fallback"""
    
    def __init__(self, task_type: str = "translation"):
        """
        Initialize client for a specific task type.
        task_type: 'translation', 'summarization', 'enrichment'
        """
        self.task_type = task_type
        self.providers = self._load_providers()
    
    def _load_providers(self) -> List[Dict[str, Any]]:
        """Load only providers with valid API keys and models for this task"""
        loaded = []
        for p in PROVIDER_CHAIN:
            api_key = os.getenv(p["api_key_env"])
            if api_key and self.task_type in p["models"]:
                p_copy = p.copy()
                p_copy["api_key"] = api_key
                p_copy["model"] = p["models"][self.task_type]
                p_copy["max_tokens"] = p["max_tokens"].get(self.task_type, 4096)
                p_copy["temperature"] = p["temperature"].get(self.task_type, 0.2)
                loaded.append(p_copy)
                logger.info(f"AI Provider loaded for {self.task_type}: {p['name']} ({p_copy['model']})")
            elif api_key:
                logger.warning(f"AI Provider {p['name']} has key but no model for {self.task_type}")
            else:
                logger.debug(f"AI Provider skipped (no key): {p['name']}")
        if not loaded:
            logger.error(f"NO AI PROVIDERS AVAILABLE for {self.task_type} - Check API keys in .env")
        return loaded
    
    def _build_headers(self, provider: Dict) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
    
    def _build_payload(self, provider: Dict, messages: List[Dict], system_prompt: Optional[str] = None) -> Dict:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        
        return {
            "model": provider["model"],
            "messages": msgs,
            "max_tokens": provider["max_tokens"],
            "temperature": provider["temperature"],
        }
    
    async def complete(self, 
                       messages: List[Dict], 
                       system_prompt: Optional[str] = None,
                       require_arabic: bool = False) -> Optional[Dict[str, Any]]:
        """
        Try completion with provider fallback.
        Returns result dict with 'content', 'provider', 'model' or None if all fail.
        """
        if not self.providers:
            logger.error(f"No providers available for {self.task_type}")
            return None
        
        for provider in self.providers:
            logger.debug(f"Trying {provider['name']} for {self.task_type}...")
            
            try:
                timeout = httpx.Timeout(provider["timeout"])
                payload = self._build_payload(provider, messages, system_prompt)
                headers = self._build_headers(provider)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(provider["base_url"], json=payload, headers=headers)
                    
                    # Check for rate limit errors
                    if response.status_code == 429:
                        logger.warning(f"{provider['name']} rate limited (429), trying next provider")
                        continue
                    
                    response.raise_for_status()
                    result = response.json()
                    content = result["choices"][0]["message"]["content"].strip()
                    
                    # Strict Arabic validation - reject CJK characters
                    if require_arabic:
                        has_arabic = any('\u0600' <= c <= '\u06FF' for c in content)
                        has_cjk = any(
                            '\u3400' <= c <= '\u4DBF' or  # CJK Extension A
                            '\u4E00' <= c <= '\u9FFF' or  # CJK Unified Ideographs
                            '\u3040' <= c <= '\u309F' or  # Hiragana
                            '\u30A0' <= c <= '\u30FF' or  # Katakana
                            '\uAC00' <= c <= '\uD7AF' or  # Hangul
                            '\uFF00' <= c <= '\uFFEF'     # Fullwidth forms
                            for c in content
                        )
                        
                        if not has_arabic:
                            logger.warning(f"{provider['name']}: No Arabic characters in response, skipping")
                            continue
                        
                        if has_cjk:
                            logger.warning(f"{provider['name']}: CJK characters detected in response, skipping")
                            continue
                        
                        # Additional: reject if mostly Latin (not Arabic)
                        arabic_count = sum(1 for c in content if '\u0600' <= c <= '\u06FF')
                        latin_count = sum(1 for c in content if c.isascii() and c.isalpha())
                        if latin_count > arabic_count * 2:
                            logger.warning(f"{provider['name']}: Too much Latin text ({latin_count} vs {arabic_count} Arabic), skipping")
                            continue
                    
                    logger.info(f"✅ {self.task_type} successful with {provider['name']} ({provider['model']})")
                    return {
                        "content": content,
                        "provider": provider["name"],
                        "model": provider["model"],
                    }
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"{provider['name']} rate limited (429): {e.response.text[:100]}")
                else:
                    logger.warning(f"{provider['name']} HTTP {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                logger.warning(f"{provider['name']} error: {e}")
        
        logger.error(f"ALL PROVIDERS FAILED for {self.task_type}")
        return None


# Convenience functions for backward compatibility
async def ai_complete(task_type: str, messages: List[Dict], **kwargs) -> Optional[Dict]:
    """Quick completion with default client"""
    client = AIClient(task_type)
    return await client.complete(messages, **kwargs)