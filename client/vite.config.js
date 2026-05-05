import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: [
      'localhost', 'ec2-98-82-30-138.compute-1.amazonaws.com'
    ]
  },
});
