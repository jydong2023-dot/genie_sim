import os
# 强制清空代理，规避 socks 代理解析错误
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

# 禁用LFS大文件下载，解决配额耗尽报错
os.environ["HF_HUB_DISABLE_LFS_DOWNLOAD"] = "1"

from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="agibot-world/GenieSimAssets",
    repo_type="dataset",
    revision="main",
    local_dir="./source/geniesim/assets",
    # 删掉已废弃 local_dir_use_symlinks=False
)
