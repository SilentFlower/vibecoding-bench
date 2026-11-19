import { createApp } from 'vue';
import UiPreview from './UiPreview.vue';
import '../../../legacy-web/ui-foundation.css';
import '../style.css';
import '../components/ui/kit.css';
import { initTheme } from '../theme';

initTheme();
createApp(UiPreview).mount('#app');
