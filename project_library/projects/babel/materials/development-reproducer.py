"""Public demonstration of the gap between existing string output and the missing parts API."""
from datetime import datetime
from babel import dates
value = datetime(2024,4,3,15,30)
pattern = "MMMM d 'at' HH:mm"
print('string',dates.format_datetime(value,pattern,locale='en_US'))
print('parts API present',hasattr(dates,'format_datetime_to_parts'))
if hasattr(dates,'format_datetime_to_parts'):
    print(dates.format_datetime_to_parts(value,pattern,locale='en_US'))
