<script setup lang="ts">
/**
 * 实体卡：图标块 / 头像 + 名称 + 副标题 + 状态徽标的统一头部，信息区，等分操作底栏。
 * @prop title 名称（h3）。
 * @prop subtitle 副标题；subtitle 插槽可覆盖（如附带节点徽标）。
 * 插槽 media：头部左侧图标块或头像；title-extra：名称后的徽标；status：右侧状态徽标；
 * 默认插槽：信息区（EntityBlock 等）；actions：底栏 EntityAction。
 */
defineProps<{ title: string; subtitle?: string }>();
</script>

<template>
  <article class="fui-entity-card" data-slot="entity-card" :class="{ 'has-actions': $slots.actions }">
    <header class="fui-entity-card-head">
      <slot name="media" />
      <div class="fui-entity-card-identity">
        <h3 class="fui-entity-card-title"><span class="fui-entity-card-name">{{ title }}</span><slot name="title-extra" /></h3>
        <p v-if="subtitle || $slots.subtitle" class="fui-entity-card-subtitle"><slot name="subtitle">{{ subtitle }}</slot></p>
      </div>
      <div v-if="$slots.status" class="fui-entity-card-status"><slot name="status" /></div>
    </header>
    <slot />
    <footer v-if="$slots.actions" class="fui-entity-card-actions"><slot name="actions" /></footer>
  </article>
</template>
