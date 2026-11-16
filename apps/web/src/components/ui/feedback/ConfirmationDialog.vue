<script setup lang="ts">
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../dialog';
import { Button } from '../button';
import { AlertCircle } from '../icon';

/** 业务所有者保留请求及错误，公共窗口只负责展示和交互。 */
const props = withDefaults(defineProps<{ open: boolean; title: string; message?: string; confirmLabel?: string; danger?: boolean; busy?: boolean; error?: string }>(), { confirmLabel: '确认继续' });
const emit = defineEmits<{ confirm: []; cancel: [] }>();
/** 提交期间保持窗口，取消由调用者收口。@return 无。 */
function cancel(): void { if (!props.busy) emit('cancel'); }
</script>
<template>
  <Dialog :open="open" @update:open="value => { if (!value) cancel(); }">
    <DialogContent class="fui-confirm-dialog" :show-close-button="!busy" @escape-key-down="event => { if (busy) event.preventDefault(); }" @interact-outside="event => { if (busy) event.preventDefault(); }">
      <DialogHeader><DialogTitle>{{ title }}</DialogTitle><DialogDescription>{{ message }}</DialogDescription></DialogHeader>
      <div v-if="$slots.default" class="fui-confirm-content"><slot /></div>
      <p v-if="error" class="fui-action-error" role="alert"><AlertCircle :size="18" />{{ error }}</p>
      <footer class="fui-confirm-footer"><Button variant="outline" :disabled="busy" @click="cancel">取消</Button><Button :variant="danger ? 'destructive' : 'default'" :disabled="busy" @click="emit('confirm')">{{ busy ? '处理中…' : confirmLabel }}</Button></footer>
    </DialogContent>
  </Dialog>
</template>
