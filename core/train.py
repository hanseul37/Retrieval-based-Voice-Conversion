import os
import numpy as np
import faiss
from random import shuffle
import json
import pathlib
import subprocess
from subprocess import Popen, PIPE, STDOUT
from schemas.model import Model
from core.moving import moving_directory

def train_index(exp_dir1, version19):
    exp_dir = "Retrieval_based_Voice_Conversion_WebUI/logs/%s" % (exp_dir1)
    os.makedirs(exp_dir, exist_ok=True)
    feature_dir = (
        "%s/3_feature256" % (exp_dir)
        if version19 == "v1"
        else "%s/3_feature768" % (exp_dir)
    )
    if not os.path.exists(feature_dir):
        return "请先进行特征提取!"
    listdir_res = list(os.listdir(feature_dir))
    if len(listdir_res) == 0:
        return "请先进行特征提取！"
    infos = []
    npys = []
    for name in sorted(listdir_res):
        phone = np.load("%s/%s" % (feature_dir, name))
        npys.append(phone)
    big_npy = np.concatenate(npys, 0)
    big_npy_idx = np.arange(big_npy.shape[0])
    np.random.shuffle(big_npy_idx)
    big_npy = big_npy[big_npy_idx]
    if big_npy.shape[0] > 2e5:
        infos.append("Trying doing kmeans %s shape to 10k centers." % big_npy.shape[0])
        yield "\n".join(infos)
        try:
            big_npy = (
                MiniBatchKMeans(
                    n_clusters=10000,
                    verbose=True,
                    batch_size=256 * config.n_cpu,
                    compute_labels=False,
                    init="random",
                )
                .fit(big_npy)
                .cluster_centers_
            )
        except:
            info = traceback.format_exc()
            logger.info(info)
            infos.append(info)
            yield "\n".join(infos)

    np.save("%s/total_fea.npy" % exp_dir, big_npy)
    n_ivf = min(int(16 * np.sqrt(big_npy.shape[0])), big_npy.shape[0] // 39)
    infos.append("%s,%s" % (big_npy.shape, n_ivf))
    yield "\n".join(infos)
    index = faiss.index_factory(256 if version19 == "v1" else 768, "IVF%s,Flat" % n_ivf)
    # index = faiss.index_factory(256if version19=="v1"else 768, "IVF%s,PQ128x4fs,RFlat"%n_ivf)
    infos.append("training")
    yield "\n".join(infos)
    index_ivf = faiss.extract_index_ivf(index)  #
    index_ivf.nprobe = 1
    index.train(big_npy)
    faiss.write_index(
        index,
        "%s/trained_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (exp_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )

    infos.append("adding")
    yield "\n".join(infos)
    batch_size_add = 8192
    for i in range(0, big_npy.shape[0], batch_size_add):
        index.add(big_npy[i : i + batch_size_add])
    faiss.write_index(
        index,
        "%s/added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (exp_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )
    infos.append(
        "成功构建索引，added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (n_ivf, index_ivf.nprobe, exp_dir1, version19)
    )

def click_train(
    exp_dir1,
    sr2,
    if_f0_3,
    spk_id5,
    save_epoch10,
    total_epoch11,
    batch_size12,
    if_save_latest13,
    pretrained_G14,
    pretrained_D15,
    gpus16,
    if_cache_gpu17,
    if_save_every_weights18,
    version19,
):
    # 生成filelist
    exp_dir = "Retrieval_based_Voice_Conversion_WebUI/logs/%s" %exp_dir1
    os.makedirs(exp_dir, exist_ok=True)
    gt_wavs_dir = "%s/0_gt_wavs" % (exp_dir)
    feature_dir = (
        "%s/3_feature256" % (exp_dir)
        if version19 == "v1"
        else "%s/3_feature768" % (exp_dir)
    )
    if if_f0_3:
        f0_dir = "%s/2a_f0" % (exp_dir)
        f0nsf_dir = "%s/2b-f0nsf" % (exp_dir)
        names = (
            set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)])
            & set([name.split(".")[0] for name in os.listdir(feature_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0nsf_dir)])
        )
    else:
        names = set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)]) & set(
            [name.split(".")[0] for name in os.listdir(feature_dir)]
        )
    opt = []
    for name in names:
        if if_f0_3:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s/%s.wav.npy|%s/%s.wav.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    f0_dir.replace("\\", "\\\\"),
                    name,
                    f0nsf_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
        else:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
    fea_dim = 256 if version19 == "v1" else 768
    if if_f0_3:
        for _ in range(2):
            opt.append(
                "Retrieval_based_Voice_Conversion_WebUI/logs/mute/0_gt_wavs/mute%s.wav|Retrieval_based_Voice_Conversion_WebUI/logs/mute/3_feature%s/mute.npy|Retrieval_based_Voice_Conversion_WebUI/logs/mute/2b-f0nsf/mute.wav.npy|%s"
                % (sr2, fea_dim, spk_id5)
            )
    else:
        for _ in range(2):
            opt.append(
                "Retrieval_based_Voice_Conversion_WebUI/logs/mute/0_gt_wavs/mute%s.wav|Retrieval_based_Voice_Conversion_WebUI/logs/mute/3_feature%s/mute.npy|%s"
                % (sr2, fea_dim, spk_id5)
            )
    shuffle(opt)
    with open("%s/filelist.txt" % exp_dir, "w") as f:
        f.write("\n".join(opt))

    # Replace logger.debug, logger.info with print statements
    print("Write filelist done")
    print("Use gpus:", str(gpus16))
    if pretrained_G14 == "":
        print("No pretrained Generator")
    if pretrained_D15 == "":
        print("No pretrained Discriminator")
    if version19 == "v1" or sr2 == "40k":
        config_path = "Retrieval_based_Voice_Conversion_WebUI/configs/v1/%s.json" % sr2
    else:
        config_path = "Retrieval_based_Voice_Conversion_WebUI/configs/v2/%s.json" % sr2
    config_save_path = os.path.join(exp_dir, "config.json")

    with open(config_save_path, "w", encoding="utf-8") as f:
        with open(config_path, "r") as config_file:
            config_data = json.load(config_file)
            json.dump(
                config_data,
                f,
                ensure_ascii=False,
                indent=4,
                sort_keys=True,
            )
        f.write("\n")

    cmd = (
        'python Retrieval_based_Voice_Conversion_WebUI/infer/modules/train/train.py -e "%s" -sr %s -f0 %s -bs %s -g %s -te %s -se %s %s %s -l %s -c %s -sw %s -v %s'
        % (
            exp_dir1,
            sr2,
            1 if if_f0_3 else 0,
            batch_size12,
            gpus16,
            total_epoch11,
            save_epoch10,
            "-pg %s" % pretrained_G14 if pretrained_G14 != "" else "",
            "-pd %s" % pretrained_D15 if pretrained_D15 != "" else "",
            1 if if_save_latest13 == True else 0,
            1 if if_cache_gpu17 == True else 0,
            1 if if_save_every_weights18 == True else 0,
            version19,
        )
    )
    # Use PIPE to capture the output and error streams
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT, bufsize=1, universal_newlines=True)

    # Print the command's output as it runs
    for line in p.stdout:
        print(line.strip())

    # Wait for the process to finish
    p.wait()
    return "훈련이 완료된 후 실험 폴더 아래에서 콘솔 훈련 로그 또는 train.log를 볼 수 있습니다."

