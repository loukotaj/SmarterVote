# Smarter.vote Web Application

A clean, modern web application for comparing political candidates using AI-powered analysis.

## � Prerequisites

- **Node.js**: Version 22.0.0 or higher
- **npm**: Version 10.0.0 or higher

## �🚀 Features

- **TypeScript Support**: Full TypeScript integration with proper type checking
- **Responsive Design**: Mobile-first design using Tailwind CSS
- **Static Site Generation**: Optimized for GitHub Pages deployment
- **AI-Powered Analysis**: Compare candidates on key political issues
- **SEO Optimized**: Proper meta tags, structured data, and social media cards

## 📁 Project Structure

```
web/
├── src/
│   ├── routes/            # SvelteKit routes
│   │   ├── +layout.svelte # Global layout with navigation
│   │   ├── +page.svelte   # Home page
│   │   ├── about/         # About page
│   │   └── races/[slug]/  # Dynamic race pages
│   ├── lib/
│   │   ├── components/    # Reusable Svelte components
│   │   └── types.ts       # TypeScript type definitions
│   ├── app.html          # HTML template
│   └── app.css           # Global styles
├── static/               # Static assets
├── build/                # Generated build output
└── package.json         # Dependencies and scripts
```

## 🛠️ Development

### Prerequisites
- Node.js 18 or higher
- npm

### Setup
```bash
npm install
npm run dev
```

### Building
```bash
npm run build
```

### Type Checking
```bash
npm run check
```

### Linting & Formatting
```bash
npm run lint
npm run format
```

## 🌐 Deployment

### GitHub Pages (Automatic)
The project is configured for automatic deployment via GitHub Actions:

1. Push to `main` branch
2. GitHub Actions builds and deploys automatically
3. Site available at `https://smarter.vote`

### Manual Deployment
```bash
npm run build:gh-pages
npm run deploy
```

## 🔧 Configuration

### Custom Domain
The `CNAME` file is configured for `smarter.vote`. To use a different domain:
1. Update `static/CNAME`
2. Configure DNS to point to GitHub Pages

### TypeScript
- Full TypeScript support in `.svelte` files
- Type definitions in `src/lib/types.ts`
- Strict type checking enabled

### SEO
- Structured data for search engines
- Open Graph tags for social media
- Custom meta descriptions per page
- Sitemap.xml and robots.txt included

## 📱 Browser Support

- Modern browsers (Chrome, Firefox, Safari, Edge)
- Mobile responsive design
- Progressive enhancement

## 🤝 Contributing

1. Use TypeScript for all new components
2. Follow existing code style and conventions
3. Test responsive design on mobile devices
4. Ensure accessibility best practices

## 📄 License

See LICENSE file in project root.
