/** 单选菜单选项；同组value必须唯一，空字符串代表调用方定义的未设置状态。 */
export interface ChoiceOption {
  value: string;
  label: string;
  disabled?: boolean;
}
