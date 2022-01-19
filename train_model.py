"""
Training model

Reference: https://github.com/piergiaj/pytorch-i3d
Edited by Shen Jie Koh
"""
#此程式為論文原作者程式修改而來
#可刪除RGB模式
#可以run，但要改loss function算法和重新架構程式

import os
os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"   
os.environ["CUDA_VISIBLE_DEVICES"]='1'
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-mode', type=str, help='rgb or depth')
parser.add_argument('-save_model', type=str)
parser.add_argument('-root', type=str)

args = parser.parse_args()

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.autograd import Variable
import torchvision

import numpy as np

from pytorch_i3d import InceptionI3d

from dataset import FloorDataset as Dataset

def run(init_lr=0.1, max_steps=64e3, mode='depth', root='', csv_file='', batch_size=1, save_model='testing'):
    # setup dataset
    if mode == 'depth':
        root = '../data/train'
        csv_file = 'csv_file/depth.csv'
    else:
        root = '../data/train' #後續需刪除RGB mode
        csv_file = 'csv_file/rgb.csv'
        
    dataset = Dataset(csv_file, root)
    train_set_size = int(len(dataset)*0.8)
    val_set_size = len(dataset) - train_set_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_set_size, val_set_size])
    
    train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_dataloader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=True)    

    dataloaders = {'train': train_dataloader, 'val': val_dataloader}
    datasets = {'train': train_dataset, 'val': val_dataset}

    # setup the model
    if mode == 'depth':
        i3d = InceptionI3d(14, in_channels=1)
        #i3d.load_state_dict(torch.load('models/flow_imagenet.pt'))
    else:
        i3d = InceptionI3d(14, in_channels=3)
        #i3d.load_state_dict(torch.load('models/rgb_imagenet.pt'))
    i3d.replace_logits(14)
    #i3d.load_state_dict(torch.load('/ssd/models/000920.pt'))
    i3d.cuda()
    i3d = nn.DataParallel(i3d)

    lr = init_lr
    optimizer = optim.SGD(i3d.parameters(), lr=lr, momentum=0.9, weight_decay=0.0000001)
    lr_sched = lr_scheduler.MultiStepLR(optimizer, [300, 1000])

    num_steps_per_update = 4 # accum gradient
    steps = 0
    # train it
    while steps < max_steps:#for epoch in range(num_epochs):
        print('Step {}/{}'.format(steps, max_steps))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                i3d.train(True)
            else:
                i3d.train(False)  # Set model to evaluate mode
                
            tot_loss = 0.0
            tot_loc_loss = 0.0
            tot_cls_loss = 0.0
            num_iter = 0
            optimizer.zero_grad()
            
            # Iterate over data.
            for data in dataloaders[phase]:
                num_iter += 1
                # get the inputs
                inputs, labels, path = data

                # wrap them in Variable
                inputs = Variable(inputs.cuda())
                #t = inputs.size(2)
                labels = Variable(labels.cuda())
                
                per_frame_logits = i3d(inputs)
               
                
                # upsample to input size
                #per_frame_logits = F.upsample(per_frame_logits, t, mode='linear')
                #print(per_frame_logits.size())
                #print(labels.size())

                # compute localization loss
                loc_loss = nn.CrossEntropyLoss(per_frame_logits, labels)
                #tot_loc_loss += loc_loss.data[0]
                tot_loc_loss += loc_loss.item()

                # compute classification loss (with max-pooling along time B x C x T)
                cls_loss = nn.CrossEntropyLoss(torch.max(per_frame_logits, dim=2)[0], torch.max(labels, dim=2)[0])
                #tot_cls_loss += cls_loss.data[0]
                tot_cls_loss += cls_loss.item()

                loss = (0.5*loc_loss + 0.5*cls_loss)/num_steps_per_update
                #tot_loss += loss.data[0]
                tot_loss += loss.item()
                loss.backward()

                if num_iter == num_steps_per_update and phase == 'train':
                    steps += 1
                    num_iter = 0
                    optimizer.step()
                    optimizer.zero_grad()
                    lr_sched.step()
                    if steps % 10 == 0:
                        print('{} Loc Loss: {:.4f} Cls Loss: {:.4f} Tot Loss: {:.4f}'.format(phase, tot_loc_loss/(10*num_steps_per_update), tot_cls_loss/(10*num_steps_per_update), tot_loss/10))
                        # save model
                        #torch.save(i3d.module.state_dict(), save_model+str(steps).zfill(6)+'.pt')
                        tot_loss = tot_loc_loss = tot_cls_loss = 0.
            if phase == 'val':
                print('{} Loc Loss: {:.4f} Cls Loss: {:.4f} Tot Loss: {:.4f}'.format(phase, tot_loc_loss/num_iter, tot_cls_loss/num_iter, (tot_loss*num_steps_per_update)/num_iter))
    


if __name__ == '__main__':
    # need to add argparse
    run(mode=args.mode, root=args.root, save_model=args.save_model)
