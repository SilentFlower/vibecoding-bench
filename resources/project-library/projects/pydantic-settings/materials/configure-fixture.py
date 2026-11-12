"""生成当前咨询场景的本地 .env，不依赖镜像 COPY 保留同名文件。"""
from pathlib import Path


def main() -> None:
    """在允许的应用目录生成公开配置文件并打印路径。@return None。"""
    directory = Path.cwd() / 'app' / 'configure'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'app.env'
    path.write_text('APP_TITLE=商品工具\nAPP_QUANTITY=2\n', encoding='utf-8')
    print(path.resolve())


if __name__ == '__main__':
    main()
