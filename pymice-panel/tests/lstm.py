import torch
import torch.nn as nn
import torch.nn.functional as F
        
class ConvLSTMCell(nn.Module):
    def __init__(self, in_channels, hidden_channels, kernel_size, bias=True):
        super().__init__()
        
        padding = kernel_size//2
        self.hidden_channels = hidden_channels
        
        self.conv = nn.Conv2d(
            in_channels + hidden_channels,
            4 * hidden_channels,
            kernel_size,
            padding=padding,
            bias=bias
        )
        
    def forward(self, x, h, c):
        combined = torch.cat([x, h], dim=1)
        gates = self.conv(combined)
        
        i, f, o, g = torch.chunk(gates, 4, dim=1)
        
        i = torch.sigmoid(i)
        f = torch.sigmoid(f)
        o = torch.sigmoid(o)
        g = torch.tanh(g)
        
        c_next = f * c + i * g
        h_next = o * torch.tanh(c_next)
        
        return h_next, c_next
    
class ConvLSTM(nn.Module):
    def __init__(self, in_channels, hidden_channels, kernel_size, return_sequences=True):
        pass