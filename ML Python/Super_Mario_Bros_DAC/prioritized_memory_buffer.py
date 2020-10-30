import numpy as np
from collections import deque
import random

class PrioritizedMemoryBuffer():
    def __init__(self, buffer_size):
        self.BUFFER_SIZE = buffer_size        

        self.memory = deque(maxlen=buffer_size)
        self.priorities = deque(maxlen=buffer_size)
        
    def add(self, state, action, reward, next_state, done):
        """Add a new experience to memory."""
        e = {
            "states" : state,
            "actions" : action,
            "rewards" : reward,
            "next_states" : next_state,
            "dones" : done,
        }

        self.memory.append(e)
        self.priorities.append(max(self.priorities, default=1))
        
    def _get_probabilities(self, priority_scale):
        scaled_priorities = np.array(self.priorities) ** priority_scale
        sample_probabilities = scaled_priorities / sum(scaled_priorities)

        return sample_probabilities
    
    def _get_importance(self, probabilities):
        importance = 1/len(self.memory) * 1/probabilities
        importance_normalized = importance / max(importance)

        return importance_normalized
        
    def enougth_samples(self, batch_size):
        return len( self.memory ) >= batch_size

    def sample(self, batch_size, priority_scale=1.0):
        
        # sample_size = min(len(self.memory), self.BATCH_SIZE)
        sample_probs = self._get_probabilities(priority_scale)
        sample_indices = random.choices( range( len(self.memory) ), k=batch_size, weights=sample_probs)
        samples = np.array( self.memory )[sample_indices]
        importances = self._get_importance( sample_probs[sample_indices] )

        states      = []
        actions     = []
        rewards     = []
        next_states = []
        dones       = []

        for exp in samples:                        
            states.append     ( exp['states']      )           
            actions.append    ( exp['actions']     )
            rewards.append    ( exp['rewards']     )
            next_states.append( exp['next_states'] )
            dones.append      ( exp['dones']       )

        states      = np.array(states)
        actions     = np.array(actions)
        rewards     = np.array(rewards)
        next_states = np.array(next_states)
        dones       = np.array(dones)
        importances = np.array(importances)

        return states, actions, rewards, next_states, dones, importances, sample_indices
    
    def set_priorities(self, indices, errors, offset=0.1):
        for i, e in zip(indices, errors):
            self.priorities[i] = abs(e) + offset

    def __len__(self):    
        return len(self.memory)