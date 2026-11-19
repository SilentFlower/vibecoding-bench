import { defineComponent, h } from 'vue';
import sprite from '@/assets/approved-icons.svg?url&no-inline';

/** 创建确认稿的SVG图标，复用相同路径与1.7描边。
 * @param name 确认稿中的图标名称。
 * @return 支持size及普通SVG属性的Vue组件。
 */
function icon(name: string) {
  return defineComponent({
    name: `ApprovedIcon${name}`,
    props: { size: { type: [Number, String], default: 19 } },
    setup: props => () => h('svg', {
      width: props.size, height: props.size, viewBox:'0 0 24 24', fill:'none',
      stroke:'currentColor', 'stroke-width':1.7, 'stroke-linecap':'round', 'stroke-linejoin':'round',
      'aria-hidden':'true',
    }, [h('use', { href:`${sprite}#i-${name}` })]),
  });
}

export const Pencil = icon('edit');
export const RefreshCw = icon('refresh');
export const Activity = icon('wave');
export const ArrowRight = icon('arrow');
export const ArrowUpRight = icon('arrow');
export const Trash2 = icon('trash');
export const Globe = icon('globe');
export const Box = icon('box');
export const Boxes = icon('box');
export const Server = icon('server');
export const ChevronRight = icon('chevron');
export const KeyRound = icon('key');
export const Plus = icon('plus');
export const Check = icon('check');
export const Users = icon('users');
export const ListTodo = icon('task');
export const Settings2 = icon('settings');
export const LayoutGrid = icon('grid');
export const Files = icon('task');
export const FileText = icon('task');
export const ShieldCheck = icon('shield');
export const Download = icon('download');
export const Copy = icon('copy');
export const X = icon('close');
export const Menu = icon('menu');
export const LogOut = icon('logout');
export const PanelLeftClose = icon('panel');
export const PanelLeftOpen = icon('panel');

export const Search = icon('search');

export const AlertCircle = icon('alert');
export const Clock = icon('clock');
