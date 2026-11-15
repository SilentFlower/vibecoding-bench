declare module 'virtual:task-runtime' {
  /** 编译时冻结的任务DOM模板。 */
  export const template: string;
  /** 挂载执行控制器。@param scope 宿主管理的浏览器接口。@return 生命周期清理。 */
  export function mount(scope: ReturnType<typeof import('./components/runtime/runtimeScope').createRuntimeScope>['scope']): {dispose():void};
}

declare module 'virtual:task-runtime-style.css';
