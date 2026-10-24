# Markup与模型代码生成读取配置时不消耗调用方容器

路线03：Markup和generate_base_model先复制配置内建容器再pop/派生，保共享别名与回调/模型身份，循环拒绝；只读外层Mapping可复用，嵌套来源不消耗。
