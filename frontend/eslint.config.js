import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

/**
 * FR-X-001 / CLAUDE.md rule 8: no hard-coded user-facing text in JSX. Visible text must come
 * from t('...'). Small local rule instead of a plugin dependency.
 */
const noLiteralText = {
  meta: {
    type: 'problem',
    messages: { literal: 'Use t("...") instead of literal text: "{{text}}"' },
  },
  create(context) {
    const report = (node, text) => {
      if (/\p{L}/u.test(text))
        context.report({ node, messageId: 'literal', data: { text: text.trim() } })
    }
    const textAttributes = new Set(['aria-label', 'title', 'placeholder', 'alt', 'label'])
    return {
      JSXText(node) {
        report(node, node.value)
      },
      JSXAttribute(node) {
        if (textAttributes.has(node.name.name) && node.value?.type === 'Literal') {
          report(node, String(node.value.value))
        }
      },
    }
  },
}

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'src/lib/api/*.d.ts', 'playwright-report', 'test-results'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      local: { rules: { 'no-literal-text': noLiteralText } },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'local/no-literal-text': 'error',
    },
  },
  { files: ['**/*.test.{ts,tsx}', 'e2e/**'], rules: { 'local/no-literal-text': 'off' } },
)
