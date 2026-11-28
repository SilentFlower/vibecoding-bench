<script setup lang="ts">
import type { RuntimeEnvironment } from './runtimeApi';
import { environmentRoles, environmentRoleStatus, installedCliLabel } from './environmentLabels';

defineProps<{ environment: RuntimeEnvironment }>();
</script>

<template>
  <section class="workspace-properties" aria-label="基本信息">
    <h4>基本信息</h4>
    <div class="kv"><span>环境 ID</span><strong><code>{{ environment.environment_id }}</code></strong></div>
    <div class="kv"><span>已安装 CLI 版本</span><strong>{{ installedCliLabel(environment) }}</strong></div>
    <div class="kv"><span>账号镜像批次</span><strong>{{ environment.runtime_release || (environment.runtime_release_error ? '待核对' : '未观测') }}</strong></div>
    <div v-for="role in environmentRoles" :key="role.id" class="kv">
      <span>{{ role.statusLabel }}</span><strong>{{ environmentRoleStatus(environment.role_status?.[role.id]) }}</strong>
    </div>
  </section>
</template>

<style scoped>
h4 {
  margin: 0;
  color: var(--ui-color-text);
  font-size: var(--ui-font-size-md);
  font-weight: 650;
}
</style>
