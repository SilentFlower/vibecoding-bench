<script setup lang="ts">
import { ref } from 'vue';
import { Input, InputGroup } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Eye, Lock } from '@/components/ui/icon';
import { login } from '../router';

/** 密码输入值 */
const password = ref('');
/** 错误信息 */
const error = ref('');
/** 登录请求加载状态 */
const loading = ref(false);
/** 是否以明文显示密码 */
const revealed = ref(false);

// 品牌区纹理沿用第一版 canvas 的几何（756×900 画布坐标）：五瓣花的中心、尺寸、透明度，以及以首朵花为圆心的 9 道同心圆。
const flowers = [
  { x: 560, y: 230, size: 150, alpha: 0.16 },
  { x: 690, y: 520, size: 70, alpha: 0.1 },
  { x: 470, y: 470, size: 40, alpha: 0.12 },
  { x: 640, y: 790, size: 110, alpha: 0.07 },
];
const rings = Array.from({ length: 9 }, (_, index) => 60 + index * 52);

/**
 * 以花心为原点、指向上方的单片花瓣路径（与第一版 canvas 的贝塞尔曲线一致）。
 * @param size 花瓣长度。
 * @return SVG path 数据。
 */
function petalPath(size: number): string {
  const side = size * 0.45;
  return `M0 0C${-side} ${-size * 0.35} ${-side} ${-size} 0 ${-size}C${side} ${-size} ${side} ${-size * 0.35} 0 0Z`;
}

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
    <section class="login-art" aria-label="控制台介绍">
      <svg class="login-art-pattern" viewBox="0 0 756 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g class="login-art-petals">
          <template v-for="flower in flowers" :key="flower.x">
            <path v-for="petal in 5" :key="petal" :d="petalPath(flower.size)" :fill-opacity="flower.alpha" :transform="`translate(${flower.x} ${flower.y}) rotate(${(petal - 1) * 72 + 17.19})`" />
          </template>
        </g>
        <g class="login-art-rings"><circle v-for="radius in rings" :key="radius" cx="560" cy="230" :r="radius" /></g>
      </svg>
      <div class="login-art-brand"><img src="/favicon.svg?v=flower2api-pink-04" alt="flower2api 标志" width="32" height="32" /><b>flower2api</b></div>
      <div class="login-art-copy">
        <h2>让每一次调用<br>井然有序</h2>
        <p>账号、环境与任务，在一个清晰的控制台里管理。</p>
        <div class="login-art-meta"><span>本地管理控制台</span><span>仅管理员可访问</span></div>
      </div>
    </section>
    <div class="login-form-area">
      <form class="login-form" @submit.prevent="submit">
        <div class="login-mobile-brand" aria-hidden="true"><span class="console-toolbar-mark"><img src="/favicon.svg?v=flower2api-pink-04" alt="" width="20" height="20" /></span>flower2api</div>
        <div class="login-heading"><h1>登录控制台</h1><p>输入管理员密码，继续管理你的工作空间。</p></div>
        <div class="login-field">
          <label for="admin-password" class="fui-label">管理员密码</label>
          <InputGroup class="login-password">
            <template #prefix><Lock /></template>
            <Input id="admin-password" v-model="password" :type="revealed ? 'text' : 'password'" autocomplete="current-password" placeholder="管理员密码" />
            <template #suffix>
              <button type="button" class="login-reveal" :aria-label="revealed ? '隐藏密码' : '显示密码'" :aria-pressed="revealed" @click="revealed = !revealed"><Eye /></button>
            </template>
          </InputGroup>
        </div>
        <p v-if="error" role="alert" class="login-error">{{ error }}</p>
        <Button type="submit" size="lg" :disabled="loading" class="login-submit">{{ loading ? '登录中...' : '登录' }}</Button>
        <p class="login-note">登录凭据保存在当前浏览器，退出后清除</p>
      </form>
    </div>
  </div>
</template>
