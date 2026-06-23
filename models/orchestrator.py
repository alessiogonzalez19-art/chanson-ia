"""
World-Class LLM Orchestrator
DeepSeek V3 / Qwen 2.5 72B / Mixtral 8x22B
"""

import gc
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TextStreamer
)
from typing import Dict, List, Optional, AsyncGenerator
from loguru import logger
import json

from config import config


class OrchestratorLLM:
    """GPT-4 class open-source LLM for music production orchestration"""
    
    def __init__(self, model_name: str = "deepseek_v3"):
        self.model_name = model_name
        self.model_config = config.WORLD_CLASS_MODELS[model_name]
        self.model = None
        self.tokenizer = None
        
    async def initialize(self):
        """Load the world-class LLM with optimal quantization"""
        logger.info(f"🚀 Loading {self.model_name}: {self.model_config['description']}")
        
        model_path = self.model_config["name"]
        
        # Configure quantization based on VRAM
        if config.use_4bit_quantization and self.model_config.get("requires_4bit", False):
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True
            )
            logger.info("📊 Using 4-bit quantization")
        else:
            quantization_config = None
            logger.info("📊 Using FP16 precision")
        
        # Load model with trust_remote_code for DeepSeek
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=quantization_config,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype=torch.float16 if not quantization_config else None
            )
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True
            )
            
            logger.info(f"✅ {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load {self.model_name}: {e}")
            logger.info("Falling back to Mixtral 8x22B...")
            await self._load_fallback()
    
    async def _load_fallback(self):
        """Load fallback model if primary fails"""
        # Select fallback based on available VRAM / Profile
        if getattr(config, 'orchestrator_model', '') in ['mistral_7b', 'mistral_7b_ollama'] or config.max_vram_usage_gb < 10:
            fallback = "qwen_1_5b"
            fallback_name = "Qwen/Qwen2.5-1.5B-Instruct"
            logger.info("⚠️ PC Standard detected. Falling back to Qwen2.5-1.5B-Instruct instead of Mixtral.")
        else:
            fallback = "mixtral_8x22b"
            fallback_name = config.WORLD_CLASS_MODELS[fallback]["name"]
            
        logger.info(f"🔄 Loading fallback model: {fallback_name}...")
        
        from transformers import BitsAndBytesConfig
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                fallback_name,
                device_map="auto",
                torch_dtype=torch.float16,
                quantization_config=quantization_config
            )
            self.tokenizer = AutoTokenizer.from_pretrained(fallback_name)
            self.model_name = fallback
            logger.info(f"✅ Fallback to {fallback_name} successful")
        except Exception as e:
            logger.error(f"❌ Fallback also failed: {e}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """Generate text with world-class LLM"""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Format according to model
        if "deepseek" in self.model_name.lower():
            # DeepSeek chat format
            formatted_prompt = self._format_deepseek(messages)
        elif "qwen" in self.model_name.lower():
            formatted_prompt = self._format_qwen(messages)
        else:
            # Mixtral format
            formatted_prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        
        inputs = self.tokenizer(formatted_prompt, return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
                top_p=0.95,
                top_k=50,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generation for real-time display"""
        full_response = await self.generate(prompt, **kwargs)
        # Compatibility wrapper for non-streaming backends: chunk the final text
        # instead of pretending we have token-level model streaming.
        chunk_size = 48
        for start in range(0, len(full_response), chunk_size):
            yield full_response[start:start + chunk_size]
    
    def _format_deepseek(self, messages: List[Dict]) -> str:
        """Format messages for DeepSeek V3"""
        formatted = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                formatted += f"System: {content}\n\n"
            elif role == "user":
                formatted += f"Human: {content}\n\n"
            elif role == "assistant":
                formatted += f"Assistant: {content}\n\n"
        formatted += "Assistant:"
        return formatted
    
    def _format_qwen(self, messages: List[Dict]) -> str:
        """Format messages for Qwen 2.5"""
        formatted = "<|im_start|>system\n"
        for msg in messages:
            if msg["role"] == "system":
                formatted += f"{msg['content']}<|im_end|>\n<|im_start|>user\n"
            elif msg["role"] == "user":
                formatted += f"{msg['content']}<|im_end|>\n<|im_start|>assistant\n"
        return formatted
    
    async def analyze_music_prompt(self, prompt: str) -> Dict:
        """Analyze a music production prompt and create detailed plan"""
        
        system_prompt = """You are a world-class music producer with expertise in:
- Music theory and composition
- Sound design and synthesis
- Mixing and mastering
- Genre conventions and innovations
- DAW production techniques

Analyze the user's prompt and create a detailed production plan in JSON format with:
{
    "genre": "primary genre",
    "subgenres": ["influences"],
    "bpm": tempo,
    "key": "musical key",
    "time_signature": "4/4",
    "mood": ["emotional descriptors"],
    "structure": {
        "intro": {"bars": 8, "description": "..."},
        "verse": {"bars": 16, "description": "..."},
        "chorus": {"bars": 16, "description": "..."},
        "bridge": {"bars": 8, "description": "..."},
        "outro": {"bars": 8, "description": "..."}
    },
    "instruments": [
        {"name": "instrument", "role": "melody/harmony/rhythm", "preset": "sound design"}
    ],
    "effects": ["reverb", "delay", "compression", "..."],
    "mixing_notes": "key mixing considerations",
    "mastering_target": "LUFS target and character"
}

Be specific, creative, and professional. Consider the entire production chain."""
        
        response = await self.generate(prompt, system_prompt, temperature=0.8)
        
        # Extract JSON from response
        try:
            # Find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM response")
        
        # Return default structure
        return {
            "genre": "electronic",
            "bpm": 128,
            "key": "C minor",
            "time_signature": "4/4",
            "mood": ["energetic", "dark"],
            "structure": {
                "intro": {"bars": 8, "description": "Atmospheric build-up"},
                "verse": {"bars": 16, "description": "Main groove"},
                "chorus": {"bars": 16, "description": "Full intensity"},
                "outro": {"bars": 8, "description": "Gradual fade"}
            }
        }
    
    def cleanup(self):
        """Free VRAM"""
        if self.model:
            del self.model
            self.model = None
        if self.tokenizer:
            del self.tokenizer
            self.tokenizer = None
        torch.cuda.empty_cache()
        gc.collect()
