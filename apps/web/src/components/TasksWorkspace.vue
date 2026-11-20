<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, type ProxyRoute } from '../api';
import { Button } from './ui/button';
import { Pagination, InfoTooltip } from './ui/controls';
import { Globe } from './ui/icon';
import ProxyPicker from './ProxyPicker.vue';
import { useToast, type FeedbackType } from '../composables/useToast';
import { useConfirmation } from '../composables/useConfirmation';
import TaskProxyDialog from './runtime/TaskProxyDialog.vue';
import CaptureWorkspace from './runtime/CaptureWorkspace.vue';
import type { RunCapture } from './runtime/runApi';
import { createRuntimeScope, type RuntimeMessage, type RuntimePagination } from './runtime/runtimeScope';
import { template, mount } from 'virtual:task-runtime';
import 'xterm/css/xterm.css';
import 'virtual:task-runtime-style.css';

const { show: showFeedback } = useToast();
const { ask: askConfirmation } = useConfirmation();
const EnvironmentWorkspace=defineAsyncComponent(()=>import('./RuntimeEnvironments.vue'));
const environmentAccountId=ref<number|null>(null);
const AccountWorkspace=defineAsyncComponent(()=>import('./Accounts.vue'));
const workspaceAccountId=ref<number|null>(null);
const proxyTaskId=ref<number|null>(null),proxyTaskName=ref('');
const proxyTips=shallowRef<{host:HTMLElement;label:string;url:string}[]>([]);
let accountOpener:HTMLElement|null=null;
const RunDetails=defineAsyncComponent(()=>import('./runtime/RunDetails.vue'));
const route=useRoute(),router=useRouter(),root=ref<HTMLElement>(),error=ref(''),ready=ref(false);
const taskTabs=['accounts','projects','warmup','tasks','runs','topics'];
/** 保留重复与空查询参数，由原控制器校验，避免无效账号链接回落到首个账号。@return 原生工作区路由。 */
const hash=computed(()=>{const tab=typeof route.query.tab==='string'&&taskTabs.includes(route.query.tab)?route.query.tab:'accounts';const query=new URLSearchParams();for(const key of ['account','environment','gateway_account','section']){const value=route.query[key];if(value===undefined)continue;for(const item of Array.isArray(value)?value:[value])query.append(key,item??'');}return `#${tab}${query.size?'?'+query:''}`;});
const runDetails=ref<{id:string;title:string;accountName:string}|null>(null);
const loginHost=shallowRef<HTMLElement|null>(null),loginProxy=ref<ProxyRoute|null|undefined>(),loginLabel=ref('直连'),loginDisabled=ref(false);
const captureHost=shallowRef<HTMLElement|null>(null),capture=ref<RunCapture|null>(null),captureUrl=ref('');
const pagers=shallowRef<{host:HTMLElement;state:RuntimePagination}[]>([]);
const paginationStates=new Map<string,RuntimePagination>();
let scope:ReturnType<typeof createRuntimeScope>|undefined,controller:ReturnType<typeof mount>|undefined,observer:MutationObserver|undefined,alive=true,connecting=false,capturePayload='';
/** 目录选择仅提交稳定ID及版本，私有连接留在Rust桥。@param value 当前线路。@return 无。 */
function chooseProxy(value:ProxyRoute|null):void{loginProxy.value=value;if(loginHost.value)loginHost.value.dataset.proxyChoice=JSON.stringify(value?{id:value.id,revision:value.revision}:null);}
/** 将控制器事件交给同一路由或Vue工作区。@param message 模块事件。@return 无。 */
function receive(message:RuntimeMessage):void{
  if(!alive)return;
  if(message.type==='runtime:ready'){synchronizeHosts();ready.value=true;return;}
  if(message.type==='runtime:pagination'&&message.pagination){paginationStates.set(message.pagination.kind,message.pagination);synchronizeHosts();return;}
  if(message.type==='runtime:environment-details'&&Number.isSafeInteger(message.id)&&Number(message.id)>0){accountOpener=document.activeElement instanceof HTMLElement?document.activeElement:null;environmentAccountId.value=Number(message.id);return;}
  if(message.type==='runtime:task-proxy'&&Number.isSafeInteger(message.id)&&Number(message.id)>0){accountOpener=document.activeElement instanceof HTMLElement?document.activeElement:null;proxyTaskId.value=Number(message.id);proxyTaskName.value=message.title||'';return;}
  if(message.type==='runtime:account-edit'&&Number.isSafeInteger(message.id)&&Number(message.id)>0){accountOpener=document.activeElement instanceof HTMLElement?document.activeElement:null;workspaceAccountId.value=Number(message.id);return;}
  if(message.type==='runtime:run-detail'&&typeof message.id==='string'&&/^[a-zA-Z0-9_-]{1,128}$/.test(message.id)){runDetails.value={id:message.id,title:message.title?.slice(0,200)||'运行详情',accountName:message.accountName?.slice(0,200)||''};return;}
  if(message.type!=='runtime:navigate'||!message.tab||!['environments',...taskTabs].includes(message.tab))return;
  const query:Record<string,string>={};if(!['environments','accounts'].includes(message.tab))query.tab=message.tab;
  for(const key of ['account','environment','gateway_account','section'] as const)if(typeof message[key]==='string')query[key]=message[key];
  const target={name:message.tab==='environments'?'environments':'tasks',query};void(message.replace?router.replace(target):router.push(target));
}
/** 为共享Vue控件保留稳定宿主，执行模块只管理其余内容。@return 无。 */
function synchronizeHosts():void{
  const host=root.value;if(!host)return;
  const tips=[...host.querySelectorAll<HTMLElement>('[data-task-proxy-id]')].map(target=>{if(!target.hasAttribute('data-vue-managed')){target.replaceChildren();target.dataset.vueManaged='';}return {host:target,label:target.dataset.proxyLabel||'代理待读取',url:target.dataset.proxyUrl||''};});
  if(tips.length!==proxyTips.value.length||tips.some((tip,index)=>tip.host!==proxyTips.value[index]?.host||tip.label!==proxyTips.value[index]?.label||tip.url!==proxyTips.value[index]?.url))proxyTips.value=tips;
  const login=host.querySelector<HTMLElement>('#acc-modal:not(.hidden) .acc-step-config:not(.hidden) #runtime-login-proxy');
  if(login!==loginHost.value){loginHost.value=login;loginProxy.value=undefined;if(login){login.dataset.managed='true';login.dataset.vueManaged='';loginLabel.value=login.dataset.proxyLabel||'直连';loginDisabled.value=login.dataset.proxyDisabled==='true';}}
  const current=host.querySelector<HTMLElement>('#work-capture-modal:not(.hidden) #work-capture-view[data-capture-payload]');
  if(current!==captureHost.value){captureHost.value=current;if(current)current.dataset.vueManaged='';capturePayload='';capture.value=null;}
  if(current?.dataset.capturePayload&&current.dataset.capturePayload!==capturePayload){const url=current.dataset.captureUrl??'';if(/^\/runtime\/api\/(?:projects|accounts\/warmup\/pi)\/work\/[A-Za-z0-9_-]+\/capture\/file$/.test(url)){try{capture.value=JSON.parse(current.dataset.capturePayload) as RunCapture;captureUrl.value=url;capturePayload=current.dataset.capturePayload;}catch{capture.value=null;}}}
  const next:typeof pagers.value=[];
  for(const kind of ['events','history']){const target=host.querySelector(`#projects-${kind}-page`)?.parentElement;if(!target)continue;let container=target.querySelector<HTMLElement>('.native-pagination-host');if(!container){container=host.ownerDocument.createElement('div');container.className='native-pagination-host';container.dataset.vueManaged='';target.append(container);target.dataset.vuePagination='true';}const state=paginationStates.get(kind);if(state)next.push({host:container,state});}
  if(next.length!==pagers.value.length||next.some((item,index)=>item.host!==pagers.value[index]?.host||item.state!==pagers.value[index]?.state))pagers.value=next;
}
/** 公共组件发送翻页意图，原控制器负责游标、快照与失败恢复。@param kind 记录分区。@param direction 原动作。@param size 新页大小。@return 无。 */
function pageAction(kind:string,direction:string,size?:number):void{const host=root.value;if(!host)return;if(size){const select=host.querySelector<HTMLSelectElement>(`#projects-${kind}-size`);if(select){select.value=String(size);select.dispatchEvent(new Event('change',{bubbles:true}));}}else host.querySelector<HTMLButtonElement>(`#projects-${kind}-${direction}`)?.click();}
/** 关闭局部配置并恢复任务卡片焦点，保存后重新读取原列表。@param refresh 是否刷新任务摘要。@return 无。 */
function closeAccount(refresh=false):void{workspaceAccountId.value=null;if(refresh)scope?.refresh();void nextTick(()=>{if(accountOpener?.isConnected)accountOpener.focus({preventScroll:true});});}
/** 代理保存后回读任务，原控制器增量更新卡片并保留焦点。@param refresh 是否已保存。@return 无。 */
function closeProxy(refresh=false):void{proxyTaskId.value=null;if(refresh){scope?.refreshAccounts();showFeedback('代理已切换','success');}void nextTick(()=>{if(accountOpener?.isConnected)accountOpener.focus({preventScroll:true});});}
/** 关闭运行详情并恢复对应列表入口焦点。@return 无。 */
function closeRun():void{const id=runDetails.value?.id;runDetails.value=null;void nextTick(()=>{if(id)root.value?.querySelector<HTMLElement>(`[data-detail="${CSS.escape(id)}"]`)?.focus({preventScroll:true});});}
/** 交换原管理会话后挂载同份模块，静态模板随构建分发。@return 连接结束。 */
async function connect():Promise<void>{
  if(connecting||!alive||!root.value)return;
  connecting=true;ready.value=false;error.value='';
  const host=root.value;
  controller?.dispose();scope?.dispose();observer?.disconnect();
  const body=host.ownerDocument.createElement('div');body.className='runtime-body work-console';body.innerHTML=template;
  host.replaceChildren(body);host.inert=true;
  try{
    await api.openRuntime();
    if(!alive)return;
    host.inert=false;
    scope=createRuntimeScope(host,body,hash.value,receive,{notify:(message,type)=>showFeedback(message,(['success','error','warning','info'].includes(type)?type:'info') as FeedbackType),confirm:(message,signal)=>askConfirmation({title:'确认操作',message,danger:true},signal)});observer=new MutationObserver(records=>{if(records.some(record=>record.type==='childList'||record.attributeName==='class'||record.attributeName==='data-capture-payload'||record.attributeName==='data-proxy-label'||record.attributeName==='data-proxy-url'))synchronizeHosts();});observer.observe(host,{subtree:true,childList:true,attributes:true,attributeFilter:['class','data-capture-payload','data-proxy-label','data-proxy-url']});controller=mount(scope.scope);synchronizeHosts();
  }catch(cause){if(alive){host.inert=true;error.value=(cause as Error).message;}}
  finally{connecting=false;}
}
watch(hash,value=>{environmentAccountId.value=null;workspaceAccountId.value=null;proxyTaskId.value=null;runDetails.value=null;scope?.setRoute(value);});
onMounted(()=>{void connect();});
onUnmounted(()=>{alive=false;observer?.disconnect();controller?.dispose();scope?.dispose();});
</script>
<template>
  <section class="tasks-native-route" :class="{'runtime-connecting':!ready}" data-native-run-details><p v-if="error" class="task-connect-error" role="alert">{{ error }} <Button variant="outline" @click="connect">重新连接</Button></p><p v-else-if="!ready" class="task-connect-loading" role="status">正在建立工作区连接…</p><div ref="root" class="task-runtime console-design embedded-tasks" :aria-busy="!ready" />
    <Teleport v-for="tip in proxyTips" :key="tip.host.dataset.taskProxyId" :to="tip.host"><InfoTooltip :label="`查看代理：${tip.label}`" :title="tip.label"><template #trigger><Globe :size="14" /><span class="work-proxy-name">{{ tip.label }}</span></template><p>{{ tip.url || (tip.label==='直连'?'使用直接网络连接':'代理信息待核对') }}</p></InfoTooltip></Teleport>
    <Teleport v-if="loginHost" :to="loginHost"><ProxyPicker :model-value="loginProxy" :current-label="loginLabel" :disabled="loginDisabled" :portal-target="loginHost.closest<HTMLElement>('#acc-modal')??loginHost" help="从代理管理选择线路，开始授权后应用" @update:model-value="chooseProxy" /></Teleport>
    <Teleport v-if="captureHost&&capture" :to="captureHost"><CaptureWorkspace :key="captureUrl" :capture="capture" :file-url="captureUrl" /></Teleport>
    <Teleport v-for="pager in pagers" :key="pager.state.kind" :to="pager.host"><Pagination :page="pager.state.page" :page-size="pager.state.size" :total="0" mode="cursor" :label="pager.state.kind==='events'?'交互记录分页':'工程记录分页'" :disabled="pager.state.loading" :has-next="pager.state.hasNext" :has-previous="pager.state.hasPrevious" :can-latest="pager.state.canLatest" @update:page="value=>pageAction(pager.state.kind,value>pager.state.page?'next':'previous')" @update:page-size="value=>pageAction(pager.state.kind,'size',value)" @latest="pageAction(pager.state.kind,'latest')" /></Teleport>
    <EnvironmentWorkspace v-if="environmentAccountId" :key="environmentAccountId" :workspace-task-account-id="environmentAccountId" @close="environmentAccountId=null;closeAccount(true)" />
    <AccountWorkspace v-if="workspaceAccountId" :key="workspaceAccountId" :workspace-account-id="workspaceAccountId" @close="closeAccount()" @refresh="closeAccount(true)" />
    <TaskProxyDialog v-if="proxyTaskId" :key="proxyTaskId" :account-id="proxyTaskId" :account-name="proxyTaskName" @close="closeProxy()" @saved="closeProxy(true)" />
    <RunDetails v-if="runDetails" :key="runDetails.id" :run-id="runDetails.id" :title="runDetails.title" :account-name="runDetails.accountName" @close="closeRun" />
  </section>
</template>
<style>
.console-native-tasks .console-content{padding:0;max-width:none}.task-runtime{min-width:0;width:100%}.runtime-connecting>.task-runtime{min-height:320px}.task-connect-loading,.task-connect-error{padding:12px 40px;background:var(--ui-color-fill-subtle);border-bottom:1px solid color-mix(in srgb, var(--ui-color-primary) 28%, var(--ui-color-surface));font-size:var(--ui-font-size-sm)}.task-runtime [data-vue-pagination=true]>:not(.native-pagination-host){display:none!important}.task-runtime .native-pagination-host{width:100%;min-width:0}.task-runtime .projects-pagination{padding-block:16px}.task-runtime .runtime-body{min-height:calc(100dvh - 24px)}
.task-runtime .work-proxy-compact>.fui-info-trigger{display:flex;align-items:center;gap:8px;min-width:0;max-width:100%;font-size:var(--ui-font-size-sm)}
</style>
