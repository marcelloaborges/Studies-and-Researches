import numpy as np
import os

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

def hidden_init(layer):
    fan_in = layer.weight.data.size()[0]
    lim = 1. / np.sqrt(fan_in)
    return (-lim, lim)

def init_weights(layer):
    if type(layer) == nn.Linear:
        nn.init.xavier_uniform_(layer.weight)
        layer.bias.data.fill_(0.01)

def layer_init(layer, w_scale=1.0):
    nn.init.orthogonal_(layer.weight.data)
    layer.weight.data.mul_(w_scale)
    nn.init.constant_(layer.bias.data, 0)

class Model(nn.Module):
    def __init__(self, state_size, action_size, fc1_units=256, fc2_units=128):        
        super(Model, self).__init__()        
        self.fc1 = nn.Linear(state_size, fc1_units)
        self.fc2 = nn.Linear(fc1_units, fc2_units)
        self.fc_prob = nn.Linear(fc2_units, action_size)
        self.fc_value = nn.Linear(fc2_units, 1)
        
        # self.bn1 = nn.BatchNorm1d(num_features=state_size)

        layer_init(self.fc1)
        layer_init(self.fc2)
        layer_init(self.fc_prob)
        layer_init(self.fc_value)

    def forward(self, state, action=None):   
        # x = self.bn1(state)     
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        
        x_prob = F.softmax( self.fc_prob(x), dim=1 )
        x_value = self.fc_value(x)
                
        dist = Categorical(logits=x_prob)

        if action is None:
            action = dist.sample().unsqueeze(1)
                        
        log_prob = dist.log_prob(action)
        entropy = dist.entropy()

        value = x_value

        return action, log_prob, entropy, value

    def load(self, checkpoint):        
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)