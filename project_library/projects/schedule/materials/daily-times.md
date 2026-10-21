# Two daily reports

The same callback must run at 10:00 and 16:00 every day. Both jobs may share tag `daily-reports` for inspection and shutdown. Creating two Job objects is allowed; a single job identity is not a business requirement. `scheduler.every().day.at("10:00").at("16:00").do(write_report)` retains only the second `at_time`. No timezone option is required for this task. Recommend the smallest supported approach; do not extend the library.
