import torch
import bdb, traceback, pdb
import importlib
import argparse
from pathlib import Path
from utils import exp
import numpy as np
from tqdm import tqdm
from dataset.base import DatasetSpec


def visualize(test_result, data):
    try:
        import open3d as o3d
    except ImportError:
        print("Please import open3d for visualization!")
        exit()

    for (view_i, view_j) in test_result.keys():
        pc_i = data[DatasetSpec.PC][view_i][0].cpu().numpy()
        pc_j = data[DatasetSpec.PC][view_j][0].cpu().numpy()
        flow_ij = test_result[(view_i, view_j)].cpu().numpy()

        base_pcd = o3d.geometry.PointCloud()
        base_pcd.points = o3d.utility.Vector3dVector(pc_i)
        base_pcd.paint_uniform_color((1.0, 0., 0.))

        final_pcd = o3d.geometry.PointCloud()
        final_pcd.points = o3d.utility.Vector3dVector(pc_i + flow_ij)
        final_pcd.paint_uniform_color((0., 1.0, 0.))

        dest_pcd = o3d.geometry.PointCloud()
        dest_pcd.points = o3d.utility.Vector3dVector(pc_j)
        dest_pcd.paint_uniform_color((0., 0., 1.0))

        corres_lineset = o3d.geometry.LineSet(
            points=o3d.utility.Vector3dVector(np.vstack([pc_i, pc_i + flow_ij])),
            lines=o3d.utility.Vector2iVector(np.arange(2 * flow_ij.shape[0]).reshape((2, -1)).T))

        print(f"Visualizing scene flow computed from view {view_i} to view {view_j}.")
        o3d.visualization.draw([base_pcd, final_pcd, dest_pcd, corres_lineset])


def test_epoch():
    net_model.eval()
    net_model.hparams.is_training = False

    pbar = tqdm(test_loader, desc='Test')
    meter = exp.AverageMeter()
    for batch_idx, data in enumerate(pbar):
        data = exp.to_target_device(data, args.device)
        with torch.no_grad():
            test_result, test_metric = net_model.test_step(data, batch_idx)

        if args.visualize:
            visualize(test_result, data)

        meter.append_loss(test_metric)

    return meter


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Anisym Evaluation script')
    parser.add_argument('config', type=str, help='Path to the config file.')
    parser.add_argument('--device', type=str, choices=['cpu', 'cuda'], default='cuda', help='Device to run on.')
    parser.add_argument('--visualize', action='store_true', help='Whether or not to visualize.')
    args = parser.parse_args()

    exp.seed_everything(0)

    model_args = exp.parse_config_yaml(Path(args.config))
    net_module = importlib.import_module("models." + model_args.model).Model
    net_model = net_module(model_args)

    # Load dataset
    test_loader = net_model.test_dataloader()

    # Move to target device
    args.device = torch.device(args.device)
    net_model = exp.to_target_device(net_model, args.device)
    net_model.device = args.device
    net_model.update_device()

    # Run test
    try:
        test_meter = test_epoch()
    except Exception as ex:
        if not isinstance(ex, bdb.BdbQuit):
            traceback.print_exc()
            pdb.post_mortem(ex.__traceback__)
        exit()

    # Print metrics
    res = test_meter.get_mean_loss_dict()
    print("Test metrics:")
    print("+ Non-occluded:")
    print(f"  + EPE3D: \t {res[f'epe3d-avg'] * 100:.2f}\t+/-\t{res[f'epe3d-std'] * 100:.2f}")
    print(f"  + AccS (%): \t {res[f'acc3d_strict-avg'] * 100:.1f}\t+/-\t{res[f'acc3d_strict-std'] * 100:.1f}")
    print(f"  + AccR (%): \t {res[f'acc3d_relax-avg'] * 100:.1f}\t+/-\t{res[f'acc3d_relax-std'] * 100:.1f}")
    print(f"  + Outlier: \t {res[f'outlier-avg'] * 100:.1f}\t+/-\t{res[f'outlier-std'] * 100:.1f}")
    print("+ Full:")
    print(f"  + EPE3D: \t {res[f'epe3d-full-avg'] * 100:.2f}\t+/-\t{res[f'epe3d-full-std'] * 100:.2f}")
    print(f"  + AccS (%): \t {res[f'acc3d_strict-full-avg'] * 100:.1f}\t+/-\t{res[f'acc3d_strict-full-std'] * 100:.1f}")
    print(f"  + AccR (%): \t {res[f'acc3d_relax-full-avg'] * 100:.1f}\t+/-\t{res[f'acc3d_relax-full-std'] * 100:.1f}")
    print(f"  + Outlier: \t {res[f'outlier-full-avg'] * 100:.1f}\t+/-\t{res[f'outlier-full-std'] * 100:.1f}")
