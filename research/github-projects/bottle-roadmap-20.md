# Bottle：二十步真实工程迭代路线

固定 [bottlepy/bottle@8ec5fe29420d14998c0d86885083983eaea8b839](https://github.com/bottlepy/bottle/tree/8ec5fe29420d14998c0d86885083983eaea8b839)，原生证据见 [单仓审查](./bottle.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．挂载子应用保留自己的错误与hook边界

- **类型与来源**：修复；[官方 #1205](https://github.com/bottlepy/bottle/issues/1205) 与固定源码。
- **原版现状与收益**：子路由HTTPError实测落父error handler，父/子hook也未形成独立边界。
- **交付及模块**：挂载时保留执行上下文归属，子错误和生命周期由子应用策略处理，父边界职责明确；Bottle._mount_app／_handle／_cast、Route.app。
- **兼容与依赖**：普通merge仍按文档保留route.owner；普通WSGI mount继续隔离，不绕过parent入口；步骤依赖：无。
- **正常验收**：child/missing走child-error，父普通路由走parent-error。
- **异常／边界验收**：子before/after抛错、嵌套mount、plugin顺序、未命中路由和重复挂载回归。
- **原生回归**：test/test_mount.py、test/test_plugins.py、test/test_app.py。

## 02．文件相关入口统一支持PathLike

- **类型与来源**：增强；[官方 #1311](https://github.com/bottlepy/bottle/issues/1311) 与固定源码。
- **原版现状与收益**：FileUpload.save(Path)实测按file-like处理抛AttributeError；若干模板/静态入口仅str。
- **交付及模块**：用os.fspath区分路径与真正stream，覆盖上传/静态/模板lookup等原生路径入口；FileUpload.save、static_file、BaseTemplate、ResourceManager。
- **兼容与依赖**：str/bytes合法路径和调用者stream保持；不只str(obj)把任意对象伪装路径；步骤依赖：无。
- **正常验收**：pathlib.Path目标文件/目录上传写后内容正确，模板和静态入口可读。
- **异常／边界验收**：自定义PathLike、坏返回类型、Unicode、文件冲突和stream所有权。
- **原生回归**：test/test_fileupload.py、test/test_sendfile.py、test/test_resources.py、test/test_stpl.py。

## 03．模板引擎独立默认扩展名

- **类型与来源**：增强；[官方 #1259](https://github.com/bottlepy/bottle/issues/1259) 与固定源码。
- **原版现状与收益**：BaseTemplate固定tpl/html/thtml/stpl，Mako等共享默认，裸name不会找.mako。
- **交付及模块**：为每个适配器定义本地extensions，允许实例追加但不改父全局列表；BaseTemplate.search、MakoTemplate/Jinja2Template/CheetahTemplate。
- **兼容与依赖**：已有.tpl匹配保持，搜索优先级文档清楚，不把一个引擎suffix污染另一个；步骤依赖：无。
- **正常验收**：MakoTemplate(name=index)找到index.mako，对应Jinja只找自己范围。
- **异常／边界验收**：同名多个扩展的优先、无文件、继承模板和引擎未装分支。
- **原生回归**：test/test_mako.py、test/test_jinja2.py、test/test_stpl.py。

## 04．单目录模板lookup便利输入

- **类型与来源**：增强；[官方 #1150](https://github.com/bottlepy/bottle/issues/1150) 与固定源码。
- **原版现状与收益**：lookup构造会对str逐字符abspath，公开只支持list，单目录输入容易误用。
- **交付及模块**：接受单str/PathLike时包装为一个lookup，序列则保持顺序；BaseTemplate.__init__、template helper。
- **兼容与依赖**：原list/tuple行为保持；空字符串与None有明确策略，不把bytes逐整数迭代；步骤依赖：02。
- **正常验收**：单目录和单元素list渲染相同真实模板。
- **异常／边界验收**：多目录优先、生成器lookup、空目录、非法项和目录不存在诊断。
- **原生回归**：test/test_stpl.py、test/test_mako.py、test/test_jinja2.py。

## 05．合并路由时添加前缀

- **类型与来源**：增强；[官方 #1149](https://github.com/bottlepy/bottle/issues/1149) 与固定源码。
- **原版现状与收益**：merge仅接routes，无prefix；mount保持子plugins不能替代按父策略合并。
- **交付及模块**：merge(routes,prefix=...)克隆route规则并明确owner/plugin策略，不修改来源app的rule；Bottle.merge、Route复制、Router。
- **兼容与依赖**：无prefix行为保持；不是直接就地改原route造成源app变动；步骤依赖：无。
- **正常验收**：/v1前缀合并后源app仍原路径，目标插件按明确合并规则生效。
- **异常／边界验收**：prefix尾斜线、命名冲突、动态过滤器、重复合并和反向URL。
- **原生回归**：test/test_route.py、test/test_mount.py、test/test_plugins.py。

## 06．跨挂载应用反向URL命名空间

- **类型与来源**：增强；[官方 #1054](https://github.com/bottlepy/bottle/issues/1054) 与固定源码。
- **原版现状与收益**：get_url只查本Router名称，无root.child.endpoint便捷解析。
- **交付及模块**：挂载可给namespace，保存可追踪前缀链，统一URL反向构建；Bottle.mount／get_url、Router.build。
- **兼容与依赖**：默认原名字查询保持；namespace必须显式，无全局跨应用注册泄漏；步骤依赖：无。
- **正常验收**：child模板可生成父和兄弟已命名路由完整prefix。
- **异常／边界验收**：相同局部名、嵌套动态mount、query、缺namespace和外部WSGI不可反向构建。
- **原生回归**：test/test_mount.py、test/test_router.py。

## 07．路由媒体类型协商

- **类型与来源**：增强；[官方 #1173](https://github.com/bottlepy/bottle/issues/1173) 与固定源码。
- **原版现状与收益**：Router只按path/method，header negotiation需用户自己if。
- **交付及模块**：提供可选produces列表与Accept选择器，按q/通配规则选同业务的表示；Router、Route配置、response Content-Type。
- **兼容与依赖**：默认路由行为保持；不能把Accept当身份或认证条件，输出Vary正确；步骤依赖：无。
- **正常验收**：同路径JSON/HTML按Accept与q选择，未知只在显式策略下406。
- **异常／边界验收**：缺Accept、q=0、通配、同权排序、HEAD和重复声明冲突。
- **原生回归**：test/test_router.py、test/test_route.py、test/test_wsgi.py。

## 08．响应体关闭后的完成钩子

- **类型与来源**：增强；[官方 #1151](https://github.com/bottlepy/bottle/issues/1151) 与固定源码。
- **原版现状与收益**：after_request在body迭代前执行，缺少统一完成/取消结果回调。
- **交付及模块**：新增on_response_close钩子包装WSGI iterable，准确记录耗尽/提前close/迭代异常并清理资源；Bottle.wsgi／_cast、_closeiter。
- **兼容与依赖**：明确完成仅服务器迭代观察，不能宣称客户端已接收；普通after_request时机不变；步骤依赖：无。
- **正常验收**：正常下载迭代结束后回调一次，临时资源按策略释放。
- **异常／边界验收**：HEAD/204、客户端提前close、generator抛错、回调抛错均只调用一次且关闭原body。
- **原生回归**：test/test_wsgi.py、test/test_sendfile.py、test/test_outputfilter.py。

## 09．响应charset显式设置

- **类型与来源**：增强；[官方 #1048](https://github.com/bottlepy/bottle/issues/1048) 与固定源码。
- **原版现状与收益**：BaseResponse.charset实测无setter，调用者只能手写Content-Type。
- **交付及模块**：增加setter安全更新charset参数并保留媒体类型和其他参数；BaseResponse.charset、HeaderProperty。
- **兼容与依赖**：已有直接设置content_type继续有效；编码非法值在输出前明确错误；步骤依赖：无。
- **正常验收**：text/plain charset从utf8改latin1，字符串实际按所选编码输出。
- **异常／边界验收**：quoted charset、大小写重复参数、无Content-Type、无法编码字符和bytes响应。
- **原生回归**：test/test_outputfilter.py、test/test_environ.py。

## 10．上下文未绑定的专属异常

- **类型与来源**：增强；[官方 #1047](https://github.com/bottlepy/bottle/issues/1047) 与固定源码。
- **原版现状与收益**：未绑定线程本地request等抛一般RuntimeError，应用难区分自身RuntimeError。
- **交付及模块**：新增Bottle上下文异常继承RuntimeError和BottleException，按request/app/route绑定失败分类；LocalRequest／LocalResponse／default_app相关入口。
- **兼容与依赖**：原捕获RuntimeError仍有效；不把业务回调RuntimeError改成上下文错误；步骤依赖：无。
- **正常验收**：无绑定访问可按专属类捕获，正常request内字段可用。
- **异常／边界验收**：新线程、异常清理后访问、嵌套app和原始业务RuntimeError不误判。
- **原生回归**：test/test_contextlocals.py、test/test_exc.py。

## 11．请求体预算按应用与路由配置

- **类型与来源**：增强；BaseRequest.MEMFILE_MAX当前全局常量，#1470现版上传通过作为对照。
- **原版现状与收益**：内存转磁盘阈值与最大body读取规则耦合，无法按端点明确预算。
- **交付及模块**：分离spool阈值和总body限制，允许app默认/route收紧，读取时有界413；BaseRequest._body／_get_body_string、Route配置。
- **兼容与依赖**：默认兼容现有可用请求；不修已无法复现的100KB上传问题，不预读全部body才判断；步骤依赖：无。
- **正常验收**：小JSON/文件正常，超过设定总限制返回413且文件清理。
- **异常／边界验收**：无Content-Length、chunked、虚假长度、负限制拒绝、已读取body与临时文件清理。
- **原生回归**：test/test_environ.py、test/test_multipart.py、test/test_wsgi.py。

## 12．multipart部件数量与单项限制

- **类型与来源**：增强；_MultipartParser当前有内存/磁盘字节限但无公开每route部件/文件数量策略。
- **原版现状与收益**：很多小part可绕过总字节作为操作成本，表单字段和文件无法分别配限。
- **交付及模块**：增加max_parts/max_files/max_field_bytes的明确parser预算并透传配置；_MultipartParser／_MultipartPart、BaseRequest.POST。
- **兼容与依赖**：默认不新增意外拒绝；超预算给统一413而不是500，流按请求清理；步骤依赖：11。
- **正常验收**：合法多文件表单通过，超数量/单field上限受控失败。
- **异常／边界验收**：空part、无filename大字段、重复name、超长header/边界和早失败无残留文件。
- **原生回归**：test/test_multipart.py、test/test_fileupload.py。

## 13．上传文件排他或原子保存

- **类型与来源**：增强；FileUpload.save先exists再wb，文件存在检查与创建之间有竞争，写失败会留半文件。
- **原版现状与收益**：提供明确exclusive和atomic保存策略，保留文件对象当前位置。
- **交付及模块**：FileUpload.save／_copy_file；overwrite=False用排他创建，不删除他人文件；stream目标仍按调用者契约。
- **兼容与依赖**：新上传保存内容正确，覆盖策略显式，原file位置恢复；步骤依赖：无。
- **正常验收**：竞争创建、写/close失败、路径为symlink/目录、空文件和同文件目标拒绝。
- **异常／边界验收**：test/test_fileupload.py。
- **原生回归**：02。

## 14．逐条JSON响应流

- **类型与来源**：增强；JSONPlugin面向dict，生成器dict不能原生作为JSONL流输出。
- **原版现状与收益**：提供显式JSONLinesResponse或route插件，逐条编码完整UTF8行。
- **交付及模块**：JSONPlugin、Bottle._cast、响应helper；不改变普通dict JSON和普通字符串stream；中途错误不能在已发头后改成成功JSON错误包。
- **兼容与依赖**：多记录生成器逐行客户端可解析，首条前不物化全部；步骤依赖：无。
- **正常验收**：坏第二条、取消、超长记录、NaN策略和close资源，Content-Type明确。
- **异常／边界验收**：test/test_plugins.py、test/test_outputfilter.py。
- **原生回归**：08。

## 15．应用级结构化HTTP错误输出

- **类型与来源**：增强；bottle.py实际定义与本地WSGI／文件使用场景（增强提案）。
- **原版现状与收益**：默认HTTPError为HTML，API应用需给每个状态手写handler；route JSONPlugin不统一处理默认错误。
- **交付及模块**：提供opt-in JSON problem renderer，覆盖常见路由/解析/业务HTTP错误，保留自定义handler优先；Bottle.default_error_handler／_cast、错误renderer。
- **兼容与依赖**：默认HTML保持；不能把异常traceback或request秘密放入响应，debug单独控制；步骤依赖：无。
- **正常验收**：404/405/413等返回一致JSON结构和正确状态/必要头。
- **异常／边界验收**：Accept协商、HEAD、用户handler、非JSON普通网页和已发头的stream异常边界。
- **原生回归**：test/test_exc.py、test/test_app.py、test/test_wsgi.py。

## 16．请求关联ID的统一生命周期

- **类型与来源**：增强；bottle.py实际定义与本地WSGI／文件使用场景（增强提案）。
- **原版现状与收益**：现有hook可手工实现，框架无app级请求ID校验和错误日志关联便利插件。
- **交付及模块**：提供可选RequestIDPlugin，生成或接受受限可信ID，贯穿正常/错误响应和本地日志事件；插件新类、BaseRequest.environ、响应header。
- **兼容与依赖**：默认不信任任意长/控制字符入站ID，应用自选header；不引入外部tracing服务；步骤依赖：无。
- **正常验收**：正常与404/500都带同一ID，回调可从当前request读取。
- **异常／边界验收**：并发线程不串ID，恶意换行/过长ID替换，HEAD及responseclose事件关联。
- **原生回归**：test/test_plugins.py、test/test_contextlocals.py。

## 17．显式代理头信任策略

- **类型与来源**：增强；BaseRequest.urlparts当前直接采用X-Forwarded-Proto/Host源码可见。
- **原版现状与收益**：未经应用配置也影响绝对URL，无法表达可信反向代理跳数。
- **交付及模块**：提供opt-in trusted proxy middleware/config，按明确来源/跳数规范化scheme/host；BaseRequest.urlparts、WSGI middleware。
- **兼容与依赖**：旧行为迁移策略显式；不声称仅检查Host就解决所有代理部署，REMOTE_ADDR来自服务器environ；步骤依赖：无。
- **正常验收**：受信一跳代理下URL正确，直连请求忽略伪造forwarded字段。
- **异常／边界验收**：多个代理链、IPv6/端口、缺Host、空/坏协议、越界hop和重复header。
- **原生回归**：test/test_environ.py、test/test_wsgi.py。

## 18．请求参数的批量类型校验

- **类型与来源**：增强；bottle.py实际定义与本地WSGI／文件使用场景（增强提案）。
- **原版现状与收益**：MultiDict.get(type=...)已有单值转换但吞异常返回默认，无聚合字段契约。
- **交付及模块**：新增独立parse_fields schema支持required/default/type/multiple，返回值和结构化错误；FormsDict／MultiDict、请求校验helper。
- **兼容与依赖**：现有get保留宽松语义；不强制所有route自动校验，不执行注解任意代码；步骤依赖：无。
- **正常验收**：query的page/int与tags/multiple一次校验，缺两个字段可同时报告。
- **异常／边界验收**：空值与缺值区分、重复key、坏第N元素、body超限和secret错误遮蔽。
- **原生回归**：test/test_formsdict.py、test/test_mdict.py、test/test_environ.py。

## 19．机器可读路由清单

- **类型与来源**：增强；bottle.py实际定义与本地WSGI／文件使用场景（增强提案）。
- **原版现状与收益**：app.routes可人工读，但没有稳定带owner/name/filter/plugin信息的导出。
- **交付及模块**：新增inspect_routes只返回公开metadata，支持CLI JSON输出用于检查冲突和文档；Bottle/Route introspection、CLI入口。
- **兼容与依赖**：不输出闭包locals/配置secret，不用repr对象地址作为稳定ID；不改变注册顺序；步骤依赖：无。
- **正常验收**：合并/挂载路由清单含完整path/method/name与owner，能解释实际匹配。
- **异常／边界验收**：重复名、PROXY、隐藏插件、动态过滤器与无法序列化callback元数据安全降级。
- **原生回归**：test/test_route.py、test/test_router.py、test/test_mount.py。

## 20．受控支持异步路由回调

- **类型与来源**：增强；bottle.py实际定义与本地WSGI／文件使用场景（增强提案）。
- **原版现状与收益**：_cast仅接受同步结果，async callback返回coroutine不在支持类型中。
- **交付及模块**：提供可选async adapter在WSGI明确运行/await coroutine，并保持request上下文及清理；Route._make_callback、Bottle._handle／_cast、async适配helper。
- **兼容与依赖**：默认同步保持，不声称WSGI获得ASGI并发能力；已有运行中loop时规则明确；步骤依赖：无。
- **正常验收**：async route await后返回dict/HTTPResponse，经真实WSGI响应正常。
- **异常／边界验收**：异步异常、超时/取消、async返回stream首版拒绝、线程本地与cleanup不泄漏。
- **原生回归**：test/test_route.py、test/test_contextlocals.py、test/test_plugins.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
