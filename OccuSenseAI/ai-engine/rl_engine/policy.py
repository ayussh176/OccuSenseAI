from typing import Dict, Tuple
import numpy as np
from utils.logger import logger

class RLPolicyAgent:
    """
    Reinforcement Learning agent using Q-Learning to optimize HVAC.
    Learns to balance comfort scores against energy usage.
    """
    def __init__(self, learning_rate=0.1, discount_factor=0.9, exploration_rate=1.0):
        self.q_table: Dict[str, np.ndarray] = {}
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        
        # Actions: 0=Off, 1=Low, 2=Med, 3=High
        self.action_space_size = 4
        
    def _get_state_key(self, temp: float, co2: float, occupancy: int) -> str:
        # Discretize continuous state spaces
        temp_bin = int(temp)
        co2_bin = int(co2 / 100) * 100
        occ_bin = min(occupancy, 50) # Cap at 50
        return f"{temp_bin}_{co2_bin}_{occ_bin}"
        
    def get_action(self, state: dict, inference_only: bool = False) -> int:
        state_key = self._get_state_key(
            state.get("temperature_c", 22.0),
            state.get("co2_ppm", 400.0),
            state.get("estimated_count", 0)
        )
        
        if state_key not in self.q_table:
            self.q_table[state_key] = np.zeros(self.action_space_size)
            
        # Epsilon-greedy strategy
        if not inference_only and np.random.rand() < self.epsilon:
            return np.random.randint(self.action_space_size)
            
        return int(np.argmax(self.q_table[state_key]))
        
    def update(self, state: dict, action: int, reward: float, next_state: dict):
        state_key = self._get_state_key(
            state.get("temperature_c", 22.0),
            state.get("co2_ppm", 400.0),
            state.get("estimated_count", 0)
        )
        next_state_key = self._get_state_key(
            next_state.get("temperature_c", 22.0),
            next_state.get("co2_ppm", 400.0),
            next_state.get("estimated_count", 0)
        )
        
        if state_key not in self.q_table:
            self.q_table[state_key] = np.zeros(self.action_space_size)
        if next_state_key not in self.q_table:
            self.q_table[next_state_key] = np.zeros(self.action_space_size)
            
        # Q-learning update rule
        old_value = self.q_table[state_key][action]
        next_max = np.max(self.q_table[next_state_key])
        
        new_value = (1 - self.lr) * old_value + self.lr * (reward + self.gamma * next_max)
        self.q_table[state_key][action] = new_value
        
        # Decay exploration
        self.epsilon = max(0.01, self.epsilon * 0.995)

rl_agent = RLPolicyAgent()
