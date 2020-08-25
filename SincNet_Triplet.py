
from Triplet_Net import *
from Triplet_DataLoader import Triplet_Time_Loader
from SincNet_dataio import ReadList, read_conf,str_to_bool
import wandb
import torch.utils.data as data
import torch.optim as optim
import time
from Metric_Losses import batch_hard_triplet_loss
import torch.backends.cudnn as cudnn

class AverageMeter:
    '''Computes and stores the average and current value'''
    def __init__(self):
        self.reset()

    def reset(self):
        self.valu = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val *n
        self.count += n
        self.avg = self.sum / self.count

def train(train_loader, SincNet_model, MLP_model, optimizer_SincNet, optimizer_MLP, epoch):
    MLP_model.train()
    SincNet_model.train()
    losses = AverageMeter()
    accuracy = AverageMeter()
    total_samples = 0
    for batch_idx, (tracks, int_labels, string_labels) in enumerate(train_loader):
        tracks, int_labels = tracks.cuda(), int_labels.cuda()
        #tracks, int_labels = tracks.cuda(), int_labels.cuda()
        embeddings = SincNet_model(tracks)
        embeddings = MLP_model(embeddings)
        loss, correct_negative, total = batch_hard_triplet_loss(int_labels, embeddings, margin_positive=2,
                                                                margin_negative=2, device='cuda',
                                                                squared=True)

        total_samples = total_samples + total
        accuracy.update((correct_negative/total)*100, 1)
        optimizer_SincNet.zero_grad()
        optimizer_MLP.zero_grad()
        loss.backward()
        optimizer_SincNet.step()
        optimizer_MLP.step()
        losses.update(loss, 1)
        if batch_idx % 64 == 0:
            print(' Train epoch: {} [{}/{}]\t Loss {:.4f} Acc {:.2f} \t '.format(epoch, batch_idx, len(train_loader.dataset), losses.avg, accuracy.avg), flush=True, end='\r')

def test(test_loader, SincNet_model, MLP_model,epoch):
    MLP_model.eval()
    SincNet_model.eval()
    total_samples = 0
    losses = AverageMeter()
    accuracy = AverageMeter()
    with torch.no_grad():
        for batch_idx, (tracks, int_labels, string_labels) in enumerate(test_loader):
            tracks, int_labels = tracks.cuda(), int_labels.cuda()
            embeddings = SincNet_model(embeddings)
            embeddings = MLP_model(embeddings)
            loss, correct_negative, total = batch_hard_triplet_loss(int_labels, embeddings, margin_negative=2, margin_positive=2,
                                                                    device='cuda', squared=True)
            total_samples = total_samples + total
            losses.update(loss, 1)
            accuracy.update((correct_negative/total)*100, 1)

    print('Test Epoch {}: Loss: {:.4f}, Accuracy {:.2f} \t'.format(epoch, losses.avg, accuracy.avg))





