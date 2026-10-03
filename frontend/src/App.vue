<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
:root {
  /* Claude「纸与墨」色板 */
  --app-bg: #f5f3ec;
  --app-bg-deep: #edeae0;
  --app-surface: #ffffff;
  --app-surface-muted: #f3f0e6;
  --app-text: #29261f;
  --app-text-muted: #736f62;
  --app-border: #e5e0d0;
  --app-border-strong: #d4cebb;
  --app-action: #c15f3c;
  --app-action-hover: #ac5232;
  --app-action-active: #96452a;
  --app-action-contrast: #fbf7f0;
  --app-action-soft: #f6e7dc;
  --app-danger: #b5402f;
  --app-success: #527a5b;
  --app-warning: #96762a;
  --app-font-serif: Georgia, "Times New Roman", "Songti SC", "STSong", "SimSun", "Noto Serif SC", serif;
  --app-font-mono: "SF Mono", "Cascadia Code", ui-monospace, SFMono-Regular, Menlo, Consolas, "Courier New", monospace;

  /* TDesign 主题变量 */
  --td-brand-color: var(--app-action);
  --td-brand-color-hover: var(--app-action-hover);
  --td-brand-color-active: var(--app-action-active);
  --td-brand-color-disabled: #dcc8bb;
  --td-brand-color-light: var(--app-action-soft);
  --td-brand-color-focus: rgba(193, 95, 60, 0.22);
  --td-success-color: var(--app-success);
  --td-warning-color: var(--app-warning);
  --td-error-color: var(--app-danger);
  --td-text-color-primary: var(--app-text);
  --td-text-color-secondary: var(--app-text-muted);
  --td-bg-color-page: var(--app-bg);
  --td-bg-color-container: var(--app-surface);
  --td-bg-color-container-hover: var(--app-surface-muted);
  --td-bg-color-secondarycontainer: var(--app-surface-muted);
  --td-bg-color-component: var(--app-surface);
  --td-component-border: var(--app-border);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

html,
body,
#app {
  min-height: 100%;
}

