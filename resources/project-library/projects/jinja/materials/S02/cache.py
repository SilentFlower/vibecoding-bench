from jinja2 import DictLoader, Environment
loader = DictLoader({'weekly.txt': 'v1'})
env = Environment(loader=loader, auto_reload=False)
old_template = env.get_template('weekly.txt')
print(old_template.render())
loader.mapping['weekly.txt'] = 'v2'
print(env.get_template('weekly.txt').render())
# Actual output: v1, then v1.
