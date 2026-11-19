<script setup lang="ts">
import { useRoute } from 'vue-router';
import { Users, Activity, KeyRound, Boxes, Server, ListTodo, Settings2, Globe, ShieldCheck } from '@/components/ui/icon';

/** 主导航复用于桌面侧栏与移动抽屉，保证两个入口集合一致；「系统设置」单独成组位于底部（主题设置随其页面加入同组）。 */
defineProps<{ collapsed?: boolean; accountCount?: number | null; runningCount?: number | null }>();
const emit = defineEmits<{ navigate: [] }>();
const route = useRoute();
const groups = [
  { label: '网关', items: [{ name: 'accounts', label: '账号', icon: Users }, { name: 'requests', label: '请求记录', icon: Activity }, { name: 'session-blocks', label: '会话封禁', icon: ShieldCheck }, { name: 'tokens', label: '访问令牌', icon: KeyRound }] },
  { label: '资源', items: [{ name: 'proxies', label: '代理管理', icon: Globe }, { name: 'environments', label: '运行环境', icon: Boxes }, { name: 'nodes', label: '节点管理', icon: Server }] },
  { label: '工作区', items: [{ name: 'tasks', label: '任务与工程', icon: ListTodo }] },
  { label: '', items: [{ name: 'settings', label: '系统设置', icon: Settings2 }] },
];
</script>

<template>
  <nav class="console-navigation" aria-label="主导航">
    <div v-for="group in groups" :key="group.label" class="navigation-group" :class="{'navigation-system': !group.label}">
      <p v-if="group.label" class="navigation-group-label" :class="{ 'sr-only': collapsed }">{{ group.label }}</p>
      <router-link v-for="link in group.items" :key="link.name" :to="{ name: link.name }" class="navigation-item"
        :class="{ 'is-active': route.name === link.name }" :title="collapsed ? link.label : undefined"
        :aria-label="link.label" :aria-current="route.name === link.name ? 'page' : undefined" @click="emit('navigate')">
        <component :is="link.icon" class="size-[18px] shrink-0" /><span class="sidebar-label">{{ link.label }}</span><b v-if="link.name==='accounts' && accountCount!=null" class="navigation-count sidebar-label">{{ accountCount }}</b><span v-if="link.name==='tasks' && runningCount!=null" class="navigation-running sidebar-label" :data-idle="runningCount === 0">{{ runningCount }}</span>
      </router-link>
    </div>
  </nav>
</template>
