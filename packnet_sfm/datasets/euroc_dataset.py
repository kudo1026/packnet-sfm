
import re
from collections import defaultdict
import os

from PIL import Image
from torch.utils.data import Dataset
import numpy as np
from packnet_sfm.utils.image import load_image

########################################################################################################################
#### FUNCTIONS
########################################################################################################################

def dummy_calibration(image):
    w, h = [float(d) for d in image.size]
    return np.array([[1000. , 0.    , w / 2. - 0.5],
                     [0.    , 1000. , h / 2. - 0.5],
                     [0.    , 0.    , 1.          ]])

def get_idx(filename):
    return int(re.search(r'\d+', filename).group())

########################################################################################################################
#### DATASET
########################################################################################################################

class EUROCDataset(Dataset):
    def __init__(self, root_dir, split, data_transform=None,
                 forward_context=0, back_context=0, strides=(1,),
                 depth_type=None, cameras=[], **kwargs):
        super().__init__()
        # Asserts
        # assert depth_type is None or depth_type == '', \
        #     'ImageDataset currently does not support depth types'
        assert len(strides) == 1 and strides[0] == 1, \
            'ImageDataset currently only supports stride of 1.'

        self.root_dir = root_dir
        self.split = split

        self.cameras = cameras

        self.backward_context = back_context
        self.forward_context = forward_context
        self.has_context = self.backward_context + self.forward_context > 0
        self.strides = 1

        self.files = []
        self.file_tree = defaultdict(list)
        self.read_files(root_dir)

        self.depth_type = depth_type
        self.with_depth = depth_type is not '' and depth_type is not None

        # print('file tree')
        # print(self.file_tree)

        for k, v in self.file_tree.items():
            file_set = set(self.file_tree[k])
            files = [fname for fname in sorted(v) if self._has_context(fname, file_set)]
            # files = [fname for fname in sorted(v)]
            self.files.extend([[k, fname] for fname in files])

        self.data_transform = data_transform

    def read_files(self, directory, ext=('.png', '.jpg', '.jpeg'), skip_empty=True):
        files = defaultdict(list)
        for entry in os.scandir(directory):
            relpath = os.path.relpath(entry.path, directory)
            if entry.is_dir():
                d_files = self.read_files(entry.path, ext=ext, skip_empty=skip_empty)
                if skip_empty and not len(d_files):
                    continue
                # files[relpath] = d_files[entry.path]
                self.file_tree[entry.path] = d_files[entry.path]
            elif entry.is_file():
                if ext is None or entry.path.lower().endswith(tuple(ext)):
                    files[directory].append(relpath)
        return files

    def __len__(self):
        return len(self.files)

    def _change_idx(self, idx, filename):
        _, ext = os.path.splitext(os.path.basename(filename))
        return self.split.format(idx) + ext

    def _has_context(self, filename, file_set):
        context_paths = self._get_context_file_paths(filename, file_set)

        return all([f in file_set for f in context_paths])

    def _get_context_file_paths(self, filename, file_set):
        fidx = get_idx(filename)
        # a hacky way to deal with two different strides in euroc dataset
        idxs = [-self.backward_context, -self.forward_context, self.backward_context, self.forward_context]
        potential_files = [self._change_idx(fidx + i, filename) for i in idxs]
        valid_paths = [fname for fname in potential_files if fname in file_set]

        # return [self._change_idx(fidx + i, filename) for i in idxs]
        return valid_paths

    def _read_rgb_context_files(self, session, filename):
        file_set = set(self.file_tree[session])
        context_paths = self._get_context_file_paths(filename, file_set)

        return [self._read_rgb_file(session, filename) for filename in context_paths]


    def _read_rgb_file(self, session, filename):

        gray_image = load_image(os.path.join(self.root_dir, session, filename))
        gray_image_np = np.array(gray_image)
        rgb_image_np = np.stack([gray_image_np for _ in range(3)], axis=2)
        rgb_image = Image.fromarray(rgb_image_np)
        
        return rgb_image

    def _read_npy_depth(self, session, depth_filename):
        depth_file_path = os.path.join(self.root_dir, session, '../../depth_maps', depth_filename)
        return np.load(depth_file_path)

    def _read_depth(self, session, depth_filename):
        """Get the depth map from a file."""
        if self.depth_type in ['vicon']:
            return self._read_npy_depth(session, depth_filename)
        else:
            raise NotImplementedError(
                'Depth type {} not implemented'.format(self.depth_type))

    def _has_depth(self, session, depth_filename):
        depth_file_path = os.path.join(self.root_dir, session, '../../depth_maps', depth_filename)

        return os.path.isfile(depth_file_path)

    def __getitem__(self, idx):
        session, filename = self.files[idx]
        image = self._read_rgb_file(session, filename)

        intrinsic_type = 'euroc' if len(self.cameras) == 0 else 'euroc_{}'.format(self.cameras[0])

        sample = {
            'idx': idx,
            'filename': '%s_%s' % (session, os.path.splitext(filename)[0]),
            'rgb': image,
            'intrinsics': dummy_calibration(image),
            'intrinsic_type': intrinsic_type
        }

        if self.has_context:
            sample['rgb_context'] = \
                self._read_rgb_context_files(session, filename)

        depth_filename = filename.split('.')[0] + 'depth.npy'
        if self.with_depth:
            if self._has_depth(session, depth_filename):
                sample['depth'] = self._read_depth(session, depth_filename)


        if self.data_transform:
            sample = self.data_transform(sample)

        return sample

########################################################################################################################
if __name__ == "__main__":
    data_dir = '/data/datasets/euroc/V1_01_easy_has_depth/mav0'
    euroc_dataset = EUROCDataset(root_dir=data_dir,split='{:09}',depth_type='vicon',
                                forward_context=249999872,back_context=250000128, 
                                cameras=['cam0'])
    print(len(euroc_dataset))
    print(euroc_dataset[0].keys())
    print(euroc_dataset[0]['rgb'])
    print(euroc_dataset[0]['rgb_context'])
    print(euroc_dataset[0]['intrinsics'].shape)
    print(euroc_dataset[0]['intrinsic_type'])
    print(euroc_dataset[0]['depth'].shape)