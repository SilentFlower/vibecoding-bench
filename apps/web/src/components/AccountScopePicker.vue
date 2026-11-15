<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronRight, Search, X } from '@/components/ui/icon';
import type { Account } from '../api';
/** 令牌权限范围选择器，保留CSV接口及暂时不可见的已选账号。 */
const props = defineProps<{ modelValue: string; accounts: Account[]; label: string; help: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const open = ref(false);
const query = ref('');
const selected = computed(() => [...new Set(props.modelValue.split(',').map(value => value.trim()).filter(Boolean))]);
const options = computed(() => props.accounts.filter(account => `${account.name} ${account.email}`.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())));
/** 只更新当前草稿，取消由父编辑器处理。@param id 账号身份。@return 无。 */
function toggle(id: string): void { const ids = selected.value.includes(id) ? selected.value.filter(value => value !== id) : [...selected.value,id]; emit('update:modelValue',ids.join(',')); }
/** 历史已选账号也可移除，列表缺失不自动丢弃权限。@param id 原身份。@return 显示名称。 */
function name(id: string): string { const account = props.accounts.find(value => String(value.id) === id); return account?.name || account?.email || `账号 #${id}`; }
</script>
<template>
  <fieldset class="account-picker"><legend class="picker-label">{{ label }}<span class="picker-count">{{ selected.length ? `${selected.length} 个已选` : '未限制' }}</span></legend><div class="picker-selected"><span v-for="id in selected" :key="id" class="account-chip">{{ name(id) }}<button type="button" :aria-label="`移除${label}中的${name(id)}`" @click="toggle(id)"><X :size="12" /></button></span></div>
    <button type="button" class="picker-trigger" :aria-expanded="open" @click="open = !open"><span>{{ open ? '收起账号列表' : '选择账号' }}</span><ChevronRight :size="12" /></button><p class="picker-help">{{ help }}</p>
    <div v-if="open" class="picker-options"><label class="picker-search"><Search :size="14" /><input v-model="query" :aria-label="`搜索${label}`" placeholder="搜索名称或邮箱" type="search" @keydown.esc.stop.prevent="open = false" /></label><div class="picker-list"><label v-for="account in options" :key="account.id" class="picker-option"><input type="checkbox" :checked="selected.includes(String(account.id))" @change="toggle(String(account.id))" /><span class="picker-avatar">{{ (account.name || account.email).slice(0,1) }}</span><span><strong>{{ account.name || account.email }}</strong><small>{{ account.email }}</small></span></label><p v-if="!options.length" class="picker-empty">没有匹配的账号</p></div></div>
  </fieldset>
</template>
