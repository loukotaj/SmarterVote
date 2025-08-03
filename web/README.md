# SmarterVote Web Application

**Modern Electoral Analysis Interface** 🌐

*SvelteKit-powered frontend for AI-driven candidate comparison | Updated: August 2025*

## 🎯 Overview

A responsive, accessible web application that transforms complex electoral data into clear, actionable candidate comparisons. Built with modern web technologies and optimized for performance, accessibility, and democratic engagement.

## ⚡ Prerequisites

### System Requirements
- **Node.js**: Version 22.0.0 or higher
- **npm**: Version 10.0.0 or higher  
- **Modern Browser**: Support for ES2022+ features

### Development Tools
- **VS Code**: Recommended with Svelte extensions
- **Git**: Version control and collaboration

## 🚀 Features

### Core Functionality
- **🤖 AI-Powered Analysis**: Candidate comparisons across 11 canonical political issues
- **📱 Responsive Design**: Mobile-first approach with Tailwind CSS
- **⚡ Static Site Generation**: Optimized for GitHub Pages deployment
- **🔍 SEO Optimized**: Proper meta tags, structured data, and social media cards
- **♿ Accessibility**: WCAG 2.1 AA compliance focus

### Technical Features
- **TypeScript Support**: Full type safety with comprehensive type checking
- **Component Architecture**: Reusable Svelte components with proper encapsulation
- **Performance Optimized**: Code splitting, lazy loading, and minimal bundle size
- **Progressive Enhancement**: Works without JavaScript, enhanced with it

## 📁 Project Architecture

```
web/
├── src/
│   ├── routes/                    # SvelteKit file-based routing
│   │   ├── +layout.svelte        # Global layout with navigation
│   │   ├── +page.svelte          # Homepage with race listings
│   │   ├── about/                # About page and methodology
│   │   │   └── +page.svelte
│   │   └── races/[slug]/         # Dynamic race-specific pages
│   │       └── +page.svelte
│   ├── lib/
│   │   ├── components/           # Reusable UI components
│   │   │   ├── CandidateCard.svelte
│   │   │   ├── IssueComparison.svelte
│   │   │   └── ConfidenceIndicator.svelte
│   │   └── types.ts              # TypeScript type definitions
│   ├── app.html                  # HTML template with meta tags
│   ├── app.css                   # Global Tailwind CSS styles
│   └── app.d.ts                  # SvelteKit app type definitions
├── static/                       # Static assets and SEO files
│   ├── favicon.svg               # Site favicon
│   ├── robots.txt                # Search engine directives
│   ├── sitemap.xml               # SEO sitemap
│   └── CNAME                     # GitHub Pages domain config
├── build/                        # Generated static site output
├── package.json                  # Dependencies and build scripts
├── svelte.config.js              # SvelteKit configuration
├── tailwind.config.js            # Tailwind CSS customization
├── tsconfig.json                 # TypeScript configuration
└── vite.config.js                # Vite build tool configuration
```

## 🛠️ Development Workflow

### Initial Setup
```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Access at http://localhost:5173
```

### Development Commands
```bash
# Type checking
npm run check
npm run check:watch          # Watch mode

# Code quality
npm run lint                 # ESLint + Svelte linting
npm run format               # Prettier formatting

# Testing
npm run test:unit            # Vitest unit tests
npm run test:integration     # Playwright integration tests
npm run test                 # Run all tests

# Building
npm run build                # Production build
npm run preview              # Preview built site
```

### Hot Module Replacement
The development server supports HMR for:
- Svelte component updates
- CSS/Tailwind changes  
- TypeScript modifications
- Route changes

## 🎨 Design System

### Color Palette
- **Primary**: Democratic blue with accessibility-compliant contrast
- **Secondary**: Neutral grays for content hierarchy
- **Accent**: Alert colors for confidence indicators
- **Semantic**: Success, warning, and error states

### Typography
- **Headings**: System font stack with fallbacks
- **Body**: Optimized for readability across devices
- **Code**: Monospace for technical content

