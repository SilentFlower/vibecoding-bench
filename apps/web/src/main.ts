import { createApp } from 'vue';
import './style.css';
import './approved-design.css';
import './proxy-design.css';
import App from './App.vue';
import router from './router';

createApp(App).use(router).mount('#app');
