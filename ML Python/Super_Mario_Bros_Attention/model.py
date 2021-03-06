import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

import torch.optim as optim

def layer_init(layer, w_scale=1.0):
    nn.init.orthogonal_(layer.weight.data)
    layer.weight.data.mul_(w_scale)
    nn.init.constant_(layer.bias.data, 0)
    return layer

def kaiming_layer_init(layer, mode='fan_out', nonlinearity='relu'):
    nn.init.kaiming_normal_(layer.weight, mode='fan_out', nonlinearity='relu')
    return layer

def kaiming_weight_init(weight, mode='fan_out', nonlinearity='relu'):
    nn.init.kaiming_normal_(weight, mode='fan_out', nonlinearity='relu')
    return weight

class AttentionEncoderModel(nn.Module):

    def __init__(self, seq_len, 
        attention_heads, n_attention_blocks, 
        img_h, img_w,         
        fc1_units=4096, fc2_units=3072, fc3_units=2048, fc4_units=1024,
        attention_size=256,
        attention_embedding=256, 
        device='cpu'):
        super(AttentionEncoderModel, self).__init__()

        self.DEVICE = device        

        self.seq_len = seq_len
        self.attention_heads = attention_heads
        self.n_attention_blocks = n_attention_blocks        
        self.attention_size = attention_size # base 64 / attention heads must be integer and even
        self.attention_embedding = attention_embedding

        # FLATTEN IMG EMBEDDING
        self.conv1 = nn.Conv2d(in_channels=3, out_channels=16, kernel_size=4, stride=2, padding=1)
        self.conv2 = nn.Conv2d(in_channels=16, out_channels=16, kernel_size=4, stride=2, padding=1)
        self.conv3 = nn.Conv2d(in_channels=16, out_channels=16, kernel_size=4, stride=2, padding=1)
        
        self.flatten_size = 16 * 12 * 15

        # MLP (CUSTOM CONV1d)
        self.pre_enconding_w, self.pre_encoding_baias =\
            self._generate_w_bias(self.flatten_size, self.attention_size )        

        # POSITIONAL
        self.positional_w =\
            kaiming_weight_init( 
                nn.Parameter( 
                    torch.rand( 
                        (1, 
                        self.seq_len, 
                        self.attention_size), 
                        requires_grad=True 
                        ).to(self.DEVICE)
                    ) 
                )

        self.dropout = nn.Dropout(.2)

        # Attention Block
        self.attention_blocks = []

        for _ in range( self.n_attention_blocks ):
            self.attention_blocks.append( self._generate_attention_block( self.flatten_size, self.attention_size ) )
        
        # ENCODING OUTPUT
        self.embedding_conv_w, self.embedding_conv_baias =\
            self._generate_w_bias( self.attention_size, self.attention_embedding )

    def _generate_attention_block(self, input_size, attention_size):        
        encoding_norm = nn.LayerNorm( self.attention_size ).to(self.DEVICE)

        encoding_w, encoding_baias = self._generate_w_bias( attention_size, attention_size * 3 )
        merging_w, merging_baias = self._generate_w_bias( attention_size, attention_size )

        residual_norm = nn.LayerNorm( self.attention_size ).to(self.DEVICE)

        residual_w1, residual_baias1 = self._generate_w_bias( attention_size, attention_size * 4 )
        residual_w2, residual_baias2 = self._generate_w_bias( attention_size * 4, attention_size )

        dropout = nn.Dropout( .2 )

        block = {
            'encoding_norm': encoding_norm,

            'encoding_w': encoding_w,
            'encoding_baias': encoding_baias,            
            'merging_w': merging_w,
            'merging_baias': merging_baias,

            'residual_norm': residual_norm,

            'residual_w1': residual_w1,
            'residual_baias1': residual_baias1,
            'residual_w2': residual_w2,
            'residual_baias2': residual_baias2,

            'dropout': dropout
        }

        return block

    def _generate_w_bias(self, input_size, attention_size):
        
        # WEIGHTS
        w = kaiming_weight_init( 
            nn.Parameter( 
                torch.rand( 
                    (1, 
                    input_size, 
                    attention_size), 
                    requires_grad=True 
                    ).to(self.DEVICE)
                ) 
            )
        
        # BAIAS
        b = torch.zeros( attention_size, requires_grad=True ).to(self.DEVICE)

        return w, b

    def _custom_conv1(self, x, w, b):
        dims_x = x.shape
        dims_w = w.shape

        # RESHAPE FOR MLP FORWARD [ BATCH * SEQ, FEATURES ]
        xs = x.view( dims_x[0] * dims_x[1], dims_x[2] )

        # [ INPUT, OUTPUT ] => ITEM_FEATURES * 3  >FORWARD> ITEM_FEATURES * 3 * ATTENTION_HEADS
        wm = w.view( -1, dims_w[-1] )

        xs_ws = (xs @ wm) + b # MATRIZ MULTIPLICATION => input * weights + baias

        # RESHAPE FOR OUTPUT [ BATCH, SEQ, FEATURES ]
        x_out = xs_ws.view( dims_x[0], dims_x[1], dims_w[-1] )

        return x_out

    def _custom_conv2(self, x, w, b):
        
        dims_x = x.shape
        dims_w = w.shape

        xc = x.view( dims_x[0] * dims_x[1], dims_x[2], dims_x[3], dims_x[4] )

        xc = self.conv1( xc )
        xc = F.relu( xc )
        xc = self.pool1( xc )
                
        xc = self.conv2( xc )
        xc = F.relu( xc )
        xc = self.pool2( xc )

        xc = self.conv3( xc )
        xc = F.relu( xc )
        xc = self.pool3( xc )

        xc = xc.view( -1, self.flatten_size )        

        # RESHAPE FOR MLP FORWARD [ BATCH * SEQ, FEATURES ]
        # xs = x.view( dims_x[0] * dims_x[1], dims_x[2] )
        xs = xc

        # [ INPUT, OUTPUT ] => ITEM_FEATURES * 3  >FORWARD> ITEM_FEATURES * 3 * ATTENTION_HEADS
        wm = w.view( -1, dims_w[-1] )

        xs_ws = (xs @ wm) + b # MATRIZ MULTIPLICATION => input * weights + baias

        # RESHAPE FOR OUTPUT [ BATCH, SEQ, FEATURES ]
        x_out = xs_ws.view( dims_x[0], dims_x[1], dims_w[-1] )

        return x_out

    def forward(self, state, dropout=True):
        
        x = state
        dims_x = x.shape
        
        # IMG FLATTEN
        x = x.view( dims_x[0] * dims_x[1], dims_x[2], dims_x[3], dims_x[4] )
                
        x = self.conv1( x )
        x = F.relu( x )
        x = self.conv2( x )
        x = F.relu( x )
        x = self.conv3( x )
        x = F.relu( x )

        # [ BATCH, SEQ(N_ITEMS), FEATURES ]        
        x = x.view( dims_x[0], dims_x[1], self.flatten_size )

        # GPT 2
        
        # [ BATCH, SEQ(N_ITEMS), FEATURES X HEADS ]        
        x = self._custom_conv1( x, self.pre_enconding_w, self.pre_encoding_baias )

        # POSITIONAL SEQxFEATURES_CONV + WP
        x = x + self.positional_w

        if dropout:
            x = self.dropout( x )

        # ATTENTION
        for block in self.attention_blocks:
            # ATTENTION REQUIRES NORM        
            x_norm = block['encoding_norm']( x )

            c = self._custom_conv1( x_norm, block['encoding_w'], block['encoding_baias'] )

            Q, K, V = c.split( self.attention_size, dim=2 )        

            Q = Q.view( -1, dims_x[1], self.attention_heads, self.attention_size // self.attention_heads )
            K = K.view( -1, dims_x[1], self.attention_heads, self.attention_size // self.attention_heads )
            V = V.view( -1, dims_x[1], self.attention_heads, self.attention_size // self.attention_heads )

            Q = Q.transpose( 2, 1 )
            K = K.transpose( 2, 1 )
            V = V.transpose( 2, 1 )
        
            # ATTENTION CALC
            w = Q @ K.transpose( 3, 2 )
            w = w * torch.rsqrt( torch.tensor( V.shape[-1] ).float() )

            # MASK
            i = torch.arange( w.shape[2] ).view(-1, 1).to(self.DEVICE)
            j = torch.arange( w.shape[3] ).to(self.DEVICE)
            m = (i >= j - w.shape[2] + w.shape[3]).float()
            m = m.view(1, 1, m.shape[0], m.shape[1])

            # APPLYING MASK
            w = w * m - 1e10 * (1 - m)
            s = torch.softmax( w, dim=3 )

            # S = Q * K
            # S * V
            a = s @ V
            a = a.transpose( 1, 2 )
            a = a.reshape( -1, a.shape[1], a.shape[2] * a.shape[3] )

            # APPLYING ATTENTION TO THE INPUT
            x = x + a

            # END ATTENTION

            # POS ATTENTION NORM
            x = block['residual_norm']( x )

            # APPLYING RESIDUAL
            m = self._custom_conv1( x, block['residual_w1'], block['residual_baias1'] )
            m = F.gelu( m )
            m = self._custom_conv1( m, block['residual_w2'], block['residual_baias2'] )

            x = x + m

            if dropout:
                x = block['dropout']( x )

        # ENCODING OUTPUT
        encoded = self._custom_conv1( x, self.embedding_conv_w, self.embedding_conv_baias )
        
        encoded = ( encoded - encoded.mean() ) / encoded.std() + 1.0e-10

        return encoded

    def load(self, checkpoint, device:'cpu'):
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint, map_location={'cuda:0': device.type}))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)

