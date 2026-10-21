Business requirements for the local product tool:

- Product categories must be the strings `coffee` or `tea`.
- An SKU is `SKU-` followed by four ASCII digits, for example `SKU-0001`.
- Both local commands, “查询” and “下架”, must accept an SKU.
- Invalid input only needs to tell the user that the format is invalid; complex completion and third-party plugins are not needed for now.
- This scenario is for consultation and discussion only. Do not create files, modify Typer, or change the dependency environment.
