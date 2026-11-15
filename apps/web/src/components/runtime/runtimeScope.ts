import type { Terminal } from 'xterm';
import type { FitAddon } from 'xterm-addon-fit';

/** 游标分页的真实位置及动作许可。 */
export interface RuntimePagination { kind:'events'|'history';page:number;size:number;loading:boolean;hasPrevious:boolean;hasNext:boolean;canLatest:boolean }
/** 运行控制器发给Vue宿主的受控导航或详情事件。 */
export interface RuntimeMessage { type: string; tab?: string; replace?: boolean; id?: string | number; title?: string; accountName?: string; account?: string | null; environment?: string | null; gateway_account?: string | null; section?: string | null; pagination?:RuntimePagination }

/** 为原执行控制器提供局部DOM根和可统一释放的浏览器资源。@param root 任务根。@param body 内容根。@param initialHash 原内部地址。@param receive Vue路由及弹窗回调。@return 作用域、地址同步和清理函数。 */
export function createRuntimeScope(root: HTMLElement, body: HTMLElement, initialHash: string, receive: (message: RuntimeMessage) => void) {
  const owner = root.ownerDocument;
  const localEvents = new EventTarget();
  const locationValue = new URL(`/runtime/?view=tasks${initialHash}`, location.origin);
  const listeners: { target: EventTarget; type: string; listener: EventListenerOrEventListenerObject; original: EventListenerOrEventListenerObject; options?: boolean | AddEventListenerOptions }[] = [];
  const timers = new Set<number>(), intervals = new Set<number>(), frames = new Set<number>();
  const observers = new Set<MutationObserver | ResizeObserver>();
  const sockets = new Set<WebSocket>(), sources = new Set<EventSource>(), terminals = new Set<Terminal>(), requests = new Set<AbortController>();
  let disposed = false;
  /** 记录原注册目标，离页成对注销。@param target 目标。@param type 类型。@param listener 回调。@param options 监听选项。@return 无。 */
  function listen(target: EventTarget, type: string, listener: EventListenerOrEventListenerObject, options?: boolean | AddEventListenerOptions, original=listener): void { target.addEventListener(type, listener, options);listeners.push({target,type,listener,original,options}); }
  /** 注销实际监听及其宿主引用。@param type 类型。@param listener 原回调。@param options 捕获选项。@return 无。 */
  function unlisten(type:string,listener:EventListenerOrEventListenerObject,options?:boolean|EventListenerOptions):void{const capture=typeof options==='boolean'?options:options?.capture??false;for(let index=listeners.length-1;index>=0;index--){const item=listeners[index]!;const recorded=typeof item.options==='boolean'?item.options:item.options?.capture??false;if(item.type===type&&item.original===listener&&recorded===capture){item.target.removeEventListener(type,item.listener,item.options);listeners.splice(index,1);}}}
  /** 只提交白名单内部地址，主历史始终由Vue管理。@param hash 内部地址。@return 无。 */
  function navigate(hash: string): void { if(disposed)return;const [tab,query]=hash.replace(/^#/,'').split('?');const params=new URLSearchParams(query);receive({type:'runtime:navigate',tab,account:params.getAll('account').length>1?'0':params.get('account'),environment:params.get('environment'),gateway_account:params.get('gateway_account'),section:params.get('section')}); }
  const scopedLocation = new Proxy(locationValue, {
    get(target,key) { if(key==='replace'||key==='assign')return (value:string)=>navigate(new URL(value,target).hash);if(key==='reload')return ()=>localEvents.dispatchEvent(new Event('hashchange'));return Reflect.get(target,key,target); },
    set(target,key,value) { if(key==='hash'){navigate(String(value));return true;}return Reflect.set(target,key,value,target); },
  });
  let historyState: unknown = null;
  const scopedHistory = {
    get state(): unknown { return historyState; },
    /** 更新控制器地址快照，实际历史由后续宿主导航消息统一写入。@param data 历史状态。@param _unused 兼容参数。@param url 内部地址。@return 无。 */
    replaceState(data: unknown, _unused: string, url?: string | URL | null): void {
      historyState = data;
      if (url != null) locationValue.hash = new URL(url, locationValue).hash;
    },
  };
  const scopedDocument = new Proxy(owner, {get(target,key){
    if(key==='documentElement')return root;if(key==='body')return body;
    if(key==='querySelector')return root.querySelector.bind(root);if(key==='querySelectorAll')return root.querySelectorAll.bind(root);
    if(key==='getElementById')return (id:string)=>root.querySelector(`#${CSS.escape(id)}`);
    if(key==='addEventListener')return (type:string,listener:EventListenerOrEventListenerObject,options?:boolean|AddEventListenerOptions)=>{
      if(type==='keydown'){
        // 页面级快捷键覆盖初始焦点，外层Vue弹窗拥有自己的键盘操作。
        const scopedListener:EventListener=event=>{const element=event.target instanceof Element?event.target:null;if(element&&!root.contains(element)&&element.closest('[role=dialog],dialog,[data-slot=dialog-content]'))return;if(typeof listener==='function')listener(event);else listener.handleEvent(event);};
        listen(owner,type,scopedListener,options,listener);
      }else listen(['pointerdown','scroll'].includes(type)?owner:root,type,listener,options);
    };
    if(key==='removeEventListener')return unlisten;
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }});
  let terminalClass:typeof Terminal,fitClass:typeof FitAddon;
  let vendor:Promise<void>|undefined;
  const localValues:Record<PropertyKey,unknown>={loadRuntimeTerminal:()=>vendor??=(async()=>{const [terminal,fit]=await Promise.all([import('xterm'),import('xterm-addon-fit')]);terminalClass=terminal.Terminal;fitClass=fit.FitAddon;})(),nativeEnvironmentWorkspace:(id:number)=>{if(!disposed)receive({type:'runtime:environment-details',id});},nativePagination:(pagination:RuntimePagination)=>{if(!disposed)receive({type:'runtime:pagination',pagination});}};
  const scopedWindow = new Proxy(window, {get(target,key){
    if(key in localValues)return localValues[key];
    if(key==='parent')return {location:window.location,document:owner,postMessage:(message:RuntimeMessage)=>{if(!disposed)receive(message);}};
    if(key==='location')return scopedLocation;
    if(key==='history')return scopedHistory;
    if(key==='addEventListener')return (type:string,listener:EventListenerOrEventListenerObject,options?:boolean|AddEventListenerOptions)=>listen(['hashchange','pagehide'].includes(type)?localEvents:window,type,listener,options);
    if(key==='removeEventListener')return unlisten;
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  },set(_target,key,value){localValues[key]=value;return true;}});
  /** 将读写连接交给宿主释放，服务器已提交的事务继续按原状态恢复。@param input 接口。@param options 请求设置。@return HTTP回执。 */
  async function scopedFetch(input:RequestInfo|URL,options:RequestInit={}):Promise<Response>{if(disposed)throw new DOMException('工作区已关闭','AbortError');const controller=new AbortController();requests.add(controller);const abort=()=>controller.abort();if(options.signal?.aborted)abort();else options.signal?.addEventListener('abort',abort,{once:true});try{const response=await fetch(input,{...options,signal:controller.signal});const cleanup=()=>{requests.delete(controller);options.signal?.removeEventListener('abort',abort);};const json=response.json.bind(response),text=response.text.bind(response);response.json=()=>json().finally(cleanup);response.text=()=>text().finally(cleanup);if(!response.body)cleanup();return response;}catch(error){requests.delete(controller);options.signal?.removeEventListener('abort',abort);throw error;}}
  /** DOM观察与宿主共同释放，迟到回调失效。 */
  class ScopedMutationObserver extends MutationObserver {
    /** 创建观察器。@param callback DOM变化回调。@return 作用域观察器。 */
    constructor(callback:MutationCallback){super((records,observer)=>{if(!disposed)callback(records,observer);});observers.add(this);} }
  /** 尺寸观察限定当前路由生命周期。 */
  class ScopedResizeObserver extends ResizeObserver {
    /** 创建尺寸观察器。@param callback 尺寸回调。@return 作用域观察器。 */
    constructor(callback:ResizeObserverCallback){super((entries,observer)=>{if(!disposed)callback(entries,observer);});observers.add(this);} }
  /** 终端连接由当前宿主登记和释放。 */
  class ScopedWebSocket extends WebSocket {
    /** 登记终端连接。@param url 可信终端地址。@param protocols 子协议。@return WebSocket实例。 */
    constructor(url:string|URL,protocols?:string|string[]){super(url,protocols);sockets.add(this);this.addEventListener('close',()=>sockets.delete(this),{once:true});} }
  /** 实时记录订阅由当前宿主登记和释放。 */
  class ScopedEventSource extends EventSource {
    /** 登记记录订阅。@param url 流地址。@param options 连接选项。@return SSE实例。 */
    constructor(url:string|URL,options?:EventSourceInit){super(url,options);sources.add(this);}
    /** 结束订阅并解除宿主引用。@return 无。 */
    override close():void{super.close();sources.delete(this);}
  }
  /** 授权或续聊时才加载终端，实例归当前路由释放。 */
  class ScopedTerminal {
    /** 创建已加载终端。@param options 原终端设置。@return xterm实例。 */
    constructor(options?:ConstructorParameters<typeof Terminal>[0]){const terminal=new terminalClass(options);terminals.add(terminal);const dispose=terminal.dispose.bind(terminal);terminal.dispose=()=>{terminals.delete(terminal);dispose();};return terminal;} }
  /** 与终端同批加载尺寸适配插件。 */
  class ScopedFitAddon {
    /** 创建匹配版本插件。@return 尺寸插件。 */
    constructor(){return new fitClass();} }
  const scope = {document:scopedDocument,window:scopedWindow,location:scopedLocation,history:scopedHistory,fetch:scopedFetch,MutationObserver:ScopedMutationObserver,ResizeObserver:ScopedResizeObserver,WebSocket:ScopedWebSocket,EventSource:ScopedEventSource,Terminal:ScopedTerminal,FitAddon:{FitAddon:ScopedFitAddon},
    setTimeout:(callback:()=>void,delay?:number)=>{if(disposed)return 0;const id=window.setTimeout(()=>{timers.delete(id);if(!disposed)callback();},delay);timers.add(id);return id;},
    clearTimeout:(id:number)=>{timers.delete(id);window.clearTimeout(id);},
    setInterval:(callback:()=>void,delay?:number)=>{if(disposed)return 0;const id=window.setInterval(()=>{if(!disposed)callback();},delay);intervals.add(id);return id;},
    clearInterval:(id:number)=>{intervals.delete(id);window.clearInterval(id);},
    requestAnimationFrame:(callback:FrameRequestCallback)=>{if(disposed)return 0;const id=window.requestAnimationFrame(time=>{frames.delete(id);if(!disposed)callback(time);});frames.add(id);return id;},
    cancelAnimationFrame:(id:number)=>{frames.delete(id);window.cancelAnimationFrame(id);},
  };
  // 同一页签的锚点也由宿主处理，避免浏览器额外写入顶层hash。
  listen(root,'click',((event:MouseEvent)=>{const link=(event.target as Element).closest<HTMLAnchorElement>('a[href^="#"]');if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||event.button!==0)return;event.preventDefault();navigate(link.getAttribute('href')!);}) as EventListener,true);
  return {scope,
    /** 在保留路由和模块实例的情况下回读当前分区。@return 无。 */
    refresh():void{if(!disposed)localEvents.dispatchEvent(new Event('hashchange'));},
    /** 将Vue地址同步到模块，不创建第二份浏览器历史。@param hash 内部地址。@return 无。 */
    setRoute(hash:string):void{if(disposed||locationValue.hash===hash)return;locationValue.hash=hash;localEvents.dispatchEvent(new Event('hashchange'));},
    /** 离开路由后释放全部宿主资源，服务端会话由原恢复协议继续管理。@return 无。 */
    dispose():void{if(disposed)return;disposed=true;localEvents.dispatchEvent(new Event('pagehide'));for(const value of listeners)value.target.removeEventListener(value.type,value.listener,value.options);for(const id of timers)window.clearTimeout(id);for(const id of intervals)window.clearInterval(id);for(const id of frames)window.cancelAnimationFrame(id);for(const observer of observers)observer.disconnect();for(const request of requests)request.abort();for(const source of sources)source.close();for(const socket of sockets)socket.close();for(const terminal of terminals){try{terminal.dispose();}catch{}}},
  };
}
