# Incremental rebuild plan
The trusted page template is {% extends 'base.html' %}{% block body %}{% include section %}{% endblock %}. base.html is <main>{% block body %}{% endblock %}</main>. a.html is A, b.html is B. Two renders use section='a.html' and section='b.html'.
We need both a conservative rebuild dependency set and the actual dependencies selected for each render. Address cache hits, fallback, duplicate references, and concurrent render isolation. Do not claim a new built-in dependency collector API. Give a plan only.