### Component Library
- **CandidateCard**: Structured candidate information display
- **IssueComparison**: Side-by-side position analysis
- **ConfidenceIndicator**: Visual confidence scoring
- **NavigationBar**: Responsive navigation component

## 🌐 Deployment & Hosting

### GitHub Pages (Production)
**Automatic Deployment:**
1. Push to `main` branch triggers GitHub Actions
2. SvelteKit builds static site optimized for GitHub Pages
3. Deployed automatically to `https://smarter.vote`

**Manual Deployment:**
```bash
# Build and deploy manually
npm run build:gh-pages
npm run deploy
```

### Local Preview
```bash
# Build production site locally
npm run build

# Preview built site
npm run preview
```

### Custom Domain Configuration
- **CNAME**: Configured for `smarter.vote` domain
- **SSL**: Automatically provided by GitHub Pages
- **CDN**: Global content delivery via GitHub's infrastructure

## ⚡ Performance Optimization

### Build Optimizations
- **Code Splitting**: Automatic route-based splitting
- **Tree Shaking**: Dead code elimination
- **Minification**: CSS and JavaScript compression
- **Asset Optimization**: Image and font optimization

### Runtime Performance
- **Preloading**: Critical resource preloading
- **Lazy Loading**: Non-critical content lazy loading  
- **Caching**: Service worker for offline capability
- **Bundle Analysis**: Regular bundle size monitoring

### Performance Metrics
- **Lighthouse Score**: >95 target across all categories
- **First Contentful Paint**: <1.5 seconds
- **Largest Contentful Paint**: <2.5 seconds
- **Cumulative Layout Shift**: <0.1

## ♿ Accessibility Features

### WCAG 2.1 AA Compliance
- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Reader Support**: Proper ARIA labels and semantics
- **Color Contrast**: Minimum 4.5:1 contrast ratios
- **Focus Management**: Clear focus indicators

### Semantic HTML
- **Proper Headings**: Logical heading hierarchy
- **Landmark Regions**: Navigation, main, and complementary regions
- **Form Labels**: Associated labels for all form controls
- **Alternative Text**: Descriptive alt text for images

## 🧪 Testing Strategy

### Unit Testing (Vitest)
- **Component Testing**: Individual component functionality
- **Utility Testing**: Helper function validation
- **Store Testing**: State management testing

### Integration Testing (Playwright)
- **User Workflows**: End-to-end user interactions
- **Cross-Browser**: Chrome, Firefox, Safari testing
- **Mobile Testing**: Responsive design validation

### Test Commands
```bash
# Run unit tests
npm run test:unit

# Run integration tests  
npm run test:integration

# Run all tests with coverage
npm run test -- --coverage

# Watch mode for development
npm run test:unit -- --watch
```

## 🔧 Advanced Configuration

### Environment Variables
```bash
# Development
VITE_API_BASE_URL=http://localhost:3000

# Production  
VITE_API_BASE_URL=https://api.smarter.vote
```

### SvelteKit Configuration (`svelte.config.js`)
```javascript
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: null,
      precompress: false
    }),
    prerender: {
      default: true
    }
  }
};
```

### Tailwind Configuration (`tailwind.config.js`)
```javascript
module.exports = {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        primary: '#1e40af',
        secondary: '#64748b'
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};
```

## 🚀 Future Enhancements

### Planned Features
- **Dark Mode**: User-preferred color scheme
- **Advanced Filtering**: Multi-criteria race filtering
- **Comparison Tools**: Side-by-side candidate analysis
- **Mobile App**: Progressive Web App capabilities

### Technical Improvements
- **Internationalization**: Multi-language support
- **Offline Support**: Enhanced service worker
- **Real-time Updates**: WebSocket integration
- **Performance**: Further optimization opportunities

---

**Democratic Technology Built with Modern Web Standards** 🗳️

*Empowering informed voting through accessible, performant, and beautiful interfaces*

*Last updated: August 2025*
