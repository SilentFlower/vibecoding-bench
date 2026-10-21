可以用一个命令直接接入，不需要在调用中再写 `product`：

```python
from typing import Annotated
import typer

app = typer.Typer(add_completion=False)


@app.command()
def product(name: str, quantity: Annotated[int, typer.Option()] = 1):
    """显示商品数量。@param name 名称。@param quantity 数量。@return None。"""
    typer.echo(f"{name}:{quantity}")


if __name__ == "__main__":
    app()
```

调用 `python shop.py 咖啡 --quantity 3` 得到 `咖啡:3`，省略数量得到 `咖啡:1`，0 可用。负数与不能转成整数的输入会返回非零退出码并提示参数错误，`--help` 只显示帮助。这里仅给出示例，尚未替你创建文件。
