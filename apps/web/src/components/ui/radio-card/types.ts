/** 单选卡选项；同组 value 必须唯一，description 为一行说明。 */
export interface RadioCardOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}
