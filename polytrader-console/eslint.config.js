import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import eslintConfigPrettier from 'eslint-config-prettier/flat'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores([
    'dist',
    'node_modules',
    'coverage',
    '**/*.d.ts',
    '**/*.generated.*',
    'src/lib/api',
  ]),

  js.configs.recommended,

  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      ...tseslint.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        // With project refs: root has "files":[] so list both ref configs (same graph as tsc -b)
        project: ['./tsconfig.app.json', './tsconfig.node.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // React Refresh HMR safety
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // Avoid double-noise: TS already checks unused locals/params
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],

      // Keeps imports clean and type-safe
      '@typescript-eslint/consistent-type-imports': [
        'warn',
        { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
      ],

      // Real bug-catchers (type-aware)
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } },
      ],

      // Style preference: let TS/Prettier handle this area
      '@typescript-eslint/require-await': 'off',
    },
  },

  // Node-side files (Vite/ESLint config, scripts, etc.)
  {
    files: ['**/*.{config,setup}.{ts,js}', 'scripts/**/*.{ts,js}'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },

  eslintConfigPrettier,
])
