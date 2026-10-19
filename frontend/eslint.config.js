// Análisis estático del frontend.
//
// Existe porque Vite compila aunque un componente o una variable no estén
// importados: el fallo solo aparece al abrir esa pantalla. Así llegó a Pau
// "Can't find variable: PromptCatalog". Aquí solo se vigila lo que rompe la
// app en ejecución (no el estilo).
import solid from 'eslint-plugin-solid/configs/recommended'
import globals from 'globals'

export default [
  {
    files: ['src/**/*.{js,jsx}'],
    ...solid,
    languageOptions: {
      ...solid.languageOptions,
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser },
    },
    rules: {
      'no-undef': 'error',               // variables y funciones sin definir
      'solid/jsx-no-undef': 'error',     // componentes <X /> sin importar
      'no-dupe-keys': 'error',
      'no-unreachable': 'error',
    },
  },
]
