"""逐步取证固定原版轮转测试的时钟与xattr，不改时钟或断言。"""
from json import dumps
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep, time

from loguru import logger
from loguru._ctime_functions import load_ctime_functions


def main() -> None:
    """执行同一原生调用顺序并保留每步真实文件与创建时间。@return None。"""
    get_ctime, _ = load_ctime_functions()
    rows = []
    logger.remove()
    try:
        with TemporaryDirectory(dir='/tmp') as temporary:
            root = Path(temporary)
            path = root / 'test.log'

            def record(name: str) -> None:
                """保留未格式化前的真实时间戳。@param name 当前步骤。@return None。"""
                rows.append({'step': name, 'time': time(),
                    'files': [{'name': p.name, 'content': p.read_text(), 'ctime': get_ctime(str(p)),
                        'mtime': p.stat().st_mtime, 'inode': p.stat().st_ino} for p in sorted(root.iterdir())]})

            handler = logger.add(path, format='{message}', delay=False, rotation='2 s')
            logger.info('1')
            record('first')
            sleep(1.5)
            logger.info('2')
            logger.remove(handler)
            handler = logger.add(path, format='{message}', delay=False, rotation='2 s')
            logger.info('3')
            record('reopen-first')
            sleep(1)
            logger.info('4')
            record('rotate-first')
            logger.remove(handler)
            sleep(1)
            handler = logger.add(path, format='{message}', delay=False, rotation='2 s')
            logger.info('5')
            record('reopen-second')
            sleep(1.5)
            logger.info('6')
            logger.remove(handler)
            record('rotate-second')
    finally:
        logger.remove()
    print(dumps({'status': 'passed', 'candidate_import': True, 'steps': rows,
        'scope': '当前镜像固定原版时钟诊断，passed只表示取证正常结束，不表示原生断言通过'}))


if __name__ == '__main__':
    main()
