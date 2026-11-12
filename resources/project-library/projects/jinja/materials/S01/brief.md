# Weekly-report integration
All templates and data in this task are synthetic and trusted. Load templates from the supplied mapping; do not introduce a web framework.
base.html: <h1>{{ title }}</h1>{% block body %}{% endblock %}
weekly.html: {% extends 'base.html' %}{% block body %}{% for metric in metrics %}<p>{{ metric }}</p>{% endfor %}{% endblock %}
Context: title='研发周报', metrics=['完成3项', '修复2项', '待办1项'].
Caller: Environment(loader=DictLoader(templates)).get_template('weekly.html').render(context).
