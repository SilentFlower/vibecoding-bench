"""只按 Rust 构建阶段计算配方摘要，隔离无关镜像阶段的缓存失效。"""
import argparse
import hashlib
import re
from pathlib import Path


def backend_recipe_digest(dockerfile: Path) -> str:
    """计算完整 backend 阶段的摘要，包含基础镜像、编译选项和依赖复制。

    :param dockerfile: 当前受版本控制的 Dockerfile。
    :return: backend 阶段原始字节的 SHA256；缺失或重复阶段时拒绝计算。
    """
    raw = dockerfile.read_bytes()
    stages = list(re.finditer(rb'^FROM[^\n]*$', raw, re.MULTILINE | re.IGNORECASE))
    selected = [index for index, stage in enumerate(stages)
        if re.search(rb'\sAS\s+backend\s*$', stage.group(), re.IGNORECASE)]
    if len(selected) != 1:
        raise ValueError('Dockerfile 必须包含唯一的 backend 构建阶段')
    index = selected[0]
    start = stages[index].start()
    end = stages[index + 1].start() if index + 1 < len(stages) else len(raw)
    return hashlib.sha256(raw[:stages[0].start()] + raw[start:end]).hexdigest()


def main() -> None:
    """输出当前 Rust 配方摘要。:return: None。"""
    parser = argparse.ArgumentParser(description='计算 Rust 构建阶段缓存摘要')
    parser.add_argument('dockerfile', type=Path)
    print(backend_recipe_digest(parser.parse_args().dockerfile))


if __name__ == '__main__':
    main()
