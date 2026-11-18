<script setup lang="ts">
import { computed, ref, watch, nextTick, defineAsyncComponent, onMounted, onUnmounted } from 'vue';
import { Menu, PanelLeftClose, PanelLeftOpen, ChevronRight, LogOut, X } from '@/components/ui/icon';
import AppNavigation from './AppNavigation.vue';
import { api } from '../api';
import { releaseVersion } from '../lib/platformVersion';
import { usePlatformVersion } from '../composables/usePlatformVersion';
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogTrigger } from '@/components/ui/dialog';
import { useRoute } from 'vue-router';
import { Button } from '@/components/ui/button';
import { logout } from '../router';
import { useToast } from '../composables/useToast';

const route = useRoute();
const nativeTasks = computed(() => route.name === 'tasks');
/** 读取本机侧栏偏好，存储不可用时保留默认展开。@return 是否折叠。 */
function savedCollapsed(): boolean { try { return localStorage.getItem('flower2api-sidebar-collapsed') === 'true'; } catch { return false; } }
const collapsed = ref(savedCollapsed());
watch(collapsed, value => { try { localStorage.setItem('flower2api-sidebar-collapsed', String(value)); } catch { /* 隐私模式仍保持本次会话选择。 */ } });
const mobileOpen = ref(false);
const { version: runtimeVersion, refresh: refreshPlatformVersion } = usePlatformVersion();
const installedVersion = ref<string | null>(null);
const currentVersion = computed(() => runtimeVersion.value ?? installedVersion.value);
const updateAvailable = ref(false);
const accountCount = ref<number | null>(null);
const runningCount = ref<number | null>(null);
const metadataController = new AbortController();
let metadataAt = 0;
let metadataLoading = false;
let updateLoading = false;
let updateTimer: ReturnType<typeof setTimeout> | undefined;
/** 读取受信目录，首次进入时检查新版，并跟进后台检查结果。@param checkUpdates 是否发起检查。@return 读取完成。 */
async function refreshUpdateMetadata(checkUpdates=false): Promise<void> {
 if(updateLoading || metadataController.signal.aborted)return;
 updateLoading=true;
 clearTimeout(updateTimer);
 try {
  const status=await api.systemUpdateStatus(metadataController.signal);
  if(metadataController.signal.aborted)return;
  if(!status.installed){installedVersion.value=null;updateAvailable.value=false;return;}
  const catalog=await api.systemUpdateReleases(metadataController.signal);
  if(metadataController.signal.aborted)return;
  const installed=catalog.releases.find(item=>item.release===status.current_release);
  installedVersion.value=installed ? releaseVersion(installed.changes) : null;
  updateAvailable.value=!!catalog.releases[0] && catalog.releases[0].release!==status.current_release;
  // 检查异步执行，短暂轮询才能让首页角标及时反映新目录。
  if(checkUpdates && !catalog.checking && !status.busy)await api.systemUpdateCheck();
  if(!metadataController.signal.aborted && (catalog.checking || (checkUpdates && !status.busy))){
   updateTimer=setTimeout(()=>{void refreshUpdateMetadata();},2000);
  }
 } catch { /* 自动检查失败时保留已读取版本，手动更新面板展示具体错误。 */ }
 finally { updateLoading=false; }
}
/** 读取品牌与角标的真实摘要，页面切换复用30秒快照。@param force 强制刷新。@param checkUpdates 是否检查新版。@return 读取完成。 */
async function refreshMetadata(force=false,checkUpdates=false): Promise<void> {
 if(metadataLoading || metadataController.signal.aborted || (!force && Date.now()-metadataAt<30000))return;
 metadataLoading=true;metadataAt=Date.now();
 // 管理桥校验独立Cookie；共享签发完成后读取，首次登录也遵守同一鉴权顺序。
 const session=api.openRuntime();
 const results=await Promise.allSettled([api.getDashboard(),session.then(()=>refreshUpdateMetadata(checkUpdates)),session.then(()=>api.runtimeSummary(metadataController.signal)),session.then(()=>refreshPlatformVersion(metadataController.signal))]);
 if(!metadataController.signal.aborted){
  if(results[0].status==='fulfilled')accountCount.value=results[0].value.accounts.total;
  if(results[2].status==='fulfilled')runningCount.value=results[2].value.active_runs;
 }
 metadataLoading=false;
}
onMounted(()=>{void refreshMetadata(false,true);});
onUnmounted(()=>{clearTimeout(updateTimer);metadataController.abort();});
watch(()=>route.fullPath,()=>{void refreshMetadata();});
const titles: Record<string, string> = { proxies: '代理管理', updates: '系统更新', environments: '运行环境', tasks: '任务与工程', accounts: '账号', requests: '请求记录', tokens: '访问令牌', settings: '系统设置' };
const pageTitle = computed(() => titles[String(route.name)] ?? '管理控制台');
watch(() => route.fullPath, () => { mobileOpen.value = false; });
const toast = useToast();
const loggingOut = ref(false);

