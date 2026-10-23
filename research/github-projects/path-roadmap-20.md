# path（path.py）：二十步真实工程迭代路线

固定 [jaraco/path@b5ae11e41ba64a9e27fdc42d8c138d7db7699910](https://github.com/jaraco/path/tree/b5ae11e41ba64a9e27fdc42d8c138d7db7699910)，原生证据见 [单仓审查](./path.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．重复合并已有符号链接

- **类型与来源**：修复；[官方 #263](https://github.com/jaraco/path/issues/263) 与实际复现。
- **原版现状与收益**：merge_tree(symlinks=True) 第二次复制相同链接抛 FileExistsError，不能重复同步。
- **交付及模块**：链接覆盖时安全替换预期目标本身，保留链接文本，实际文件不被跟随写坏；Path.merge_tree、symlink／readlink。
- **兼容与依赖**：普通文件复制策略不变；已有目录冲突明确拒绝，不递归删除未知目录；步骤依赖：无。
- **正常验收**：重复两次合并完成，源链接改指向后目标也更新。
- **异常／边界验收**：相对链接、悬空链接、目标是文件／链接／目录分别处理，失败不删除源。
- **原生回归**：tests/test_path.py 的 merge_tree／symlink 测试。

## 02．文件原位编辑的中断回滚

- **类型与来源**：修复；固定源码与 observe.py 合成文件场景。
- **原版现状与收益**：in_place 只捕获 Exception，KeyboardInterrupt 走 finally 删备份；实测原文件被空文件替代。
- **交付及模块**：把准备、写入、关闭和发布置于完整事务边界，所有 BaseException 退出保留旧内容；Path.in_place。
- **兼容与依赖**：保持迭代 reader／writer 和成功替换用法；不把用户已存在 .bak 当可随意删除资源；步骤依赖：无。
- **正常验收**：正常编辑成功，RuntimeError／KeyboardInterrupt／SystemExit 都恢复旧内容。
- **异常／边界验收**：打开 writer、编码、flush／close 失败不丢原件；仅清理本次拥有的备份／临时文件。
- **原生回归**：tests/test_path.py:TestInPlace。

## 03．遍历中的链接策略与循环识别

- **类型与来源**：增强；固定源码与 observe.py 合成文件场景。
- **原版现状与收益**：walk 默认 child.is_dir 会跟随链接，前12项已见 loop/loop 重复。
- **交付及模块**：增加 follow_symlinks 与按设备／inode 的祖先循环检测，避免无限走回同一目录；Path.walk／walkdirs／walkfiles、Traversal。
- **兼容与依赖**：保留现有显式 send 跳转钩子；默认行为兼容说明，循环可按 error policy 报告；步骤依赖：无。
- **正常验收**：真实子目录完整访问；允许链接模式能访问未出现的链接目标。
- **异常／边界验收**：自环、双目录环、悬空链接、权限错误和同目录多个独立链接，不把合法重复文件当循环。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 04．递归路径模式匹配

- **类型与来源**：增强；[官方 #214](https://github.com/jaraco/path/issues/214) 与缺少 rglob 的源码。
- **原版现状与收益**：glob 文档明确非递归；** 当前只匹配一层，不提供任意层规则。
- **交付及模块**：增加 rglob 与显式 recursive glob，按目录组件处理 **；Path.glob／iglob／新增 rglob、matchers。
- **兼容与依赖**：旧 glob 默认不变，不能借递归默认改变已有调用；步骤依赖：03。
- **正常验收**：**/*.txt 匹配 0、1、多层文件且返回 Path 派生类型。
- **异常／边界验收**：隐藏文件、字符组、Unicode、链接循环和无匹配；与步骤03链接策略对齐。
- **原生回归**：tests/test_path.py:TestPatternMatching、模块 doctest。

## 05．遍历深度和声明式排除

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：send 可手动控制单点进入，但没有 max_depth／exclude 的便捷整体策略。
- **交付及模块**：在 walk 提供有界深度和相对路径排除匹配，文件筛选与目录剪枝分开；Path.walk、matchers。
- **兼容与依赖**：默认不限制，现有 match 不被误当剪枝；不重复新增已有 merge_tree.ignore；步骤依赖：无。
- **正常验收**：max_depth=1 不进入孙目录，exclude .git/** 在枚举时剪枝。
- **异常／边界验收**：深度0、负深度拒绝、空排除、只排文件与中断迭代不多读目录。
- **原生回归**：tests/test_path.py 的遍历和 matcher 测试。

## 06．稳定的遍历顺序

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：iterdir 使用 os.listdir 原顺序，复制清单在不同运行结果顺序不可依赖。
- **交付及模块**：提供 sort/key 参数控制每层顺序，供可复现归档和报告使用；Path.iterdir／walk。
- **兼容与依赖**：默认文件系统顺序保持；不改变默认性能或掩盖大小写冲突；步骤依赖：无。
- **正常验收**：乱序创建文件后 sort=True 产生固定相对路径顺序。
- **异常／边界验收**：Unicode、大小写并存、key 异常和大目录有明确局部物化成本。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 07．词法相对路径约束

- **类型与来源**：增强；[官方 #214](https://github.com/jaraco/path/issues/214) 与源码签名。
- **原版现状与收益**：relpathto 可生成 ..，没有 relative_to／is_relative_to 的词法包含契约。
- **交付及模块**：新增词法 relative_to 与 is_relative_to，返回受控相对路径；Path 路径变换方法。
- **兼容与依赖**：明确它不解析链接、不是文件系统沙箱；原 relpath 保持；步骤依赖：无。
- **正常验收**：子路径相对父路径得到 a/b，同路径得到点。
- **异常／边界验收**：不同驱动、绝对与相对混合、同名前缀目录和 .. 归一化规则清楚。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 08．严格真实路径解析

- **类型与来源**：增强；[官方 #214](https://github.com/jaraco/path/issues/214) 与源码。
- **原版现状与收益**：realpath 不公开 strict，缺失组件与环路的错误控制不足。
- **交付及模块**：增加 resolve(strict=False/True) 对接当前平台真实路径解析并保留 Path 类型；Path.realpath／新增 resolve。
- **兼容与依赖**：旧 realpath 行为保持；strict 参数无平台支持时明确拒绝或完整实现；步骤依赖：无。
- **正常验收**：相对路径含符号链接解析为实际绝对路径。
- **异常／边界验收**：缺失末组件、缺失父组件、链接环和自定义 os.path module 的边界有测试。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 09．统一特殊文件类型检查

- **类型与来源**：增强；[官方 #214](https://github.com/jaraco/path/issues/214) 与 introspection。
- **原版现状与收益**：已有 is_file/is_dir/islink/ismount，缺少 FIFO／socket／设备等标准判定。
- **交付及模块**：一次交付剩余 stat 类型谓词与标准命名兼容，避免每个别名独立计步；Path 类型查询段、stat／lstat。
- **兼容与依赖**：已有 islink／ismount 保留；不创建真实设备文件测试，不跟随链接策略明确定义；步骤依赖：无。
- **正常验收**：合成 FIFO 和 Unix socket 正确识别，普通文件均为 false。
- **异常／边界验收**：文件消失、权限错误、悬空链接和不支持平台的可用性显式。
- **原生回归**：tests/test_path.py 的 stat／文件类型测试。

## 10．touch 的存在和权限策略

- **类型与来源**：增强；固定源码与 observe.py 合成文件场景。
- **原版现状与收益**：touch() 固定创建0o666并更新时间，不支持 exist_ok=False。
- **交付及模块**：增加 mode／exist_ok，并保留返回派生 Path 的链式调用；Path.touch。
- **兼容与依赖**：无参语义保持；exist_ok=False 使用排他创建避免检查再创建竞争；步骤依赖：无。
- **正常验收**：创建指定mode的新文件、已有文件允许时更新时间。
- **异常／边界验收**：已有路径拒绝时内容／mtime不变，目录、只读文件、symlink和umask按明确规则。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 11．可选换行风格写入行

- **类型与来源**：增强；固定源码与 observe.py 合成文件场景。
- **原版现状与收益**：write_lines 总是 os.linesep，不能输出固定 CRLF 或保留输入分隔。
- **交付及模块**：提供 linesep/newline 明确参数，让跨平台生成文本可复现；Path.write_lines／_replace_linesep。
- **兼容与依赖**：默认原规则保持，不重复扩展已有 write_text(linesep=...)；步骤依赖：无。
- **正常验收**：同一行序列输出 LF／CRLF／无附加换行的精确字节。
- **异常／边界验收**：末行无换行、已有混合行终止、空行、生成器与非ASCII编码完整。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 12．逐行读取大文件

- **类型与来源**：增强；固定源码与 observe.py 合成文件场景。
- **原版现状与收益**：lines() 读全文后返回 list；chunks 有流式块但不是行接口。
- **交付及模块**：新增 iter_lines，显式 retain/newline/encoding，并在提前结束时关闭自有文件；Path.lines／新增 iter_lines。
- **兼容与依赖**：lines 的现有 list 返回保持；不是把迭代结果缓存起来再yield；步骤依赖：无。
- **正常验收**：大合成文件首行无需读取全文件，内容与 lines 对照一致。
- **异常／边界验收**：超长单行、空文件、CRLF、坏编码、提前close和读取异常不泄漏fd。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 13．整文件写入原子发布

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：write_text/write_bytes 直接覆盖；in_place 是旧文件读取编辑场景，不能提供新文件原子写便利入口。
- **交付及模块**：新增 atomic 选项或独立 write_*_atomic，先完整编码再同目录临时发布；Path.write_text／write_bytes。
- **兼容与依赖**：默认直接写保持；调用者不提供reader，不复用会提前改名旧文件的旧实现；步骤依赖：无。
- **正常验收**：新文件／已有文件写后内容完全匹配，mode按明确规则保留。
- **异常／边界验收**：编码、磁盘写、replace异常保留旧文件并清理临时文件；不是跨设备原子性承诺。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 14．相同输出保留文件时间

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：write_text/write_bytes 总是重写，即使新字节相同会触发构建／同步。
- **交付及模块**：新增 only_if_changed，比较相同直接保留inode/mtime，变化按选择的发布模式写入；Path.write_text／write_bytes。
- **兼容与依赖**：默认重写保持；只承诺本次比较，不宣称非合作并发事务隔离；步骤依赖：13。
- **正常验收**：相同字节的生成文件保持时间，不同字节更新。
- **异常／边界验收**：空文件、新目标、二进制、符号链接策略和比较失败不静默丢写。
- **原生回归**：tests/test_path.py 的读写／时间测试。

## 15．目录合并的可审查计划

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：merge_tree 直接执行，没有机器可读的差异和 dry-run 结果。
- **交付及模块**：新增 plan_merge 返回将新增／覆盖／冲突的相对路径，apply 可按预期摘要核对后执行；Path.merge_tree、独立计划记录类型。
- **兼容与依赖**：现有 merge_tree 返回和直接执行保持；计划不等于锁定目标状态；步骤依赖：无。
- **正常验收**：dry-run 不写目标，计划与实际操作清单对应。
- **异常／边界验收**：源／目标在计划后变化时显式拒绝陈旧项，ignore已存在不重复计步，路径不能越界。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 16．显式镜像模式清理多余项

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：merge_tree 只增加覆盖，不删除已从源移走的旧文件，备份镜像会累积过期项。
- **交付及模块**：提供单独 opt-in mirror_tree，基于计划列出目标额外项并受控删除；目录同步新入口、计划和遍历模块。
- **兼容与依赖**：绝不改变 merge_tree 默认；拒绝目标等于源／源内部或不明根，首版限制本地普通目录；步骤依赖：15。
- **正常验收**：合成源删去一文件后镜像目标相应删除，其余内容保留。
- **异常／边界验收**：符号链接只处理链接本身、忽略文件保留、计划摘要失配停止；所有验收只对临时树。
- **原生回归**：tests/test_path.py 的目录复制／合并测试。

## 17．按内容判定文件是否需要复制

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：only_newer 仅按mtime，来源内容改变但时间保持会被跳过。
- **交付及模块**：提供独立 only_different(copy_func)，先大小再流式hash／字节比较决定；only_newer 附近新增比较包装器、Path.chunks。
- **兼容与依赖**：only_newer 原语义保持；清楚声明比较期间文件变化会拒绝或重试；步骤依赖：无。
- **正常验收**：同mtime不同内容仍复制，相同内容较旧也可跳过。
- **异常／边界验收**：同大小不同内容、大文件、来源消失和比较错误不误判相同。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 18．哈希算法策略和参数

- **类型与来源**：增强；[官方 #240](https://github.com/jaraco/path/issues/240) 与 _hash 源码。
- **原版现状与收益**：hashlib.new(hash_name) 没有 usedforsecurity／digest参数，FIPS 下非安全MD5用途无法显式表明。
- **交付及模块**：哈希API透传受控构造参数，文档把示例改为SHA-256，非安全MD5需显式选择；Path._hash／read_hash／read_hexhash／read_md5。
- **兼容与依赖**：默认算法选择不变；不绕过系统安全策略，实际FIPS验证另列环境；步骤依赖：无。
- **正常验收**：SHA-256结果与hashlib一致，选项透传可观察。
- **异常／边界验收**：未知算法、拒绝参数、shake可变长度输出明确支持范围；本轮未声称FIPS实机验证。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 19．多摘要一次读取与校验清单

- **类型与来源**：增强；固定源码的文件／备份工作流缺口分析（增强提案）。
- **原版现状与收益**：每个 read_hash 独立扫描，备份既要 SHA-256 又要其他摘要时重复IO，也无校验清单入口。
- **交付及模块**：一次流式读取计算指定多算法并生成／校验受控相对路径清单；Path.chunks／新摘要集合 helper。
- **兼容与依赖**：原单hash方法保留；清单不执行命令、不允许绝对或越界路径；步骤依赖：无。
- **正常验收**：合成树清单生成后逐文件校验，损坏一文件定位失败。
- **异常／边界验收**：重复项、未知算法、空树、链接策略、超大清单和文件读取中变化明确处理。
- **原生回归**：tests/test_path.py、path/__init__.py 原生 doctest。

## 20．可选 platformdirs 的特殊目录后端

- **类型与来源**：增强；Path.special／SpecialResolver 实际依赖 appdirs 与库的跨平台目录场景。
- **原版现状与收益**：现有 special 只导入 appdirs，无法使用 platformdirs 的 state／runtime 等扩展策略。
- **交付及模块**：新增显式 backend 选项支持 platformdirs，保留用户／site Path 和 Multi 包装；SpecialResolver、Path.special、可选extra。
- **兼容与依赖**：默认 appdirs 保持，核心零依赖仍能 -S 导入；不把所有目录名当独立步骤；步骤依赖：无。
- **正常验收**：在合成XDG环境中 user.state/runtime 和多路径返回正确包装类型。
- **异常／边界验收**：后端未安装给明确ImportError，版本参数／root策略／真实目录不自动创建。
- **原生回归**：tests/test_path.py:TestSpecialPaths／TestMultiPath。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
