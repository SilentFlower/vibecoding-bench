"""在隔离验收容器中观察固定 Typer 与用户应用的真实行为。

@param --candidate-root 冻结候选根目录，默认由控制端环境变量注入。
@param --answer-file 冻结 UTF-8 回答，仅咨询示例验收需要。
@param --mode 当前任务的冻结观察模式。
@return 标准输出为单一、有界 JSON；控制端与冻结 expected 比较。
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_SINGLE = '''from typing import Annotated
import typer
app = typer.Typer(add_completion=False)
@app.command()
def product(name: str, quantity: Annotated[int, typer.Option(min=0)] = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    typer.echo(f"{name}:{quantity}")
if __name__ == "__main__":
    app()
'''
_GROUP = '''import typer
app = typer.Typer(add_completion=False)
@app.callback()
def root(verbose: bool = False):
    """声明根选项。@param verbose 详细模式。@return None。"""
@app.command()
def export():
    """演示本地导出入口。@return None。"""
    typer.echo("exported")
if __name__ == "__main__":
    app()
'''
_TYPES = '''from typing import Annotated, Literal
import json
import re
import typer
from typer import _click
from typer.models import ParameterInfo
from typer.testing import CliRunner
class Sku:
    """保存已校验的商品编号。@param value 编号。"""
    def __init__(self, value: str):
        self.value = value
def parse_sku(value: str) -> Sku:
    """解析商品编号。@param value 输入。@return 业务对象。"""
    if not re.fullmatch(r"SKU-[0-9]{4}", value):
        raise ValueError("SKU 格式不对")
    return Sku(value)
class SkuType(_click.types.ParamType):
    """自定义商品参数类型。"""
    name = "sku"
    def convert(self, value, param, ctx):
        """转换参数。@param value 输入。@param param 参数。@param ctx 上下文。@return 商品编号。"""
        try:
            return parse_sku(value)
        except ValueError as error:
            self.fail(str(error), param, ctx)
app = typer.Typer(add_completion=False)
@app.callback()
def root():
    """提供三个独立参数能力入口。@return None。"""
@app.command()
def category(value: Literal["coffee", "tea"]):
    """输出品类。@param value 品类。@return None。"""
    typer.echo(value)
@app.command()
def find(sku: Annotated[Sku, typer.Argument(parser=parse_sku)]):
    """演示解析函数。@param sku 商品。@return None。"""
    typer.echo(sku.value)
@app.command()
def archive(sku: Annotated[Sku, typer.Argument(click_type=SkuType())]):
    """演示参数类型。@param sku 商品。@return None。"""
    typer.echo(sku.value)
runner = CliRunner()
ok = runner.invoke(app, ["category", "coffee"])
bad = runner.invoke(app, ["category", "milk"])
custom = runner.invoke(app, ["find", "SKU-0001"])
custom_bad = runner.invoke(app, ["find", "SKU-１２３４"])
typed = runner.invoke(app, ["archive", "SKU-0002"])
rejected = False
try:
    ParameterInfo(parser=parse_sku, click_type=SkuType())
except ValueError:
    rejected = True
print(json.dumps({
    "literal_choices": ok.exit_code == 0 and ok.stdout.strip() == "coffee" and bad.exit_code != 0,
    "custom_parser": custom.exit_code == 0 and custom.stdout.strip() == "SKU-0001",
    "custom_type": typed.exit_code == 0 and typed.stdout.strip() == "SKU-0002",
    "parser_and_type_rejected": rejected,
    "invalid_parser_input_rejected": custom_bad.exit_code != 0 and "Invalid value" in custom_bad.output,
}))
'''


def _environment(root: Path) -> dict:
    environment = dict(os.environ)
    paths = [str(root / "library"), str(root / "app")]
    if environment.get("PYTHONPATH"):
        paths.append(environment["PYTHONPATH"])
    environment.update(PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1", NO_COLOR="1", TERM="dumb", TERMINAL_WIDTH="80",
        _TYPER_FORCE_DISABLE_TERMINAL="1")
    return environment


def _run(arguments: list[str], cwd: Path, environment: dict) -> dict:
    # 双管道按字节限流，避免错误候选无限打印占满验收内存。
    process = subprocess.Popen([sys.executable, "-B", *arguments], cwd=cwd,
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        selector.register(stream, selectors.EVENT_READ, name)
    deadline, limited = time.monotonic() + 8, None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                limited = "程序超过单用例时限"
                break
            for key, _ in selector.select(min(remaining, 0.2)):
                block = os.read(key.fileobj.fileno(), 4096)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                captured[key.data].extend(block)
                if len(captured[key.data]) > 65536:
                    limited = "程序输出超过单用例上限"
                    break
            if limited:
                break
        if limited:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()
    result = {name: _ANSI.sub("", bytes(value[:65536]).decode("utf-8", errors="replace"))
        for name, value in captured.items()}
    result["returncode"] = process.returncode if not limited else 124
    if limited:
        result["stderr"] += limited
    return result


def _candidate_library(root: Path, environment: dict) -> bool:
    command = "import json,typer;print(json.dumps({'file':typer.__file__,'version':typer.__version__}))"
    result = _run(["-c", command], root, environment)
    if result["returncode"]:
        return False
    try:
        value = json.loads(result["stdout"])
        return (Path(value["file"]).resolve() == (root / "library/typer/__init__.py").resolve()
            and value["version"] == "0.27.3")
    except (KeyError, ValueError, TypeError):
        return False


def _complete_programs(answer: str) -> list[str]:
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", answer, flags=re.DOTALL | re.IGNORECASE)
    blocks = [block for block in blocks if len(block.encode("utf-8")) <= 32768]
    if not blocks:
        blocks = [answer]

    def complete(value: str) -> str | None:
        try:
            tree = ast.parse(value)
        except SyntaxError:
            return None
        imported = any((isinstance(node, ast.Import) and any(alias.name == "typer" for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "typer") for node in tree.body)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        launches = any((isinstance(node.func, ast.Attribute) and node.func.attr == "run")
            or (isinstance(node.func, ast.Name) and node.func.id in {
                target.id for assignment in tree.body if isinstance(assignment, ast.Assign)
                for target in assignment.targets if isinstance(target, ast.Name)
                and isinstance(assignment.value, ast.Call)}) for node in calls)
        return ast.dump(tree, include_attributes=False) if imported and launches else None

    # 首先识别完整程序；仅在回答是分块代码时合并，不能任取第一个代码块。
    programs = {}
    for block in blocks[:8]:
        fingerprint = complete(block)
        if fingerprint:
            programs[fingerprint] = block
    if not programs and len(blocks) > 1:
        joined = "\n\n".join(blocks[:8])
        fingerprint = complete(joined)
        if fingerprint and len(joined.encode("utf-8")) <= 32768:
            programs[fingerprint] = joined
    return list(programs.values())


def _consult(root: Path, answer_file: Path, environment: dict) -> dict:
    answer = answer_file.read_text(encoding="utf-8")
    programs = _complete_programs(answer) if len(answer.encode("utf-8")) <= 131072 else []
    result = {"candidate_library": _candidate_library(root, environment),
        "consult_sample_found": bool(programs), "consult_unambiguous": len(programs) == 1,
        "quantity_three": False, "quantity_default": False, "quantity_zero": False,
        "negative_rejected": False, "invalid_integer_rejected": False, "help_no_business": False}
    if len(programs) != 1:
        return result
    with tempfile.TemporaryDirectory(prefix="typer-consult-") as temporary:
        cwd = Path(temporary)
        (cwd / "shop.py").write_text(programs[0], encoding="utf-8")
        for key, arguments, expected in (("quantity_three", ["咖啡", "--quantity", "3"], "咖啡:3"),
                ("quantity_default", ["咖啡"], "咖啡:1"),
                ("quantity_zero", ["咖啡", "--quantity", "0"], "咖啡:0")):
            reply = _run(["shop.py", *arguments], cwd, environment)
            result[key] = reply["returncode"] == 0 and reply["stdout"].strip() == expected
        for key, value in (("negative_rejected", "-1"), ("invalid_integer_rejected", "不是整数")):
            reply = _run(["shop.py", "咖啡", "--quantity", value], cwd, environment)
            result[key] = reply["returncode"] != 0 and bool((reply["stdout"] + reply["stderr"]).strip())
        reply = _run(["shop.py", "--help"], cwd, environment)
        result["help_no_business"] = (reply["returncode"] == 0 and "quantity" in reply["stdout"]
            and not re.search(r"咖啡:\d", reply["stdout"]))
    return result


def _diagnose(root: Path, mode: str, environment: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="typer-diagnosis-") as temporary:
        cwd = Path(temporary)
        (cwd / "shop.py").write_text(_SINGLE if mode == "single" else _GROUP, encoding="utf-8")
        if mode == "single":
            direct = _run(["shop.py", "咖啡", "--quantity", "3"], cwd, environment)
            named = _run(["shop.py", "product", "咖啡", "--quantity", "3"], cwd, environment)
            return {"candidate_library": _candidate_library(root, environment),
                "single_direct_works": direct["returncode"] == 0 and direct["stdout"].strip() == "咖啡:3",
                "single_extra_command_rejected": named["returncode"] != 0}
        before = _run(["shop.py", "--verbose", "export"], cwd, environment)
        after = _run(["shop.py", "export", "--verbose"], cwd, environment)
        root_help = _run(["shop.py", "--help"], cwd, environment)
        export_help = _run(["shop.py", "export", "--help"], cwd, environment)
        return {"candidate_library": _candidate_library(root, environment),
            "root_option_before_works": before["returncode"] == 0 and before["stdout"].strip() == "exported",
            "root_option_after_rejected": after["returncode"] != 0 and "No such option" in after["stderr"],
            "option_belongs_to_root": root_help["returncode"] == 0 and export_help["returncode"] == 0
                and "verbose" in root_help["stdout"] and "verbose" not in export_help["stdout"]}


def _types(root: Path, environment: dict) -> dict:
    reply = _run(["-c", _TYPES], root, environment)
    keys = ("literal_choices", "custom_parser", "custom_type", "parser_and_type_rejected",
        "invalid_parser_input_rejected")
    result = {key: False for key in keys}
    if reply["returncode"] == 0:
        try:
            values = json.loads(reply["stdout"])
            result.update({key: values.get(key) is True for key in keys})
        except (ValueError, AttributeError):
            pass
    return {"candidate_library": _candidate_library(root, environment), **result}


def _export(root: Path, environment: dict) -> dict:
    script = root / "app/shop.py"
    expected = [{"sku": "SKU-0001", "name": "咖啡", "quantity": 3},
        {"sku": "SKU-0002", "name": "茶", "quantity": 0}]
    valid = [dict(item, ignored="不导出") for item in expected]
    result = {"candidate_library": _candidate_library(root, environment)}

    def run_case(value: object, *, raw: bool = False, existing: bool = False,
            same: bool = False, missing: bool = False) -> tuple[dict, bytes | None, bool, bool]:
        with tempfile.TemporaryDirectory(prefix="typer-export-") as temporary:
            cwd = Path(temporary)
            source, output = cwd / "catalog.json", cwd / "result.json"
            if not missing:
                source.write_text(value if raw else json.dumps(value, ensure_ascii=False), encoding="utf-8")
            before = source.read_bytes() if source.exists() else None
            if same:
                output = source
            elif existing:
                output.write_bytes(b"keep-existing-output")
            reply = _run([str(script), "export", str(source), "--output", str(output)], cwd, environment)
            data = output.read_bytes() if output.exists() else None
            unchanged = (source.read_bytes() if source.exists() else None) == before
            explained = bool((reply["stdout"] + reply["stderr"]).strip())
            return reply, data, unchanged, explained

    reply, data, unchanged, _ = run_case(valid)
    try:
        decoded = json.loads(data) if data is not None else None
    except ValueError:
        decoded = None
    result["normal_export"] = reply["returncode"] == 0 and decoded == expected
    result["chinese_utf8"] = data is not None and "咖啡".encode() in data and "茶".encode() in data
    result["input_unchanged"] = unchanged
    reply, data, unchanged, _ = run_case([])
    try:
        empty = json.loads(data) if data is not None else None
    except ValueError:
        empty = None
    result["empty_array"] = reply["returncode"] == 0 and empty == [] and unchanged
    invalid = {
        "bad_json": ("[not-json", True), "not_array": ({"sku": "SKU-0001"}, False),
        "non_object": (["商品"], False), "missing_sku": ([{"name": "咖啡", "quantity": 1}], False),
        "missing_name": ([{"sku": "SKU-0001", "quantity": 1}], False),
        "missing_quantity": ([{"sku": "SKU-0001", "name": "咖啡"}], False),
        "empty_sku": ([{"sku": "", "name": "咖啡", "quantity": 1}], False),
        "empty_name": ([{"sku": "SKU-0001", "name": "", "quantity": 1}], False),
        "wrong_sku_type": ([{"sku": 1, "name": "咖啡", "quantity": 1}], False),
        "wrong_name_type": ([{"sku": "SKU-0001", "name": 1, "quantity": 1}], False),
        "negative_quantity": ([dict(expected[0], quantity=-1)], False),
        "float_quantity": ([dict(expected[0], quantity=1.5)], False),
        "bool_quantity": ([dict(expected[0], quantity=True)], False),
        "string_quantity": ([dict(expected[0], quantity="3")], False),
        "duplicate_sku": ([expected[0], dict(expected[0], name="另一种咖啡")], False),
        "late_invalid_record": ([expected[0], dict(expected[1], quantity=False)], False),
    }
    for key, (value, raw) in invalid.items():
        reply, data, unchanged, explained = run_case(value, raw=raw)
        result["reject_" + key] = reply["returncode"] != 0 and data is None and unchanged and explained
    reply, data, unchanged, explained = run_case(valid, existing=True)
    result["refuse_overwrite"] = (reply["returncode"] != 0 and data == b"keep-existing-output"
        and unchanged and explained)
    reply, _, unchanged, explained = run_case(valid, same=True)
    result["refuse_input_as_output"] = reply["returncode"] != 0 and unchanged and explained
    reply, data, _, explained = run_case(None, missing=True)
    result["missing_input"] = reply["returncode"] != 0 and data is None and explained
    with tempfile.TemporaryDirectory(prefix="typer-product-") as temporary:
        cwd = Path(temporary)
        product = _run([str(script), "product", "咖啡", "--quantity", "3"], cwd, environment)
        default = _run([str(script), "product", "咖啡"], cwd, environment)
        negative = _run([str(script), "product", "咖啡", "--quantity", "-1"], cwd, environment)
        result["product_regression"] = (product["returncode"] == 0 and product["stdout"].strip() == "咖啡:3"
            and default["returncode"] == 0 and default["stdout"].strip() == "咖啡:1" and negative["returncode"] != 0)
        before = set(cwd.iterdir())
        root_help = _run([str(script), "--help"], cwd, environment)
        export_help = _run([str(script), "export", "--help"], cwd, environment)
        result["help_without_output"] = (root_help["returncode"] == 0 and export_help["returncode"] == 0
            and "export" in root_help["stdout"] and "output" in export_help["stdout"] and set(cwd.iterdir()) == before)
    tests = root / "app/tests"
    result["business_tests_present"] = tests.is_dir() and any(tests.rglob("test*.py"))
    readme = root / "app/README.md"
    text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    result["usage_documented"] = "export" in text and "--output" in text and "product" in text
    return result


def main() -> None:
    """解析冻结模式并输出观察结果。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, default=os.environ.get("PROJECT_CANDIDATE_ROOT", "."))
    parser.add_argument("--answer-file", type=Path, default=os.environ.get("PROJECT_ANSWER_FILE"))
    parser.add_argument("--mode", required=True, choices=("consult", "single", "group", "types", "export"))
    arguments = parser.parse_args()
    root = arguments.candidate_root.resolve()
    environment = _environment(root)
    if arguments.mode == "consult":
        if arguments.answer_file is None:
            raise ValueError("咨询验收需要控制端注入冻结回答")
        result = _consult(root, arguments.answer_file, environment)
    elif arguments.mode in ("single", "group"):
        result = _diagnose(root, arguments.mode, environment)
    elif arguments.mode == "types":
        result = _types(root, environment)
    else:
        result = _export(root, environment)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
