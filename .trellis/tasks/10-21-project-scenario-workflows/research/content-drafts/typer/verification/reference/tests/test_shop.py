"""参考候选附带的用户业务测试，不代替控制端独立验收。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ShopTests(unittest.TestCase):
    """验证导出与既有商品命令的用户行为。"""

    def _invoke(self, cwd: Path, arguments: list[str]) -> subprocess.CompletedProcess:
        script = Path(__file__).resolve().parents[1] / "shop.py"
        return subprocess.run([sys.executable, str(script), *arguments], cwd=cwd,
            capture_output=True, text=True, timeout=8, check=False)

    def test_export_and_retain_product(self):
        """正常导出保留中文与顺序，原商品命令仍可用。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            data = [{"sku": "SKU-0001", "name": "咖啡", "quantity": 3, "extra": 4}]
            source = cwd / "catalog.json"
            source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            before = source.read_bytes()
            reply = self._invoke(cwd, ["export", "catalog.json", "--output", "result.json"])
            self.assertEqual(0, reply.returncode, reply.stderr)
            self.assertEqual([{"sku": "SKU-0001", "name": "咖啡", "quantity": 3}],
                json.loads((cwd / "result.json").read_text(encoding="utf-8")))
            self.assertIn("咖啡", (cwd / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(before, source.read_bytes())
            product = self._invoke(cwd, ["product", "咖啡", "--quantity", "3"])
            self.assertEqual("咖啡:3", product.stdout.strip())

    def test_invalid_input_and_overwrite_leave_files_intact(self):
        """后续无效记录不留下部分输出，已有文件不被覆盖。@return None。"""
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            source = cwd / "catalog.json"
            source.write_text('[{"sku":"a","name":"咖啡","quantity":1},'
                '{"sku":"b","name":"茶","quantity":true}]', encoding="utf-8")
            reply = self._invoke(cwd, ["export", "catalog.json", "--output", "result.json"])
            self.assertNotEqual(0, reply.returncode)
            self.assertFalse((cwd / "result.json").exists())
            (cwd / "result.json").write_text("已有内容", encoding="utf-8")
            reply = self._invoke(cwd, ["export", "catalog.json", "--output", "result.json"])
            self.assertNotEqual(0, reply.returncode)
            self.assertEqual("已有内容", (cwd / "result.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
