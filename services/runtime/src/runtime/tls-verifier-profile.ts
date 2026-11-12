/** 独立 TLS 辅助程序的候选身份；交付前必须通过完整回环验收，构建不会自动授信。 */
export const TLS_VERIFIER_IDENTITY = {
  profile: 'claude-code-2.1.293',
  sha256: 'f41c1aff4c4836767790a67cab57370446a7610cb7ec79ae9d7c44e5ec02fb01',
  target: 'x86_64-unknown-linux-gnu',
  recipe: 1,
} as const;