class AttentionActionModel(nn.Module):

    def __init__(self, encoding_size, action_size, fc1_units=128, fc2_units=64, device='cpu'):
        super(AttentionActionModel, self).__init__()

        self.encoding_size = encoding_size
        self.action_size = action_size

        self.fc1 = layer_init( nn.Linear(encoding_size, fc1_units) )
        self.fc2 = layer_init( nn.Linear(fc1_units + action_size, fc2_units) )
        
        self.value = nn.Linear(fc2_units, 1)
        self.value.weight.data.uniform_(-3e-3, 3e-3)

    def forward(self, state, dist):
        
        x = self.fc1(state)
        x = F.relu( x )
        
        x = torch.cat( (x, dist), dim=2 )

        x = self.fc2( x )
        x = F.relu( x )

        x = self.value( x ) # reward        

        return x

    def load(self, checkpoint, device:'cpu'):
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint, map_location={'cuda:0': device.type}))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)

class DQNModel(nn.Module):

    def __init__(self, state_size, action_size, fc1_units=256, fc2_units=128, fc3_units=64, fc4_units=32):
        super(DQNModel, self).__init__() 

        self.fc1 = layer_init( nn.Linear(state_size, fc1_units) )
        self.fc2 = layer_init( nn.Linear(fc1_units, fc2_units) )
        self.fc3 = layer_init( nn.Linear(fc2_units, fc3_units) )
        self.fc4 = layer_init( nn.Linear(fc3_units, fc4_units) )

        self.dropout = nn.Dropout(.25)

        self.fc_action = layer_init( nn.Linear(fc4_units, action_size) )

    def forward(self, state):

        x = self.dropout(state)

        x = F.relu( self.fc1(x) )
        x = F.relu( self.fc2(x) )
        x = F.relu( self.fc3(x) )
        x = F.relu( self.fc4(x) )

        x = self.fc_action(x)

        return x

    def load(self, checkpoint, device:'cpu'):
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint, map_location={'cuda:0': device.type}))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)

