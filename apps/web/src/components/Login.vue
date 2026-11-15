<script setup lang="ts">
import { ref } from 'vue';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { login } from '../router';

/** 密码输入值 */
const password = ref('');
/** 错误信息 */
const error = ref('');
/** 登录请求加载状态 */
const loading = ref(false);

/** 提交登录表单 */
async function submit() {
  if (!password.value.trim()) {
    error.value = '请输入密码';
    return;
  }
  error.value = '';
  loading.value = true;
  try {
    await login(password.value.trim());
  } catch {
    error.value = '密码错误';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-intro" aria-label="控制台介绍">
      <img src="/favicon.svg?v=flower2api-pink-04" alt="" aria-hidden="true" class="size-12" />
      <h1>flower2api</h1><p>账号、环境与任务，一个清晰的工作空间。</p>
    </section>
    <div class="login-form-area">
      <Card>
        <CardHeader class="px-0 pb-6">
          <img src="/favicon.svg?v=flower2api-pink-04" alt="flower2api 标志" class="size-10 mb-4" />
          <CardTitle class="text-2xl font-semibold tracking-tight">登录控制台</CardTitle>
          <p class="page-description">输入管理员密码，继续管理你的工作空间</p>
        </CardHeader>
        <CardContent class="px-0">
          <form @submit.prevent="submit" class="space-y-5">
            <div class="space-y-2"><label for="admin-password" class="text-sm font-medium">管理员密码</label>
              <Input id="admin-password" v-model="password" type="password" autocomplete="current-password" placeholder="管理员密码" class="h-11" />
            </div>
            <p v-if="error" role="alert" class="text-red-600 text-sm">{{ error }}</p>
            <Button type="submit" :disabled="loading" class="w-full h-11">{{ loading ? '登录中...' : '登录' }}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