body {
  color: var(--app-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background-color: var(--app-bg);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

::selection {
  background: #efd9c8;
}

button,
input,
textarea,
select {
  font: inherit;
  -webkit-user-select: text;
  user-select: text;
}

code,
pre {
  font-family: var(--app-font-mono);
}

:focus-visible {
  outline: 2px solid var(--app-action);
  outline-offset: 2px;
}

/* —— 卡片 —— */
.t-card {
  overflow: hidden;
  background: var(--app-surface);
  border: 1px solid var(--app-border) !important;
  border-radius: 14px;
  box-shadow: none;
}

.t-card__header {
  min-height: auto;
  padding: 22px 24px 18px;
  border-bottom: 1px solid var(--app-border);
}

.t-card__title {
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.t-card__subtitle {
  margin-top: 6px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.t-card__body {
  padding: 22px 24px 24px;
}

/* —— 按钮 —— */
.t-button {
  min-height: 36px;
  border-radius: 9px;
  box-shadow: none !important;
  transition: color 0.18s ease, background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.t-button--theme-primary.t-button--variant-base {
  color: var(--app-action-contrast);
  background: var(--app-action);
  border-color: var(--app-action);
}

.t-button--theme-primary.t-button--variant-base:hover {
  color: var(--app-action-contrast);
  background: var(--app-action-hover);
  border-color: var(--app-action-hover);
}

.t-button--theme-primary.t-button--variant-base:active {
  background: var(--app-action-active);
  border-color: var(--app-action-active);
  transform: translateY(1px);
}

.t-button--theme-primary.t-button--variant-outline,
.t-button--theme-primary.t-button--variant-text {
  color: var(--app-action);
}

.t-button--theme-primary.t-button--variant-outline:hover,
.t-button--theme-primary.t-button--variant-text:hover {
  color: var(--app-action-hover);
}

.t-button--variant-outline {
  color: var(--app-text);
  background: var(--app-surface);
  border-color: var(--app-border-strong);
}

.t-button--variant-outline:hover {
  color: var(--app-text);
  background: var(--app-surface-muted);
  border-color: #b8b19d;
}

.t-button--theme-danger.t-button--variant-outline {
  color: var(--app-danger);
  background: var(--app-surface);
  border-color: #e3c4bc;
}

.t-button--theme-danger.t-button--variant-outline:hover {
  color: #93342a;
  background: #f9ece8;
  border-color: #d3a79d;
}

.t-button--variant-text:hover {
  background: var(--app-surface-muted);
}

/* —— 链接 —— */
.t-link {
  font-weight: 500;
}

.t-link--theme-primary {
  color: var(--app-action);
}

.t-link--theme-primary:hover {
  color: var(--app-action-hover);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* —— 表单 —— */
.t-input,
.t-textarea,
.t-input-number,
.t-select-input {
  border-color: var(--app-border);
  border-radius: 9px;
  box-shadow: none;
}

.t-input:hover,
.t-textarea:hover,
.t-input-number:hover,
.t-select-input:hover {
  border-color: #b8b19d;
}

.t-input--focused,
.t-textarea--focused,
.t-input-number.t-is-focused,
.t-select-input.t-is-focused {
  border-color: var(--app-action);
  box-shadow: 0 0 0 3px rgba(193, 95, 60, 0.16);
}

.t-form__label {
  color: var(--app-text);
}

/* —— 表格 —— */
.t-table {
  color: var(--app-text);
  border-radius: 10px;
}

.t-table th {
  color: #5c574a;
  font-size: 13px;
  font-weight: 600;
  background: var(--app-surface-muted);
}

.t-table td,
.t-table th {
  border-color: var(--app-border);
}

.t-table tbody tr > td {
  transition: background 0.15s ease;
}

.t-table tbody tr:hover > td {
  background: #faf8f1 !important;
}

/* —— 标签 —— */
.t-tag {
  border-radius: 999px;
}

.t-tag--default {
  color: #6b6656;
  background: #f0ede2;
}

.t-tag--primary {
  color: #a04b2c;
  background: var(--app-action-soft);
}

.t-tag--success {
  color: var(--app-success);
  background: #e8efe9;
}

.t-tag--danger {
  color: var(--app-danger);
  background: #f9ece8;
}

.t-tag--warning {
  color: var(--app-warning);
  background: #f6efdc;
}

/* —— 分页 —— */
.t-pagination__number.t-is-current {
  color: var(--app-action-contrast);
  background: var(--app-action);
  border-color: var(--app-action);
}

/* —— 对话框 —— */
.t-dialog {
  overflow: hidden;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(64, 52, 36, 0.18);
}

.t-dialog__ctx .t-dialog__mask {
  background: rgba(46, 40, 30, 0.4);
}

.t-dialog__header {
  padding: 22px 24px 18px;
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 20px;
  font-weight: 600;
  border-bottom: 1px solid var(--app-border);
}

.t-dialog__body {
  padding: 24px;
  color: var(--app-text);
}

.t-dialog__footer {
  padding: 16px 24px 20px;
  border-top: 1px solid var(--app-border);
}

.t-dialog__close {
  color: var(--app-text-muted);
  border-radius: 6px;
}

.t-dialog__close:hover {
  color: var(--app-text);
  background: var(--app-surface-muted);
}

/* —— 全局消息 —— */
.t-message {
  min-height: 44px;
  padding: 10px 14px;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  box-shadow: 0 12px 36px rgba(64, 52, 36, 0.14);
}

.t-message.t-is-success > .t-icon,
.t-message.t-is-success > [data-t-icon] > .t-icon {
  color: var(--app-success);
}

.t-message.t-is-warning > .t-icon,
.t-message.t-is-warning > [data-t-icon] > .t-icon {
  color: var(--app-warning);
}

.t-message.t-is-error > .t-icon,
.t-message.t-is-error > [data-t-icon] > .t-icon {
  color: var(--app-danger);
}

/* —— 浮层 —— */
.t-popup__content {
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  box-shadow: 0 14px 40px rgba(64, 52, 36, 0.15);
}

.t-popconfirm .t-popup__content {
  padding: 16px;
}

.t-popconfirm__body {
  color: var(--app-text);
}

.t-popconfirm__buttons {
  margin-top: 16px;
}

.t-dropdown__menu {
  padding: 6px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  box-shadow: 0 14px 40px rgba(64, 52, 36, 0.15);
}

.t-dropdown__item {
  border-radius: 7px;
}

.t-dropdown__item:hover {
  background: var(--app-surface-muted);
}

/* —— 警告与描述 —— */
.t-alert {
  color: #6b6656;
  background: #f2efe4;
  border-color: var(--app-border);
  border-radius: 10px;
}

.t-descriptions__body td,
.t-descriptions__body th {
  border-color: var(--app-border);
}

/* —— 选项卡 —— */
.t-tabs__nav-item.t-is-active {
  color: var(--app-action);
}

.t-tabs__bar {
  background: var(--app-action);
}

@supports ((-webkit-backdrop-filter: blur(0)) or (backdrop-filter: blur(0))) {
  .t-popup,
  .t-dialog {
    -webkit-backdrop-filter: blur(0);
    backdrop-filter: blur(0);
  }
}

@media (max-width: 720px) {
  .t-card__header {
    padding: 20px 18px 16px;
  }

  .t-card__body {
    padding: 18px;
  }

  .t-dialog {
    width: calc(100vw - 32px) !important;
    max-width: calc(100vw - 32px);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
