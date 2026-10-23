"""公开复现尾随内容与分钟溢出被接受。"""
from arrow.parser import ParserError, TzinfoParser
for value in ('+03:00.34','+03:99','+24:00','+03:00','(UTC+01:00'):
    try:
        print(value, TzinfoParser.parse(value))
    except (ParserError,ValueError) as error:
        print(value,type(error).__name__)
