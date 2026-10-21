# Complete sanitized call context
The caller supplies config_path explicitly as the absolute path to synthetic-config.env.txt in its temporary directory. loader.py is the exact call body. Before the call, the process mapping is environment.json; observed.json records its return and final APP_MODE. No other loading call or asynchronous writer exists in this reproduction.
