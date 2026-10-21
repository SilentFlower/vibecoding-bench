from pathlib import Path
from tempfile import TemporaryDirectory
import dataset

with TemporaryDirectory() as directory:
    db = dataset.connect("sqlite:///" + str(Path(directory) / "orders.sqlite"))
    try:
        table = db["orders"]
        rows = (dict(order=key) for key in ["A", "B"])
        table.insert_many(rows)
        print(table.count())
    finally:
        db.close()
