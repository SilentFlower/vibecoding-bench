# Exact trailing-newline reproduction
The source text is the two-character string "x\n", bytes 78 0a. Environment().from_string(source).render() gives 'x'; ''.join(Environment().from_string(source).stream()) also gives 'x'.
The requirement is to retain a source-template final newline when present. A separate variable value may itself contain 'x\n'; do not trim variable data. No library modification is authorized.
