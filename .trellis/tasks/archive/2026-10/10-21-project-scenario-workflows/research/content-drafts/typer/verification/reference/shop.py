"""商品应用增强的可达参考候选，仅供独立校准，不投放到工作区。"""
import json
from pathlib import Path
from typing import Annotated

import typer


app = typer.Typer(add_completion=False)


@app.callback()
def root():
    """提供商品工具命令组。@return None。"""


@app.command()
def product(name: str, quantity: Annotated[int, typer.Option(min=0)] = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    typer.echo(f"{name}:{quantity}")


def _records(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("输入必须是对象数组")
    result, seen = [], set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 项必须是对象")
        for field in ("sku", "name"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError(f"第 {index} 项的 {field} 必须是非空字符串")
        if type(item.get("quantity")) is not int or item["quantity"] < 0:
            raise ValueError(f"第 {index} 项的 quantity 必须是非负整数，布尔值不算整数")
        if item["sku"] in seen:
            raise ValueError(f"重复 sku：{item['sku']}")
        seen.add(item["sku"])
        result.append({field: item[field] for field in ("sku", "name", "quantity")})
    return result


@app.command("export")
def export_catalog(source: Path, output: Annotated[Path, typer.Option("--output")]):
    """校验后导出商品清单。

    @param source 用户输入 JSON 文件。
    @param output 必须尚不存在的输出文件。
    @return None；错误时非零退出。
    """
    created = False
    try:
        if source.resolve() == output.resolve():
            raise ValueError("输入和输出不能是同一路径")
        if output.exists() or output.is_symlink():
            raise ValueError("输出文件已存在，拒绝覆盖")
        values = json.loads(source.read_text(encoding="utf-8"))
        # 所有记录通过后才创建文件，避免后面的无效行留下部分导出。
        payload = json.dumps(_records(values), ensure_ascii=False, indent=2) + "\n"
        # 独占创建也覆盖检查后出现同名文件的竞争，不能静默覆盖旧文件。
        with output.open("x", encoding="utf-8") as stream:
            created = True
            stream.write(payload)
    except (OSError, UnicodeError, ValueError) as error:
        if created:
            output.unlink(missing_ok=True)
        typer.echo(f"导出失败：{error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"已导出 {len(values)} 项")


if __name__ == "__main__":
    app()
