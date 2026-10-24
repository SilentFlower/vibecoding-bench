"""允许授权Python实现叠加，继续固定原节点和原生扩展证明。"""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
spec=spec_from_file_location("frozen_pendulum_control",Path(__file__).with_name("native_regression.py"))
control=module_from_spec(spec);spec.loader.exec_module(control)
suite=dict(control.SUITES["pendulum"])
assert suite["implementation_dir"]=="src/pendulum" and suite["native_modules"]==["pendulum._pendulum"]
suite["overlay"]=True
control.SUITES["pendulum"]=suite
if __name__=="__main__":control.main()