def main():
    #READ CONFIG FILE
    options = read_conf()

    #LOG ON WANDB?
    log = options.wandb
    project_name = options.project

    if log:
        wandb.init(project='SincNet_MetricLoss')
        wandb.run.name = project_name

    device = torch.device("cuda:0")

    kwargs = {'num_workers' : 8, 'pin_memory':True}

    #Get data path
    data_PATH = options.path
    sincnet_path = options.sincnet_path
    mlp_path = options.mlp_path

    train_loader = data.DataLoader(Triplet_Time_Loader(path=data_PATH, spectrogram=False, train=True), batch_size=64, shuffle=False, **kwargs)
    test_loader = data.DataLoader(Triplet_Time_Loader(path=data_PATH, spectrogram=False, train=False), batch_size=64, shuffle=False, **kwargs)

    #get parameters for SincNet and MLP
    #[cnn]
    # [cnn]
    cnn_N_filt = list(map(int, options.cnn_N_filt.split(',')))
    cnn_len_filt = list(map(int, options.cnn_len_filt.split(',')))
    cnn_max_pool_len = list(map(int, options.cnn_max_pool_len.split(',')))
    cnn_use_laynorm_inp = str_to_bool(options.cnn_use_laynorm_inp)
    cnn_use_batchnorm_inp = str_to_bool(options.cnn_use_batchnorm_inp)
    cnn_use_laynorm = list(map(str_to_bool, options.cnn_use_laynorm.split(',')))
    cnn_use_batchnorm = list(map(str_to_bool, options.cnn_use_batchnorm.split(',')))
    cnn_act = list(map(str, options.cnn_act.split(',')))
    cnn_drop = list(map(float, options.cnn_drop.split(',')))

    # [dnn]
    fc_lay = list(map(int, options.fc_lay.split(',')))
    fc_drop = list(map(float, options.fc_drop.split(',')))
    fc_use_laynorm_inp = str_to_bool(options.fc_use_laynorm_inp)
    fc_use_batchnorm_inp = str_to_bool(options.fc_use_batchnorm_inp)
    fc_use_batchnorm = list(map(str_to_bool, options.fc_use_batchnorm.split(',')))
    fc_use_laynorm = list(map(str_to_bool, options.fc_use_laynorm.split(',')))
    fc_act = list(map(str, options.fc_act.split(',')))

    # [optimization]
    lr = float(options.lr)
    batch_size = int(options.batch_size)
    N_epochs = int(options.N_epochs)
    N_batches = int(options.N_batches)
    N_eval_epoch = int(options.N_eval_epoch)
    seed = int(options.seed)
    torch.manual_seed(1234)

    SincNet_args = {'input_dim': 48000, #3 seconds at 16000Hz
                   'fs': 16000,
                   'cnn_N_filt': cnn_N_filt,
                   'cnn_len_filt': cnn_len_filt,
                   'cnn_max_pool_len': cnn_max_pool_len,
                   'cnn_use_laynorm_inp': cnn_use_laynorm_inp,
                   'cnn_use_batchnorm_inp': cnn_use_batchnorm_inp,
                   'cnn_use_laynorm': cnn_use_laynorm,
                   'cnn_use_batchnorm': cnn_use_batchnorm,
                   'cnn_act': cnn_act,
                   'cnn_drop': cnn_drop
                   }
    SincNet_model = SincNet(SincNet_args)
    SincNet_model.to(device)

    DNN1_args = {'input_dim': SincNet_model.out_dim,
                 'fc_lay': fc_lay,
                 'fc_drop': fc_drop,
                 'fc_use_batchnorm': fc_use_batchnorm,
                 'fc_use_laynorm': fc_use_laynorm,
                 'fc_use_laynorm_inp': fc_use_laynorm_inp,
                 'fc_use_batchnorm_inp': fc_use_batchnorm_inp,
                 'fc_act': fc_act}

    MLP_net = MLP(DNN1_args)
    MLP_net.to(device)

    try:
        SincNet_model.load_state_dict(sincnet_path)
        MLP_net.load_state_dict(mlp_path)
    except:
        print('Could not load models')


    optimizer_SincNet = optim.RMSprop(params=SincNet_model.parameters(), lr=lr, alpha=0.8, momentum=0.5)
    optimizer_MLP = optim.RMSprop(params=MLP_net.parameters(), lr=lr, alpha=0.8, momentum=0.5)

    cudnn.benchmark = True
    cudnn.enabled = True


    for epoch in range(1, N_epochs+1):
        start_time = time.time()
        train(epoch=epoch, train_loader=train_loader, SincNet_model=SincNet_model, MLP_model=MLP_net, optimizer_SincNet=optimizer_SincNet, optimizer_MLP=optimizer_MLP)
        duration = time.time() - start_time
        print("Done training epoch {} in {:.4f}".format(epoch, duration))
        test(test_loader=test_loader, SincNet_model=SincNet_model, MLP_model=MLP_net, epoch=epoch)
        if (epoch % 10) == 0:
            torch.save(SincNet_model.state_dict(), sincnet_path)
            torch.save(MLP_net.state_dict(), mlp_path)
            print("Model saved after {} epochs".format(epoch))




if __name__ == '__main__':
    main()