def train_model(model: Model):
    model_name = model.model_name
    exp_dir = model_name
    dataset = model.wav
    sample_rate = "48000"
    ksample_rate = "48k"
    if sample_rate == "40000":
        ksample_rate = "40k"
    else:
        ksample_rate = "48k"
    version = "v2"
    version19 = version

    f0method = "rmvpe"

    save_frequency = 50
    epoch = model.epoch
    batch_size = str(model.batch_size)
    cache_gpu = True

    os.makedirs("Retrieval_based_Voice_Conversion_WebUI/logs/%s" % (exp_dir), exist_ok=True)
    f = open("Retrieval_based_Voice_Conversion_WebUI/logs/%s/preprocess.log" % (exp_dir), "w")
    os.makedirs("Retrieval_based_Voice_Conversion_WebUI/logs/%s" % (exp_dir), exist_ok=True)
    f = open("Retrieval_based_Voice_Conversion_WebUI/logs/%s/extract_f0_feature.log" % (exp_dir), "w")
    f.close()

    command = f"python Retrieval_based_Voice_Conversion_WebUI/infer/modules/train/preprocess.py '{dataset}' {sample_rate} 2 'Retrieval_based_Voice_Conversion_WebUI/logs/{exp_dir}' False 3.0"
    os.system(command)

    if f0method != "rmvpe_gpu":
        command = f"python Retrieval_based_Voice_Conversion_WebUI/infer/modules/train/extract/extract_f0_print.py 'Retrieval_based_Voice_Conversion_WebUI/logs/{exp_dir}' 2 '{f0method}'"
    else:
        command = f"python Retrieval_based_Voice_Conversion_WebUI/infer/modules/train/extract/extract_f0_rmvpe.py 1 0 0 'Retrieval_based_Voice_Conversion_WebUI/logs/{exp_dir}' True"
    os.system(command)

    command = f"python Retrieval_based_Voice_Conversion_WebUI/infer/modules/train/extract_feature_print.py cuda:0 1 0 0 'Retrieval_based_Voice_Conversion_WebUI/logs/{exp_dir}' '{version}' False"
    os.system(command)

    result_generator = train_index(exp_dir, version)

    for result in result_generator:
        print(result)

    if version == 'v1':
        if ksample_rate == '40k':
            G_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained/f0G40k.pth'
            D_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained/f0D40k.pth'
        elif ksample_rate == '48k':
            G_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained/f0G48k.pth'
            D_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained/f0D48k.pth'
    elif version == 'v2':
        if ksample_rate == '40k':
            G_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained_v2/f0G40k.pth'
            D_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained_v2/f0D40k.pth'
        elif ksample_rate == '48k':
            G_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained_v2/f0G48k.pth'
            D_path = 'Retrieval_based_Voice_Conversion_WebUI/assets/pretrained_v2/f0D48k.pth'

    result_generator = click_train(
        exp_dir,
        ksample_rate,
        True,
        0,
        save_frequency,
        epoch,
        batch_size,
        True,
        G_path,
        D_path,
        0,
        cache_gpu,
        False,
        version,
    )
    print(result_generator)

    model_path = f'Retrieval_based_Voice_Conversion_WebUI/assets/weights/{model_name}.pth'
    index_path = f'Retrieval_based_Voice_Conversion_WebUI/logs/{exp_dir}'

    model_path, index_path = moving_directory(model_path, index_path)

    return model_path, index_path