class ActorModel(nn.Module):

    def __init__(self, encoding_size, action_size, fc1_units=128, fc2_units=64, device='cpu'):
        super(ActorModel, self).__init__() 

        self.encoding_size = encoding_size
        self.action_size = action_size

        self.fc1 = layer_init( nn.Linear(encoding_size, fc1_units) )
        self.fc2 = layer_init( nn.Linear(fc1_units, fc2_units) )
        
        self.fc_action = layer_init( nn.Linear(fc2_units, action_size) )
        self.fc_action.weight.data.uniform_(-3e-3, 3e-3)

    def forward(self, state):
        x = self.fc1(state)
        x = F.relu( x )

        x = self.fc2( x )
        x = F.relu( x )

        x = self.fc_action( x )

        # action dist
        x = ( x - x.mean() ) / x.std() + 1.0e-10

        return x

    def load(self, checkpoint, device:'cpu'):
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint, map_location={'cuda:0': device.type}))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)

class CriticModel(nn.Module):

    def __init__(self, encoding_size, action_size, fc1_units=128, fc2_units=64, device='cpu'):
        super(CriticModel, self).__init__() 
        
        self.encoding_size = encoding_size
        self.action_size = action_size 

        self.fc1 = layer_init( nn.Linear(encoding_size, fc1_units) )
        self.fc2 = layer_init( nn.Linear(fc1_units + action_size, fc2_units) )
        
        self.fc_value = layer_init( nn.Linear(fc2_units, 1) )
        self.fc_value.weight.data.uniform_(-3e-3, 3e-3)

    def forward(self, state, dist):
        x = self.fc1(state)
        x = F.relu( x )

        x = torch.cat( (x, dist), dim=1 )

        x = self.fc2( x )
        x = F.relu( x )

        x = self.fc_value( x )

        # action dist
        # x = ( x - x.mean() ) / x.std() + 1.0e-10

        return x

    def load(self, checkpoint, device:'cpu'):
        if os.path.isfile(checkpoint):
            self.load_state_dict(torch.load(checkpoint, map_location={'cuda:0': device.type}))

    def checkpoint(self, checkpoint):
        torch.save(self.state_dict(), checkpoint)