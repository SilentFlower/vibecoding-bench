<script setup lang="ts">
import { computed, ref, watch, defineAsyncComponent, onMounted, onUnmounted } from 'vue';
import { Menu, PanelLeftClose, PanelLeftOpen, ChevronRight, LogOut, ArrowUpCircle } from '@/components/ui/icon';
import AppNavigation from './AppNavigation.vue';
import { api } from '../api';
import { releaseVersion } from '../lib/platformVersion';
import { usePlatformVersion } from '../composables/usePlatformVersion';
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogTrigger } from '@/components/ui/dialog';
import { useRoute, useRouter } from 'vue-router';
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
// 移动端应用栏显示的页面标题，与各页页头一致。
const titles: Record<string, string> = { accounts: '账号管理', requests: '请求记录', 'session-blocks': '会话封禁', tokens: '访问令牌', proxies: '代理管理', environments: '运行环境', nodes: '节点管理', tasks: '任务与工程', settings: '系统设置', updates: '系统更新' };
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

const SystemUpdateDialog = defineAsyncComponent(() => import('./SystemUpdateDialog.vue'));
const router = useRouter();
// 直接访问 /updates 时背后是账号页，弹窗自动打开；导航到其他页面时关闭。
const updatesOpen = ref(route.name === 'updates');
/** 从版本号打开更新弹窗，地址保持不变；修饰键沿用独立深链接。@param event 链接点击。@return 无。 */
function openUpdatePanel(event: MouseEvent): void {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  mobileOpen.value = false;
  updatesOpen.value = true;
}
watch(() => route.fullPath, () => { updatesOpen.value = route.name === 'updates'; });
// 弹窗关闭即卸载轮询并刷新版本号角标；从 /updates 进入的回到账号页。
watch(updatesOpen, value => {
  if (value) return;
  void refreshMetadata(true);
  if (route.name === 'updates') void router.replace({ name: 'accounts' });
});
</script>

<template>
  <div class="console-shell" :class="{ 'sidebar-collapsed': collapsed, 'console-native-tasks': nativeTasks }">
    <aside class="console-sidebar" aria-label="侧边栏">
      <div class="console-brand-row">
        <router-link :to="{ name: 'accounts' }" class="console-brand-mark" aria-label="flower2api 首页"><img src="/favicon.svg?v=flower2api-pink-04" alt="flower2api 标志" width="24" height="24" /></router-link>
        <strong class="console-brand-name sidebar-label">flower2api</strong>
        <a href="/updates" class="brand-update" aria-label="系统更新" :class="{'has-update': updateAvailable}" :title="updateAvailable ? '系统更新 · 有可用新版' : '系统更新'" @click="openUpdatePanel">
          <template v-if="!collapsed">{{ currentVersion ?? '版本' }}<ArrowUpCircle v-if="updateAvailable" /></template>
          <template v-else><ArrowUpCircle v-if="updateAvailable" /><ChevronRight v-else /></template>
        </a>
        <small class="sidebar-tagline sidebar-label">让每一次调用井然有序</small>
      </div>
      <AppNavigation :collapsed="collapsed" :account-count="accountCount" :running-count="runningCount" />
      <div class="sidebar-footer">
        <span class="sidebar-avatar" aria-hidden="true">管</span>
        <div class="sidebar-label sidebar-identity"><strong>管理员</strong><small>本地管理控制台</small></div>
        <div class="sidebar-tools">
          <button type="button" class="sidebar-tool desktop-sidebar-toggle" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" :aria-expanded="!collapsed" :title="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="collapsed = !collapsed">
            <PanelLeftOpen v-if="collapsed" /><PanelLeftClose v-else />
          </button>
          <button type="button" class="sidebar-tool sidebar-exit" :disabled="loggingOut" aria-label="退出" title="退出" @click="handleLogout"><LogOut /></button>
        </div>
      </div>
    </aside>
    <div class="console-workspace">
      <header class="console-toolbar">
        <span class="console-toolbar-mark" aria-hidden="true"><img src="/favicon.svg?v=flower2api-pink-04" alt="" width="20" height="20" /></span>
        <span class="toolbar-page">{{ pageTitle }}</span>
        <Dialog v-model:open="mobileOpen">
          <DialogTrigger as-child><button type="button" class="mobile-sidebar-toggle" aria-label="打开主导航"><Menu /></button></DialogTrigger>
          <!-- 抽屉：工具类覆盖 DialogContent 的居中定位与尺寸（cn 合并会去掉冲突类），外观见 console-shell.css。 -->
          <DialogContent class="mobile-navigation-panel flex flex-col top-0 left-0 translate-x-0 translate-y-0 w-[min(300px,88vw)] max-w-none sm:max-w-none data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left" :aria-describedby="undefined">
            <div class="console-brand-row">
              <span class="console-brand-mark" aria-hidden="true"><img src="/favicon.svg?v=flower2api-pink-04" alt="" width="24" height="24" /></span>
              <DialogTitle class="console-brand-name">flower2api</DialogTitle>
              <a href="/updates" class="brand-update" aria-label="系统更新" :class="{'has-update': updateAvailable}" :title="updateAvailable ? '系统更新 · 有可用新版' : '系统更新'" @click="openUpdatePanel">{{ currentVersion ?? '系统更新' }}<ArrowUpCircle v-if="updateAvailable" /></a>
              <small class="sidebar-tagline">让每一次调用井然有序</small>
            </div>
            <DialogDescription class="sr-only">选择管理页面</DialogDescription>
            <AppNavigation :account-count="accountCount" :running-count="runningCount" @navigate="mobileOpen = false" />
            <div class="sidebar-footer">
              <span class="sidebar-avatar" aria-hidden="true">管</span>
              <div class="sidebar-identity"><strong>管理员</strong><small>本地管理控制台</small></div>
              <div class="sidebar-tools"><button type="button" class="sidebar-tool" :disabled="loggingOut" aria-label="退出" title="退出" @click="handleLogout"><LogOut /></button></div>
            </div>
          </DialogContent>
        </Dialog>
      </header>
      <!-- 嵌入工作区沿用自己的滚动容器；折叠侧栏只改变宽度，保留文档身份。 -->
      <main id="console-content" class="console-content">
      <!-- 子路由内容 -->
      <router-view />
      </main>
    </div>
    <SystemUpdateDialog v-if="updatesOpen" v-model:open="updatesOpen" />
  </div>
</template>
