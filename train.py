import os
import torch
import torchvision
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils
import torch.optim as optim
import torchvision.transforms as standard_transforms

import numpy as np
import glob
import cv2

from data_loader import Rescale, RescaleT, RandomCrop, ToTensor, ToTensorLab, SalObjDataset
from model import UIUNET
from tqdm import tqdm  # tqdm import

if __name__ == '__main__':
    # ------- 1. define loss function --------
    bce_loss = nn.BCELoss(reduction='mean')

    def muti_bce_loss_fusion(d0, d1, d2, d3, d4, d5, d6, labels_v):
        loss0 = bce_loss(d0, labels_v)
        loss1 = bce_loss(d1, labels_v)
        loss2 = bce_loss(d2, labels_v)
        loss3 = bce_loss(d3, labels_v)
        loss4 = bce_loss(d4, labels_v)
        loss5 = bce_loss(d5, labels_v)
        loss6 = bce_loss(d6, labels_v)

        loss = loss0 + loss1 + loss2 + loss3 + loss4 + loss5 + loss6
        return loss0, loss

    # ------- 2. set the directory of training dataset --------
    model_name = 'uiunet'
    data_dir = "/home/jihong/UIU_datasets/datasets/data/archive/"
    tra_image_dir = "images/"
    tra_label_dir = "masks/"
    image_ext = '.jpg'
    label_ext = '.png'
    model_dir = os.path.join(os.getcwd(), 'saved_models', model_name + os.sep)

    epoch_num = 500
    batch_size_train = 80
    batch_size_val = 80
    train_num = 0
    val_num = 0

    tra_img_name_list = glob.glob(data_dir + tra_image_dir + '*' + image_ext)
    tra_lbl_name_list = glob.glob(data_dir + tra_label_dir + '*' + label_ext)

    print("---")
    print("train images: ", len(tra_img_name_list))
    print("train labels: ", len(tra_lbl_name_list))
    print("---")
    print("---")

    train_num = len(tra_img_name_list)

    salobj_dataset = SalObjDataset(
        img_name_list=tra_img_name_list,
        lbl_name_list=tra_lbl_name_list,
        transform=transforms.Compose([
            RescaleT(320),
            RandomCrop(288),
            ToTensorLab(flag=0)]))
    salobj_dataloader = DataLoader(salobj_dataset, batch_size=batch_size_train, shuffle=False, num_workers=4, drop_last=True)

    # ------- 3. define model --------
    net = UIUNET(3, 1)

    # 멀티 GPU 사용 설정
    if torch.cuda.device_count() > 1:
        print("Let's use", torch.cuda.device_count(), "GPUs!")
        net = nn.DataParallel(net)  # DataParallel로 모델을 감싸기

    # 모델을 GPU로 이동
    if torch.cuda.is_available():
        net = net.cuda()

    # ------- 4. define optimizer --------
    print("---define optimizer...")
    optimizer = optim.Adam(net.parameters(), lr=0.001, betas=(0.9, 0.999), eps=1e-08, weight_decay=0)

    # ------- 5. training process --------
    print("---start training...")
    ite_num = 0
    save_frq = 2000  # save the model every 2000 iterations

    for epoch in range(0, epoch_num):
        net.train()

        running_loss = 0.0
        running_tar_loss = 0.0
        ite_num4val = 0

        # tqdm으로 에포크 당 진행 바 시각화
        pbar = tqdm(total=len(salobj_dataloader), desc=f"Epoch {epoch + 1}/{epoch_num}")

        for i, data in enumerate(salobj_dataloader):
            ite_num += 1
            ite_num4val += 1

            inputs, labels = data['image'], data['label']
            inputs = inputs.type(torch.FloatTensor)
            labels = labels.type(torch.FloatTensor)

            # wrap them in Variable
            if torch.cuda.is_available():
                inputs_v, labels_v = Variable(inputs.cuda(), requires_grad=False), Variable(labels.cuda(), requires_grad=False)
            else:
                inputs_v, labels_v = Variable(inputs, requires_grad=False), Variable(labels, requires_grad=False)

            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            d0, d1, d2, d3, d4, d5, d6 = net(inputs_v)
            loss2, loss = muti_bce_loss_fusion(d0, d1, d2, d3, d4, d5, d6, labels_v)

            loss.backward()
            optimizer.step()

            # Update running loss
            running_loss += loss.item()
            running_tar_loss += loss2.item()

            # Update tqdm progress bar
            pbar.set_postfix({'train loss': running_loss / ite_num4val, 'tar loss': running_tar_loss / ite_num4val})
            pbar.update(1)

            # Save model at save frequency
            if ite_num % save_frq == 0:
                torch.save(net.state_dict(), model_dir + model_name + "_bce_itr_%d_train_%3f_tar_%3f.pth" % (ite_num, running_loss / ite_num4val, running_tar_loss / ite_num4val))
                running_loss = 0.0
                running_tar_loss = 0.0
                net.train()  # resume train
                ite_num4val = 0

        pbar.close()

        print(f"Epoch [{epoch + 1}/{epoch_num}] complete: train loss: {running_loss / len(salobj_dataloader):.3f}, tar loss: {running_tar_loss / len(salobj_dataloader):.3f}")
