import { createApp } from 'vue';
import '../../legacy-web/ui-foundation.css';
import './style.css';
import './components/ui/kit.css';
import './console-shell.css';
import './approved-design.css';
import './proxy-design.css';
import App from './App.vue';
import router from './router';
import { initTheme } from './theme';

// 挂载前应用已保存的主题，首次渲染即为用户主题。
initTheme();
createApp(App).use(router).mount('#app');
