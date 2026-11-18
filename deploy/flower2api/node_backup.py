#!/usr/bin/env python3
"""SSH Node离线备份与集群组合校验的宿主源码入口。"""
from pathlib import Path
import sys

from source_layout import source_path

sys.path.insert(0,str(source_path(Path(__file__).resolve().parents[2],'orchestrator')))
from cluster_backup import main


if __name__=='__main__':
    main()
