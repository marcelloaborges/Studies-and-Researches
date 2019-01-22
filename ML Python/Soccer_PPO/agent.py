import numpy as np

import torch
import torch.optim as optim
import torch.nn.functional as F
import torch.nn as nn

from model import ActorModel, CriticModel
from memory import Memory

from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler

class Agent:

    def __init__(
        self, 
        device,
        key,
        agent_type,
        actor_state_size,
        action_size,
        critic_state_size,
        lr,
        n_step,        
        batch_size,
        gamma,
        epsilon,
        entropy_weight,
        gradient_clip,
        checkpoint_folder
        ):

        self.DEVICE = device
        self.KEY = key
        self.TYPE = agent_type

        self.CHECKPOINT_ACTOR_FILE = checkpoint_folder + 'checkpoint_' + self.TYPE + '_' + str(self.KEY) + '.pth'
        self.CHECKPOINT_CRITIC_FILE = checkpoint_folder + 'checkpoint_critic_' + self.TYPE + '_' + str(self.KEY) + '.pth'

        # NEURAL MODEL
        self.actor_model = ActorModel( actor_state_size, action_size ).to(self.DEVICE)
        self.critic_model = CriticModel( critic_state_size ).to(self.DEVICE)
        self.optimizer = optim.Adam( list( self.actor_model.parameters() ) + list( self.critic_model.parameters() ), lr=lr )
        # self.optimizer = optim.RMSprop( list( self.actor_model.parameters() ) + list( self.critic_model.parameters() ), lr=lr, alpha=0.99, eps=1e-5 )

        self.actor_model.load(self.CHECKPOINT_ACTOR_FILE)
        self.critic_model.load(self.CHECKPOINT_CRITIC_FILE)

        # N_STEP MEMORY AND OPTIMIZER MEMORY        
        self.memory = Memory()        

        # HYPERPARAMETERS
        self.N_STEP = n_step        
        self.BATCH_SIZE = batch_size
        self.GAMMA = gamma
        self.GAMMA_N = gamma ** n_step
        self.EPSILON = epsilon
        self.ENTROPY_WEIGHT = entropy_weight
        self.GRADIENT_CLIP = gradient_clip        


        self.loss = 0

    def act(self, state):
        state = torch.from_numpy(state).float().unsqueeze(0).to(self.DEVICE)

        self.actor_model.eval()
        with torch.no_grad():                
            action, log_prob, _ = self.actor_model(state)                    
        self.actor_model.train()

        action = action.cpu().detach().numpy().item()
        log_prob = log_prob.cpu().detach().numpy().item()

        return action, log_prob

    def step(self, actor_state, critic_state, action, log_prob, reward):                
        self.memory.add( actor_state, critic_state, action, log_prob, reward )
        
    def optimize(self):            
        # LEARN
        actor_states, critic_states, actions, log_probs, rewards, n_exp = self.memory.experiences()


        discount = self.GAMMA**np.arange(n_exp)
        rewards = rewards.squeeze(1) * discount
        rewards_future = rewards[::-1].cumsum(axis=0)[::-1]


        actor_states = torch.from_numpy(actor_states).float().to(self.DEVICE)
        critic_states = torch.from_numpy(critic_states).float().to(self.DEVICE)
        actions = torch.from_numpy(actions).long().to(self.DEVICE).squeeze(1)
        log_probs = torch.from_numpy(log_probs).float().to(self.DEVICE).squeeze(1)
        rewards = torch.from_numpy(rewards_future.copy()).float().to(self.DEVICE)


        self.critic_model.eval()
        with torch.no_grad():
            values = self.critic_model( critic_states ).detach()
        self.critic_model.train()
                        
        advantages = (rewards - values.squeeze()).detach()
        advantages_normalized = (advantages - advantages.mean()) / (advantages.std() + 1.0e-10)
        advantages_normalized = torch.tensor(advantages_normalized).float().to(self.DEVICE)


        batches = BatchSampler( SubsetRandomSampler( range(0, n_exp) ), self.BATCH_SIZE, drop_last=False)

        for batch_indices in batches:
            batch_indices = torch.tensor(batch_indices).long().to(self.DEVICE)

            sampled_actor_states = actor_states[batch_indices]
            sampled_critic_states = critic_states[batch_indices]
            sampled_actions = actions[batch_indices]
            sampled_log_probs = log_probs[batch_indices]
            sampled_rewards = rewards[batch_indices]
            sampled_advantages = advantages_normalized[batch_indices]            


            _, new_log_probs, entropies = self.actor_model(sampled_actor_states, sampled_actions)


            ratio = ( new_log_probs - sampled_log_probs ).exp()

            clip = torch.clamp( ratio, 1 - self.EPSILON, 1 + self.EPSILON )

            policy_loss = torch.min( ratio * sampled_advantages, clip * sampled_advantages )
            policy_loss = - torch.mean( policy_loss )

            entropy = torch.mean(entropies)


            values = self.critic_model( sampled_critic_states )            
            value_loss = F.mse_loss( sampled_rewards, values.squeeze() )


            loss = policy_loss + (0.5 * value_loss) - (entropy * self.ENTROPY_WEIGHT)  


            self.optimizer.zero_grad()                  
            loss.backward()
            # nn.utils.clip_grad_norm_( self.actor_model.parameters(), self.GRADIENT_CLIP )
            # nn.utils.clip_grad_norm_( self.critic_model.parameters(), self.GRADIENT_CLIP )
            self.optimizer.step()


            self.loss = loss.data

        self.EPSILON *= 1
        self.ENTROPY_WEIGHT *= 0.995

        return self.loss

    def checkpoint(self):
        self.actor_model.checkpoint(self.CHECKPOINT_ACTOR_FILE)
        self.critic_model.checkpoint(self.CHECKPOINT_CRITIC_FILE)