import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    return {
        plugins: [sveltekit()],
        server: {
            port: 3000,
            host: true
        },
        build: {
            target: 'es2020',
            sourcemap: false,
            rollupOptions: {
                output: {
                    manualChunks: {
                        vendor: ['svelte']
                    }
                }
            }
        },
        optimizeDeps: {
            include: ['svelte']
        },
        define: {
            'process.env.PUBLIC_API_BASE_URL': JSON.stringify(env.PUBLIC_API_BASE_URL || '')
        }
    };
});
