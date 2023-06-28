import torch
import torch.nn as nn
import torch.nn.functional as F


class PositionalEncoding(nn.Module):
    def __init__(self, input_embedding_size, num_channels):
        super(PositionalEncoding, self).__init__()
        self.pos_encoding = torch.zeros(num_channels, input_embedding_size)
        position = torch.arange(0, num_channels, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, input_embedding_size, 2).float() * (
                -torch.log(torch.tensor(10000.0)) / input_embedding_size))
        self.pos_encoding[:, 0::2] = torch.sin(position * div_term)
        self.pos_encoding[:, 1::2] = torch.cos(position * div_term)
        self.pos_encoding = self.pos_encoding.unsqueeze(0)

    def forward(self, x):
        return x + self.pos_encoding[:, :x.size(1)].to(x.device)


class TransformerBlock(nn.Module):
    def __init__(self, input_embedding_size, num_heads, hidden_size, dropout):
        super(TransformerBlock, self).__init__()
        self.self_attn = nn.MultiheadAttention(embed_dim=input_embedding_size, num_heads=num_heads)
        self.norm1 = nn.LayerNorm(input_embedding_size)
        self.linear1 = nn.Linear(in_features=input_embedding_size, out_features=hidden_size)
        self.linear2 = nn.Linear(in_features=hidden_size, out_features=input_embedding_size)
        self.norm2 = nn.LayerNorm(input_embedding_size)
        self.dropout = nn.Dropout(p=dropout)
        self.silu = nn.SiLU()

    def forward(self, x):
        attn_output, _ = self.self_attn(x, x, x)
        x = x + self.dropout(attn_output)
        x = self.norm1(x + attn_output)
        ff_output = self.linear1(x)
        ff_output = self.linear2(ff_output)
        x = x + self.dropout(ff_output)
        x = self.norm2(x)
        x = self.silu(x)
        return x


class EEGTransformer(nn.Module):
    def __init__(self,
                 num_layers,
                 num_channels,
                 num_heads,
                 window_size,
                 input_embedding_size,
                 hidden_size,
                 dropout,
                 num_classes):
        super(EEGTransformer, self).__init__()
        self.input_embedding = nn.Linear(in_features=window_size, out_features=input_embedding_size)
        self.pos_encoding = PositionalEncoding(input_embedding_size=input_embedding_size, num_channels=num_channels)
        self.encoder = nn.ModuleList(
            [TransformerBlock(input_embedding_size=input_embedding_size,
                              num_heads=num_heads,
                              hidden_size=hidden_size,
                              dropout=dropout) for _ in range(num_layers)])
        self.convnet = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=40, kernel_size=(1, 20), stride=(1, 1)),
            nn.BatchNorm2d(num_features=40),
            nn.SiLU(),
            nn.Conv2d(in_channels=40, out_channels=40, kernel_size=(22, 1), stride=(1, 1)),
            nn.BatchNorm2d(num_features=40),
            nn.SiLU(),
            nn.AvgPool2d(kernel_size=(1, 30), stride=(1, 15)),
            nn.Dropout(p=dropout),
            nn.Conv2d(in_channels=40, out_channels=input_embedding_size, kernel_size=(1, 1), stride=(1, 1)),
            nn.Flatten(start_dim=2),
        )
        self.fc = nn.Sequential(
            nn.LayerNorm(normalized_shape=input_embedding_size),
            nn.Linear(in_features=input_embedding_size, out_features=num_classes),
        )
        for param in self.input_embedding.parameters():
            param.requires_grad = False

    def forward(self, x):
        # x = self.input_embedding(x)
        # x = self.pos_encoding(x)
        x = x.unsqueeze(dim=1)
        x = self.convnet(x)
        x = torch.transpose(input=x, dim0=1, dim1=2)
        for layer in self.encoder:
            x = layer(x)
        x = torch.mean(input=x, dim=1)
        x = self.fc(x)
        return x
