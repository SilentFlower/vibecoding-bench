# Synthetic configuration layers
Read shared.env.txt and local.env.txt with dotenv_values. Merge shared, then local, then deployment.json; later layers win. No expression refers to another file. Preserve empty strings. Do not mutate os.environ.
