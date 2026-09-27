# DejaVu web

The war-room UI for DejaVu (Next.js App Router, Tailwind, pnpm). It talks to the FastAPI backend over REST and Server-Sent Events.

```
pnpm install
pnpm dev      # http://localhost:3000
pnpm lint
pnpm build
```

Design tokens live in `src/app/globals.css` (spec Section 11.1). Violet (`memory`) is reserved for things DejaVu remembered.
