import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import tsParser from '@typescript-eslint/parser'

export default [
  {
    ignores: [
      'dist',
      'node_modules',
      'visualization/dist',
      'src/auto-imports.d.ts',
      'src/components.d.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    // .vue 的 <script> 块用 TypeScript parser 解析, 否则报 Parsing error
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        sourceType: 'module',
        ecmaVersion: 'latest',
      },
    },
  },
  {
    // 配置文件允许 require() 风格导入（如 tailwind 插件）
    files: ['**/*.config.ts', '**/tailwind.config.ts', '**/postcss.config.js'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
  {
    rules: {
      // 单文件组件允许单单词名 (App.vue / XIcon.vue 等)
      'vue/multi-word-component-names': 'off',
      // 以下在推荐集中为 error/warn, 调低以避免一次性刷屏阻断 CI;
      // 均为 warning, 不影响 `eslint . --fix` 退出码 (仅 error 会失败)
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-empty-object-type': 'warn',
      '@typescript-eslint/no-namespace': 'off',
      'no-undef': 'off',
    },
  },
]