/** 完成统一退出；服务异常时展示错误并允许重试。@return 退出操作完成。 */
async function handleLogout(): Promise<void> {
  if (loggingOut.value) return;
  loggingOut.value = true;
  try {
    await logout();
  } catch (error) {
    toast.show(error instanceof Error ? error.message : '退出失败，请重试');
  } finally {
    loggingOut.value = false;
  }
}

const SystemUpdates = defineAsyncComponent(() => import('./SystemUpdates.vue'));
const updatePanel = ref<HTMLDialogElement | null>(null);
const updatesOpen = ref(false);
/** 从品牌打开更新工作区，保留当前页面；修饰键沿用独立深链接。@param event 链接点击。@return 面板打开完成。 */
async function openUpdatePanel(event: MouseEvent): Promise<void> {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  mobileOpen.value = false;
  updatesOpen.value = true;
  await nextTick();
  updatePanel.value?.showModal();
}
/** 关闭更新面板并卸载轮询。@return 无。 */
function closeUpdatePanel(): void { const wasOpen=updatesOpen.value;updatePanel.value?.close();updatesOpen.value = false;if(wasOpen)void refreshMetadata(true); }
watch(() => route.fullPath, closeUpdatePanel);
</script>

<template>
  <div class="console-shell" :class="{ 'sidebar-collapsed': collapsed, 'console-native-tasks': nativeTasks }">
    <aside class="console-sidebar" aria-label="侧边栏">
      <div class="console-brand-row">
        <router-link :to="{ name: 'accounts' }" class="console-brand" aria-label="flower2api 首页">
          <img src="/favicon.svg?v=flower2api-pink-04" alt="flower2api 标志" class="size-7 shrink-0" />
          <span class="sidebar-label"><strong>flower2api</strong></span>
        </router-link>
        <a href="/updates" class="brand-update" aria-label="系统更新" :class="{'has-update': updateAvailable}" :title="updateAvailable ? '系统更新 · 有可用新版' : '系统更新'" @click="openUpdatePanel">
          <span v-if="!collapsed">{{ currentVersion ?? '版本' }}</span><ChevronRight class="size-3" />
        </a>
      </div>
      <p class="sidebar-tagline sidebar-label">让每一次调用井然有序</p>
      <AppNavigation :collapsed="collapsed" :account-count="accountCount" :running-count="runningCount" />
      <div class="sidebar-footer">
        <span class="sidebar-avatar" aria-hidden="true">管</span>
        <div class="sidebar-label sidebar-identity"><strong>管理员</strong><small>本地管理控制台</small></div>

        <Button variant="ghost" size="icon" class="desktop-sidebar-toggle" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" :aria-expanded="!collapsed" @click="collapsed = !collapsed">
          <PanelLeftOpen v-if="collapsed" class="size-4" /><PanelLeftClose v-else class="size-4" />
        </Button>

        <Button variant="ghost" size="icon" @click="handleLogout" :disabled="loggingOut" class="sidebar-exit" aria-label="退出" title="退出"><LogOut class="size-4" /></Button>
      </div>
    </aside>
    <div class="console-workspace">
      <header class="console-toolbar">
        <Dialog v-model:open="mobileOpen">
          <DialogTrigger as-child><Button variant="ghost" size="icon" class="mobile-sidebar-toggle" aria-label="打开主导航"><Menu class="size-5" /></Button></DialogTrigger>
          <DialogContent class="mobile-navigation-panel" :aria-describedby="undefined">
            <DialogTitle>flower2api</DialogTitle>
            <a href="/updates" class="brand-update" aria-label="系统更新" :class="{'has-update': updateAvailable}" :title="updateAvailable ? '系统更新 · 有可用新版' : '系统更新'" @click="openUpdatePanel">{{ currentVersion ?? '系统更新' }}<ChevronRight class="size-3" /></a>
            <DialogDescription class="sr-only">选择管理页面</DialogDescription>
            <AppNavigation :account-count="accountCount" :running-count="runningCount" @navigate="mobileOpen = false" />
            <Button variant="outline" @click="handleLogout" :disabled="loggingOut"><LogOut class="size-4" />退出</Button>
          </DialogContent>
        </Dialog>
        <span class="toolbar-page">{{ pageTitle }}</span>
        <span class="toolbar-brand">flower2api</span>
      </header>
      <!-- 嵌入工作区沿用自己的滚动容器；折叠侧栏只改变宽度，保留文档身份。 -->
      <main id="console-content" class="console-content space-y-6">
      <!-- 子路由内容 -->
      <router-view />
      </main>
    </div>
    <dialog ref="updatePanel" class="approved-update-dialog" aria-labelledby="system-update-panel-title" @close="updatesOpen = false" @click="event => { if (event.target === updatePanel) closeUpdatePanel(); }">
      <header class="approved-update-head"><div><h2 id="system-update-panel-title">系统更新</h2><p>flower2api · 应用与运行组件</p></div><button type="button" aria-label="关闭更新面板" @click="closeUpdatePanel"><X :size="18" /></button></header>
      <div class="approved-update-scroll"><SystemUpdates v-if="updatesOpen" embedded /></div>
    </dialog>
  </div>
</template>
