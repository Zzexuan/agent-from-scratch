import sys

from huggingface_hub import snapshot_download

from afg.config import SearchConfig

# 同一个仓库里还有 onnx / openvino 格式的同一份权重，我们只用 PyTorch 版，别白下几百 MB；
# pytorch_model.bin 和 model.safetensors 是同一份权重两种封装，transformers 优先读 safetensors
SKIP_PATTERNS = [
    "onnx/*",
    "*.onnx",
    "openvino/*",
    "*.h5",
    "*.msgpack",
    "*.ot",
    "*.tflite",
    "pytorch_model.bin",
]


def download(config):
    print("正在下载 " + config.embedder_repo + " 到 " + config.embedder_dir)
    path = snapshot_download(
        repo_id=config.embedder_repo,
        local_dir=config.embedder_dir,
        ignore_patterns=SKIP_PATTERNS,
    )
    print("完成：" + path)
    return path


def main():
    config = SearchConfig()
    if len(sys.argv) > 1:
        config.embedder_dir = sys.argv[1]
    try:
        download(config)
    except OSError as error:
        # requests / huggingface_hub 的网络错误都继承自 OSError，一起接住给一句人话提示
        print("下载失败：" + str(error))
        print("检查代理是否可用，或改用镜像：")
        print("  export HF_ENDPOINT=https://hf-mirror.com")
        print("  python -m afg.rag.download")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
