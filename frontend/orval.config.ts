import { defineConfig } from 'orval'

// Genera tipos y hooks de TanStack Query desde el esquema OpenAPI del backend.
// Regenerar con `npm run api:generate` (requiere openapi.json actualizado: `make schema`).
export default defineConfig({
  api: {
    input: './openapi.json',
    output: {
      mode: 'tags-split',
      target: './src/api/generated',
      schemas: './src/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      prettier: true,
      override: {
        mutator: { path: './src/api/mutator.ts', name: 'customFetch' },
        fetch: { includeHttpResponseReturnType: false },
        query: { signal: true },
      },
    },
  },
})
