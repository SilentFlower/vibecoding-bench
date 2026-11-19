<!-- 工具栏：默认插槽放左侧筛选 / 分段，end 插槽靠右放搜索等；窄屏自动换行。 -->
<template>
  <div class="fui-toolbar" data-slot="toolbar">
    <slot />
    <div v-if="$slots.end" class="fui-toolbar-end"><slot name="end" /></div>
  </div>
</template>
