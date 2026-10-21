from tempfile import TemporaryDirectory
from path import Path

with TemporaryDirectory() as directory:
    document = Path(directory) / "orders.txt"
    document.write_bytes(b"original\r\n")
    try:
        with document.in_place(encoding="utf-8") as (reader, writer):
            writer.write("partial")
            raise KeyboardInterrupt("synthetic cancellation")
    except KeyboardInterrupt:
        pass
    print(document.bytes())
    print(reader.closed, writer.closed)
    reader.close()
    writer.close()
