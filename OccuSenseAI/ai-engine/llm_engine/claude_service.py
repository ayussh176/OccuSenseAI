import json
import httpx
from utils.logger import logger

class ClaudeService:
    def __init__(self):
        self.api_url = "https://api.anthropic.com/v1/messages"
        # In a real app we'd load this from config/settings.py
        self.api_key = "dummy_key_for_now" 
        
    async def generate_explanation(self, state: dict) -> str:
        """
        Generates a natural language explanation for why the HVAC should
        be adjusted based on the current environmental state and comfort score.
        """
        # For hackathon/demo purposes, if key is missing or dummy, we mock it
        if self.api_key == "dummy_key_for_now":
            temp = state.get("temperature_c", 22)
            co2 = state.get("co2_ppm", 400)
            if co2 > 800:
                return "CO2 levels are rising above comfortable levels. Recommending increased ventilation."
            elif temp > 24:
                return "Temperature is too warm for optimal comfort. Recommending cooling."
            return "Environment is within optimal parameters. No changes needed."
            
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        prompt = f"Analyze this environmental state: {json.dumps(state)}. What HVAC action should be taken and why?"
        
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    return data["content"][0]["text"]
                logger.error(f"Claude API Error: {response.text}")
        except Exception as e:
            logger.error(f"Failed to generate explanation: {e}")
            
        return "Explanation unavailable."

claude_service = ClaudeService()
