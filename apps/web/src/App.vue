<script setup lang="ts">
import { FeedbackHost } from './components/ui/feedback';
import { useActiveScrollbars } from './composables/useActiveScrollbars';
useActiveScrollbars();
</script>
<template>
  <div class="min-h-screen"><router-view /><FeedbackHost /></div>
</template>
