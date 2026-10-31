import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The capture server. Going through this proxy keeps captured pages on the client's origin, which is what
// lets the client apply patches inside them.
const CAPTURE_SERVER = 'http://localhost:3000';
const proxy = { '/api': CAPTURE_SERVER, '/snapshots': CAPTURE_SERVER };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { proxy },
});
